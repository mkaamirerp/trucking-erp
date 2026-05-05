"""Stateless semantic PDF → LoadDocumentParseResponse (B4 prompt + json_schema).

No DB, no Load Lab runs, no router. Optional injected OpenAI callable for tests / wiring.

Deferred: broker DB grounding, Load Lab guarded pipeline parity.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from app.core.config import settings
from app.schemas.load_document_parse import (
    LoadDocumentParseResponse,
    LoadParseDocumentMeta,
    LoadParseExtractedFields,
    ParseDocumentSemanticModelOutput,
)
from app.services.load_document_parse import _extract_text_and_pages_from_pdf_bytes
from app.services.load_document_parse_adapter import map_lab_parse_response_to_document_contract

_CONTEXT_ECHO_ALLOW = frozenset({"email_thread_id", "load_id"})
_MAX_USER_TEXT = 80_000
_LABISH_ROOT_KEYS = frozenset(
    {"parse_diagnostics", "run_id", "ai_model_output", "semantic_extract_status"}
)

SEMANTIC_PROMPT_VERSION_PARSE_DOCUMENT = "parse_document_prompt_v1"
SEMANTIC_SCHEMA_VERSION_PARSE_DOCUMENT = "parse_document_semantic_schema_v1"
_PARSE_DOCUMENT_SEMANTIC_SCHEMA_NAME = "parse_document_semantic_v1"

_OPENAI_RESPONSE_JSON_SCHEMA: dict[str, Any] = ParseDocumentSemanticModelOutput.model_json_schema()

_PUBLIC_CONTEXT_ALLOW_KEYS = frozenset(
    {
        "parse_path",
        "semantic_outcome",
        "email_thread_id",
        "load_id",
        "semantic_model",
        "semantic_prompt_version",
        "semantic_schema_version",
        "semantic_schema_name",
        "provider_status",
        "text_truncated",
    }
)

PARSE_DOCUMENT_SEMANTIC_SYSTEM_PROMPT = """You extract structured load data from trucking rate confirmations and load confirmation documents (PDF text provided by the user).

Output must be a single JSON object matching the response schema: document, extracted, warnings, and field_confidence only. Do not include raw_text, context, or OpenAI wire fields.

Field goals (extracted.*):
- Broker / party: broker_name_snapshot = freight broker or logistics company issuing the rate con (not the carrier, not the shipper/consignee unless they are clearly the broker). Do not use carrier signature blocks, driver lines, or "carrier" sections as broker identity.
- broker_mc_number_snapshot, broker_dot_number_snapshot: only when clearly labeled as MC-/DOT for the broker party. Otherwise null.
- broker_contact_*: dispatch / broker contact if clearly labeled, not generic carrier contacts.
- broker_load_reference: primary load ID, order number, PRO#, or reference the broker uses for this shipment. Prefer labeled "Load", "Order", "Ref", "Shipment" lines. Do not confuse with BOL#, trailer#, equipment unit numbers, phone numbers, or weights.
- rate: linehaul / total carrier rate as a number (USD) when clearly stated. customer_rate if a distinct customer-facing rate appears.
- miles: loaded or payable miles if present.
- mode, equipment_type, trailer_type, trailer_size, commodity, estimated_weight, temperature_requirement, customs_broker_name: fill when clearly supported by text; otherwise null.
- references: array of {kind, value, ...} for secondary refs (BOL, PO, etc.) when present.
- stops: physical pickup and delivery stops only, in route order. Each stop: stop_type (pickup | delivery | drop | other), sequence (0-based order along the route), facility_name, street, city, state_or_province, postal_code, country, reference_number, appointment_type, appointment_date (use YYYY-MM-DD when you can infer unambiguously), appointment_time_text, notes. Do not duplicate header/office/bill-to addresses as stops unless they are actual shipper/consignee locations for this move. Do not invent stops.
- warnings: add human-readable strings for uncertainty (e.g. ambiguous ref, conflicting rates, missing appointment). Use [] if none.

field_confidence: optional map from extracted field path (e.g. broker_load_reference) to low|medium|high. Omit keys you do not assess.

Rules:
- Do not invent values. Use null or omit optional fields when unknown.
- Preserve meanings from the document; do not normalize away critical identifiers.
- Do not stuff unrelated numbers into weight, rate, or reference fields.
- If the text is not a load/rate confirmation, return minimal extracted with a warning explaining that.
"""


def _safe_filename(filename: str | None) -> str:
    return (filename or "upload.pdf")[:512]


def _sanitize_public_context(ctx: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in ctx.items() if k in _PUBLIC_CONTEXT_ALLOW_KEYS}


def _semantic_meta(*, model: str, schema_name: str, raw_text: str) -> dict[str, Any]:
    return {
        "semantic_model": model,
        "semantic_prompt_version": SEMANTIC_PROMPT_VERSION_PARSE_DOCUMENT,
        "semantic_schema_version": SEMANTIC_SCHEMA_VERSION_PARSE_DOCUMENT,
        "semantic_schema_name": schema_name,
        "text_truncated": len(raw_text) > _MAX_USER_TEXT,
    }


def _merge_public_context(
    res: LoadDocumentParseResponse,
    *,
    context_echo: dict[str, Any] | None,
    parse_path: str,
    semantic_outcome: str,
    extra: dict[str, Any] | None = None,
) -> LoadDocumentParseResponse:
    echo = {
        k: v
        for k, v in (context_echo or {}).items()
        if k in _CONTEXT_ECHO_ALLOW
    }
    ctx = dict(res.context) if res.context else {}
    if extra:
        ctx.update(extra)
    ctx.update(echo)
    ctx["parse_path"] = parse_path
    ctx["semantic_outcome"] = semantic_outcome
    ctx = _sanitize_public_context(ctx)
    return res.model_copy(update={"context": ctx})


def _sparse_response(
    *,
    filename: str,
    raw_text: str,
    warnings: list[str],
    context_echo: dict[str, Any] | None,
    parse_path: str,
    semantic_outcome: str,
    extra: dict[str, Any] | None = None,
) -> LoadDocumentParseResponse:
    out = LoadDocumentParseResponse(
        document=LoadParseDocumentMeta(filename=_safe_filename(filename)),
        extracted=LoadParseExtractedFields(),
        raw_text=raw_text,
        warnings=list(warnings),
        field_confidence={},
        context={},
    )
    return _merge_public_context(
        out,
        context_echo=context_echo,
        parse_path=parse_path,
        semantic_outcome=semantic_outcome,
        extra=extra,
    )


def _map_semantic_model_to_document_response(
    ai: ParseDocumentSemanticModelOutput,
    *,
    server_filename: str,
    raw_text: str,
) -> LoadDocumentParseResponse:
    """Attach server-controlled filename and PDF text; AI supplies extracted + warnings + confidence."""
    return LoadDocumentParseResponse(
        document=LoadParseDocumentMeta(filename=_safe_filename(server_filename)),
        extracted=ai.extracted,
        raw_text=raw_text,
        warnings=list(ai.warnings),
        field_confidence=dict(ai.field_confidence),
        context={},
    )


def _injected_dict_to_load_response(
    candidate: dict[str, Any],
    *,
    server_filename: str,
    raw_text: str,
) -> LoadDocumentParseResponse:
    """Lab-shaped → mapper; otherwise B4 semantic model output → LoadDocumentParseResponse."""
    if any(k in candidate for k in _LABISH_ROOT_KEYS):
        return map_lab_parse_response_to_document_contract(candidate)
    ai = ParseDocumentSemanticModelOutput.model_validate(candidate)
    return _map_semantic_model_to_document_response(ai, server_filename=server_filename, raw_text=raw_text)


async def parse_load_workspace_from_pdf_semantic_stateless(
    pdf_bytes: bytes,
    *,
    filename: str,
    context_echo: dict[str, Any] | None = None,
    openai_chat_json_schema: Callable[..., Awaitable[dict[str, Any]]] | None = None,
) -> LoadDocumentParseResponse:
    """Extract PDF text; optionally run injected OpenAI-compatible call; return workspace contract.

    ``openai_chat_json_schema`` receives a real JSON Schema for ``ParseDocumentSemanticModelOutput``.
    Returned dict must be a JSON object (no raw ``choices`` wire). ``context`` from models is dropped
    by the schema; allowlisted context is applied server-side.
    """
    parse_path = "semantic_stateless"
    fn = _safe_filename(filename)
    raw_text, _page_texts, extract_warnings = _extract_text_and_pages_from_pdf_bytes(pdf_bytes)
    warnings: list[str] = list(extract_warnings)

    model = (settings.openai_extraction_model or "gpt-4o-mini").strip() or "gpt-4o-mini"
    meta = _semantic_meta(model=model, schema_name=_PARSE_DOCUMENT_SEMANTIC_SCHEMA_NAME, raw_text=raw_text)

    if not (raw_text or "").strip():
        warnings.append("No extractable text from PDF; semantic extraction skipped.")
        return _sparse_response(
            filename=fn,
            raw_text=raw_text,
            warnings=warnings,
            context_echo=context_echo,
            parse_path=parse_path,
            semantic_outcome="skipped_no_text",
            extra=meta,
        )

    if openai_chat_json_schema is None:
        warnings.append("[semantic] Semantic extraction skipped (no OpenAI client supplied).")
        return _sparse_response(
            filename=fn,
            raw_text=raw_text,
            warnings=warnings,
            context_echo=context_echo,
            parse_path=parse_path,
            semantic_outcome="skipped_no_client",
            extra=meta,
        )

    key = (settings.openai_api_key or "").strip()

    if not key:
        warnings.append(
            "[semantic] OpenAI API key not configured (OPENAI_API_KEY); semantic extraction skipped."
        )
        return _sparse_response(
            filename=fn,
            raw_text=raw_text,
            warnings=warnings,
            context_echo=context_echo,
            parse_path=parse_path,
            semantic_outcome="skipped_missing_key",
            extra=meta,
        )

    system = PARSE_DOCUMENT_SEMANTIC_SYSTEM_PROMPT
    user_text = (
        f"Filename: {fn}\n\n"
        f"Extract load fields from the following PDF text. If something is unclear, add an entry "
        f"to `warnings` rather than guessing.\n\n"
        f"--- PDF TEXT ---\n{raw_text[:_MAX_USER_TEXT]}\n--- END ---"
    )
    schema = _OPENAI_RESPONSE_JSON_SCHEMA
    schema_name = _PARSE_DOCUMENT_SEMANTIC_SCHEMA_NAME

    try:
        api_response = await openai_chat_json_schema(
            api_key=key,
            model=model,
            system=system,
            user_text=user_text,
            schema=schema,
            schema_name=schema_name,
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)[:400]
        warnings.append(f"[semantic] OpenAI call failed: {msg}")
        return _merge_public_context(
            LoadDocumentParseResponse(
                document=LoadParseDocumentMeta(filename=fn),
                extracted=LoadParseExtractedFields(),
                raw_text=raw_text,
                warnings=warnings,
                field_confidence={},
                context={},
            ),
            context_echo=context_echo,
            parse_path=parse_path,
            semantic_outcome="openai_error",
            extra={**meta, "provider_status": "error"},
        )

    if not isinstance(api_response, dict):
        warnings.append("[semantic] Invalid injectable return type; expected dict.")
        return _merge_public_context(
            LoadDocumentParseResponse(
                document=LoadParseDocumentMeta(filename=fn),
                extracted=LoadParseExtractedFields(),
                raw_text=raw_text,
                warnings=warnings,
                field_confidence={},
                context={},
            ),
            context_echo=context_echo,
            parse_path=parse_path,
            semantic_outcome="invalid_injectable_return",
            extra=meta,
        )

    if "choices" in api_response:
        warnings.append(
            "[semantic] Raw OpenAI response shape is not supported in this skeleton; "
            "injectable must return a contract-level dict."
        )
        return _merge_public_context(
            LoadDocumentParseResponse(
                document=LoadParseDocumentMeta(filename=fn),
                extracted=LoadParseExtractedFields(),
                raw_text=raw_text,
                warnings=warnings,
                field_confidence={},
                context={},
            ),
            context_echo=context_echo,
            parse_path=parse_path,
            semantic_outcome="unsupported_openai_wire",
            extra=meta,
        )

    try:
        parsed = _injected_dict_to_load_response(
            api_response, server_filename=fn, raw_text=raw_text
        )
    except (ValidationError, ValueError, TypeError) as exc:
        warnings.append(f"[semantic] Failed to validate semantic payload: {exc!s}"[:500])
        return _merge_public_context(
            LoadDocumentParseResponse(
                document=LoadParseDocumentMeta(filename=fn),
                extracted=LoadParseExtractedFields(),
                raw_text=raw_text,
                warnings=warnings,
                field_confidence={},
                context={},
            ),
            context_echo=context_echo,
            parse_path=parse_path,
            semantic_outcome="validation_failed",
            extra=meta,
        )

    inner_ctx = dict(parsed.context) if parsed.context else {}
    merged = parsed.model_copy(
        update={
            "warnings": list(parsed.warnings) + warnings,
            "context": inner_ctx,
        }
    )
    return _merge_public_context(
        merged,
        context_echo=context_echo,
        parse_path=parse_path,
        semantic_outcome="success",
        extra=meta,
    )
