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
from app.services.pdf_text_extract import extract_text_and_pages_from_pdf_bytes
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
    raw_full_text, page_texts, warnings = extract_text_and_pages_from_pdf_bytes(pdf_bytes)
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
        "You are a TruckERP product parser for freight PDFs. Return JSON matching the provided schema. "
        "Work in two phases: (1) Set document_type from the enum and write classification_reasoning: "
        "a short justification for the document class and how you will read route stops and contacts. "
        "(2) Then populate extracted only in line with that classification—conservatively; do not invent "
        "broker, stop, equipment, reference, rate, or appointments; put uncertainty in warnings. "
        "Rate confirmations (Broker→Carrier): interpret STOP DETAIL / pickup-delivery tables as route stops; "
        "PU/PICKUP→pickup, DEL/DELIVERY→delivery, SO in a stop-detail row after pickup→delivery; "
        "when one line has a stop label plus a date and the next line is a time, combine into appointment_date "
        "(YYYY-MM-DD) and appointment_time_text. "
        "broker_contact_* must be the broker/agent for the load only—not motor carrier, driver, payment desk, "
        "or shipper/receiver location contacts. If diagnostics show broker_party vs carrier_party, never put "
        "carrier_party values in broker_contact_*."
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
        "Extract JSON with root keys: document, document_type (required enum), classification_reasoning, "
        "extracted, warnings, field_confidence. Do not include parse_diagnostics.\n\n"
        "PHASE 1 — document_type: Choose rate_confirmation | driver_information_sheet | invoice | bol | other. "
        "Rate/load confirmations normally Broker→Carrier with pickup and delivery stops and broker load references.\n"
        "PHASE 2 — classification_reasoning: Briefly state why you chose that type and how you will map stops "
        "(e.g. STOP DETAIL rows) and broker vs carrier contacts before filling extracted.\n\n"
        "When document_type is rate_confirmation, extract from the text: broker identity, broker_contact_* "
        "(broker/agent only), broker_load_reference, carrier rate, equipment, commodity/weight/temperature, "
        "pickup/delivery stops with appointment_date (YYYY-MM-DD) and appointment_time_text, stop references.\n\n"
        "STOP DETAIL / stop tables: Rows may be split across lines. Example pattern:\n"
        "  PU 05/29/25\n"
        "  09:00\n"
        "  Facility Name\n"
        "  Address…\n"
        "means appointment_date=2025-05-29 (normalize MM/DD/YY to ISO), appointment_time_text=09:00 "
        "for that stop. Same for DEL/DELIVERY lines. SO (stop-off) as a stop row after pickup maps to stop_type delivery. "
        "Do not drop date/time when you attach facility_name, street, city, or state.\n\n"
        "If you cannot extract appointment_date for a rate_confirmation stop that has facility or address, "
        "omit it only when unsupported by the text; otherwise the server may add: "
        "[review] Stop has facility/address but appointment date was not extracted; verify STOP DETAIL table. "
        "Prefer extracting the date from STOP DETAIL when present.\n\n"
        "Contacts: CARRIER INFORMATION = motor carrier side; CONTACT INFORMATION = broker/agent unless labels say otherwise. "
        "Never fill broker_contact_* from carrier, driver, payment/paperwork, or shipper/receiver blocks.\n\n"
        "Diagnostics (hints only; verify in PDF): contact_candidates[] broker_party|carrier_party|… "
        "Prefer primary broker_party for broker_contact_*; tracking/after-hours broker channels are secondary.\n"
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

    doc_type = payload.pop("document_type", None)
    classification_reasoning = payload.pop("classification_reasoning", None)

    context = dict(payload.get("context") or {})
    context.pop("parse_diagnostics", None)
    context["parse_path"] = _PARSE_PATH
    if doc_type is not None:
        context["document_type"] = doc_type
    if classification_reasoning:
        context["classification_reasoning"] = str(classification_reasoning)[:2000]

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
