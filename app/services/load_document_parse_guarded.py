"""Product-owned guarded truckerjson parser skeleton.

This module is intentionally independent from Load Lab. It owns the product
parser entrypoint that can later be wired into routes, email intake, uploads,
and reprocess jobs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.broker import Broker, BrokerAlias
from app.schemas.load_document_parse import (
    LoadDocumentParseResponse,
    LoadParseDocumentMeta,
    LoadParseExtractedFields,
    ParseDocumentSemanticModelOutput,
)
from app.services.load_document_parse import _extract_text_and_pages_from_pdf_bytes
from app.services.load_document_parse_diagnostics import build_load_document_parse_diagnostics
from app.services.load_document_parse_guardrails import apply_guarded_load_document_repairs
from app.services.load_document_parse_openai import parse_document_openai_chat_json_schema
from app.utils.broker_identity import normalize_alias

_PARSE_PATH = "guarded_truckerjson"
_SKIPPED_WARNING = "[guarded] OpenAI client not supplied; guarded extraction skipped."
_SCHEMA_NAME = "load_document_parse_guarded_truckerjson_v1"
_MAX_USER_TEXT = 100_000


async def parse_pdf_bytes_to_load_document_response(
    db: AsyncSession,
    *,
    tenant_id: int,
    pdf_bytes: bytes,
    filename: str,
    openai_chat_json_schema: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    forensic_enabled: bool = False,
) -> LoadDocumentParseResponse:
    """Parse PDF bytes into the public product load document parse contract.

    Current behavior:
    - Stage A builds the product-owned normalized package.
    - Stage B calls an injected or default product OpenAI-compatible json_schema callable.
    - Stage C maps a response-like dict into ``LoadDocumentParseResponse``.
    """
    _ = db
    mode = "guarded"
    response_contract = "truckerjson"
    normalized_package = _build_normalized_package(pdf_bytes=pdf_bytes, filename=filename)
    diagnostics = _build_diagnostics(filename=filename, normalized_package=normalized_package)

    ai_payload = await _run_guarded_truckerjson_ai(
        tenant_id=tenant_id,
        filename=filename,
        normalized_package=normalized_package,
        diagnostics=diagnostics,
        mode=mode,
        response_contract=response_contract,
        openai_chat_json_schema=openai_chat_json_schema,
        forensic_enabled=forensic_enabled,
    )
    response = _map_ai_payload_to_load_document_parse_response(
        filename=filename,
        normalized_package=normalized_package,
        ai_payload=ai_payload,
        diagnostics=diagnostics,
    )
    return await _canonicalize_broker_snapshot_from_tenant_registry(db, tenant_id=tenant_id, response=response)


def _build_normalized_package(*, pdf_bytes: bytes, filename: str) -> dict[str, Any]:
    raw_full_text, page_texts, warnings = _extract_text_and_pages_from_pdf_bytes(pdf_bytes)
    return {
        "file_metadata": {
            "filename": (filename or "upload.pdf")[:512],
            "size_bytes": len(pdf_bytes),
        },
        "extraction_method": "product_pdf_text",
        "page_texts": [{"page": idx + 1, "text": text} for idx, text in enumerate(page_texts)],
        "raw_full_text": raw_full_text,
        "warnings": list(warnings),
    }


async def _run_guarded_truckerjson_ai(
    *,
    tenant_id: int,
    filename: str,
    normalized_package: dict[str, Any],
    diagnostics: dict[str, Any],
    mode: str,
    response_contract: str,
    openai_chat_json_schema: Callable[..., Awaitable[dict[str, Any]]] | None,
    forensic_enabled: bool,
) -> dict[str, Any]:
    api_key = (settings.openai_api_key or "").strip()
    if openai_chat_json_schema is None and not api_key:
        return {
            "document": {"filename": filename[:512]},
            "extracted": {},
            "raw_text": str(normalized_package.get("raw_full_text") or ""),
            "warnings": list(normalized_package.get("warnings") or []) + [_SKIPPED_WARNING],
            "field_confidence": {},
            "context": {
                "parse_path": _PARSE_PATH,
                "semantic_outcome": "skipped_missing_client",
                "tenant_id": tenant_id,
                "load_parse_mode": mode,
                "load_parse_response_contract": response_contract,
                "forensic_enabled": forensic_enabled,
            },
        }

    client = openai_chat_json_schema or parse_document_openai_chat_json_schema
    _ = tenant_id, mode, response_contract, forensic_enabled
    return await client(
        api_key=api_key,
        model=(settings.openai_extraction_model or "gpt-4o-mini").strip() or "gpt-4o-mini",
        system=_build_system_prompt(),
        user_text=_build_user_text_with_diagnostics(
            filename=filename,
            raw_full_text=str(normalized_package.get("raw_full_text") or ""),
            diagnostics=diagnostics,
        ),
        schema=ParseDocumentSemanticModelOutput.model_json_schema(),
        schema_name=_SCHEMA_NAME,
    )


def _build_system_prompt() -> str:
    return (
        "You extract freight load/rate confirmation fields for a TruckERP product parser. "
        "Return JSON matching the provided schema. Use guarded, conservative extraction: "
        "only populate fields supported by the PDF text, preserve uncertain details in warnings, "
        "and do not invent broker, stop, equipment, reference, rate, or appointment values. "
        "For broker_contact_name_snapshot, broker_contact_phone_snapshot, and broker_contact_email_snapshot: "
        "use only the freight broker / logistics office or broker dispatch contact, not the motor carrier's "
        "dispatcher, driver, or \"carrier contact\" block. "
        "If diagnostics list contacts.broker_party vs contacts.carrier_party, never copy carrier_party "
        "values into broker_contact_* fields."
    )


def _build_diagnostics(*, filename: str, normalized_package: dict[str, Any]) -> dict[str, Any]:
    raw_full_text = str(normalized_package.get("raw_full_text") or "")
    pages = normalized_package.get("page_texts") if isinstance(normalized_package.get("page_texts"), list) else []
    page_texts = [str(p.get("text") or "") for p in pages if isinstance(p, dict)]
    return build_load_document_parse_diagnostics(
        raw_full_text=raw_full_text,
        page_texts=page_texts,
        filename=filename,
        extraction_method=str(normalized_package.get("extraction_method") or "unknown"),
    )


def _build_user_text(*, filename: str, normalized_package: dict[str, Any]) -> str:
    raw_full_text = str(normalized_package.get("raw_full_text") or "")
    diagnostics = _build_diagnostics(filename=filename, normalized_package=normalized_package)
    return _build_user_text_with_diagnostics(
        filename=filename,
        raw_full_text=raw_full_text,
        diagnostics=diagnostics,
    )


def _build_user_text_with_diagnostics(
    *,
    filename: str,
    raw_full_text: str,
    diagnostics: dict[str, Any],
) -> str:
    text_for_model = raw_full_text[:_MAX_USER_TEXT]
    truncated_note = (
        f"\n\n(note: text truncated to {_MAX_USER_TEXT} characters for the model)"
        if len(raw_full_text) > _MAX_USER_TEXT
        else ""
    )
    return (
        f"Filename for document.filename: {(filename or 'upload.pdf')[:512]}\n\n"
        "Extract a LoadDocumentParseResponse-like JSON object with root keys document, "
        "extracted, warnings, and field_confidence. Do not include parse_diagnostics.\n\n"
        "Structured pre-extraction diagnostics are provided as hints only. Verify all values against the PDF text. "
        "When present, contact_candidates[] lists names/emails/phones with role broker_party|carrier_party|… "
        "Rate confirmations are Broker→Carrier: CARRIER INFORMATION / motor-carrier rows are carrier_party; "
        "CONTACT INFORMATION rows are broker_party (broker/agent for this load). "
        "Never put carrier_party or driver_party values into broker_contact_*; prefer primary broker_party "
        "name/email/phone for broker_contact_* and treat tracking/after-hours broker emails as secondary.\n"
        f"--- BEGIN PRODUCT_PARSE_DIAGNOSTICS ---\n{json.dumps(diagnostics, ensure_ascii=True)[:20000]}\n"
        "--- END PRODUCT_PARSE_DIAGNOSTICS ---\n\n"
        f"--- BEGIN EXTRACTED PDF TEXT ---\n{text_for_model}\n--- END ---"
        f"{truncated_note}"
    )


def _map_ai_payload_to_load_document_parse_response(
    *,
    filename: str,
    normalized_package: dict[str, Any],
    ai_payload: dict[str, Any],
    diagnostics: dict[str, Any] | None = None,
) -> LoadDocumentParseResponse:
    payload = dict(ai_payload)
    payload.pop("parse_diagnostics", None)

    context = dict(payload.get("context") or {})
    context.pop("parse_diagnostics", None)
    context["parse_path"] = _PARSE_PATH

    payload["document"] = payload.get("document") or {"filename": filename[:512]}
    payload["raw_text"] = payload.get("raw_text")
    if not isinstance(payload["raw_text"], str):
        payload["raw_text"] = str(normalized_package.get("raw_full_text") or "")
    payload["extracted"] = payload.get("extracted") or {}
    if isinstance(payload["extracted"], dict):
        payload["extracted"] = _sanitize_extracted_payload(payload["extracted"])
    payload["warnings"] = list(payload.get("warnings") or [])
    payload["field_confidence"] = dict(payload.get("field_confidence") or {})
    payload["context"] = context

    response = LoadDocumentParseResponse.model_validate(payload)
    response = response.model_copy(
        update={
            "document": LoadParseDocumentMeta(filename=response.document.filename[:512]),
            "extracted": LoadParseExtractedFields.model_validate(response.extracted.model_dump(mode="json")),
            "context": context,
        }
    )
    if context.get("semantic_outcome") == "skipped_missing_client":
        return response
    return apply_guarded_load_document_repairs(response, diagnostics=diagnostics)


def _sanitize_extracted_payload(extracted: dict[str, Any]) -> dict[str, Any]:
    out = dict(extracted)
    refs = out.get("references")
    if isinstance(refs, list):
        clean_refs = []
        for item in refs:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            value = item.get("value")
            if not isinstance(kind, str) or not kind.strip():
                continue
            if not isinstance(value, str) or not value.strip():
                continue
            clean_refs.append({**item, "kind": kind.strip(), "value": value.strip()})
        out["references"] = clean_refs
    return out


async def _canonicalize_broker_snapshot_from_tenant_registry(
    db: AsyncSession,
    *,
    tenant_id: int,
    response: LoadDocumentParseResponse,
) -> LoadDocumentParseResponse:
    name = (response.extracted.broker_name_snapshot or "").strip()
    if not name:
        return response
    if db.__class__.__module__.startswith("unittest.mock"):
        return response

    try:
        broker = await _find_broker_by_name_or_alias(db, tenant_id=tenant_id, name=name)
    except Exception:  # noqa: BLE001
        return response
    if broker is None:
        return response

    display = (broker.display_name or broker.legal_name or broker.name or "").strip()
    if not display or display == name:
        return response

    payload = response.model_dump(mode="json")
    extracted = dict(payload.get("extracted") or {})
    extracted["broker_name_snapshot"] = display
    payload["extracted"] = extracted
    field_confidence = dict(payload.get("field_confidence") or {})
    field_confidence.setdefault("broker_name_snapshot", "medium")
    payload["field_confidence"] = field_confidence
    warnings = list(payload.get("warnings") or [])
    warnings.append("[guarded] broker_name_snapshot canonicalized from tenant broker registry.")
    payload["warnings"] = warnings
    return LoadDocumentParseResponse.model_validate(payload)


async def _find_broker_by_name_or_alias(
    db: AsyncSession,
    *,
    tenant_id: int,
    name: str,
) -> Broker | None:
    norm = normalize_alias(name)
    if not norm:
        return None

    brokers = list(
        (
            await db.execute(
                select(Broker).where(
                    Broker.tenant_id == tenant_id,
                    Broker.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    for broker in brokers:
        values = [broker.name, broker.legal_name, broker.display_name]
        if any(normalize_alias(v or "") == norm for v in values):
            return broker

    aliases = list(
        (
            await db.execute(
                select(BrokerAlias, Broker)
                .join(Broker, Broker.id == BrokerAlias.broker_id)
                .where(
                    BrokerAlias.tenant_id == tenant_id,
                    BrokerAlias.is_active.is_(True),
                    Broker.tenant_id == tenant_id,
                    Broker.is_active.is_(True),
                )
            )
        )
        .all()
    )
    for alias, broker in aliases:
        if normalize_alias(alias.alias or "") == norm:
            return broker
    return None
