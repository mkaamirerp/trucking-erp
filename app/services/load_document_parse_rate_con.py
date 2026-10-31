"""Production Rate Confirmation parse path (shared acquisition + v2 handoff + mechanical validation).

Wired as the product ``parse_pdf_bytes_to_load_document_response`` implementation.
Does **not** embed PRODUCT_PARSE_DIAGNOSTICS or run semantic guardrail repairs.

Digital PDFs: original PDF bytes + v2 JSON rules/schema → OpenAI. Locally extracted page
text is kept for ``raw_text`` / mechanical validation but is **not** duplicated into the
OpenAI user-message handoff when PDF bytes are attached.

Image-only/scanned PDFs: OCR pages, then OCR text in ``document.pages`` + the same JSON
rules/schema → OpenAI (no original PDF attachment). Mixed PDFs remain blocked.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.broker import Broker, BrokerAlias
from app.schemas.load_document_parse import (
    LoadDocumentParseResponse,
    LoadParseDocumentMeta,
    LoadParseExtractedFields,
    postgres_safe_load_document_parse_response,
)
from app.schemas.load_document_parse_semantic import ParseDocumentSemanticModelOutput
from app.services.load_document_parse_openai import parse_document_openai_chat_json_schema
from app.services.load_document_parse_semantic_llm import (
    default_load_parser_semantic_client,
    load_parser_semantic_api_key,
    load_parser_semantic_configured,
    load_parser_semantic_model,
    load_parser_semantic_provider,
)
from app.services.load_parser_mechanical_validation import apply_load_parser_mechanical_validation
from app.services.load_parser_semantic_to_product import map_semantic_extracted_to_product
from app.services.load_parser_openai_handoff_v2 import (
    build_load_rate_con_openai_handoff_v2_payload,
    build_v2_openai_system_prompt,
    build_v2_openai_user_message,
)
from app.services.load_parser_pdf_acquisition import PDF_SCANNED, acquire_load_parser_pdf_pages
from app.services.load_parser_pdf_ocr import ocr_load_parser_pdf_pages
from app.services.load_parser_pdf_safety import validate_load_parser_pdf
from app.services.load_parser_duplicate_precheck import find_exact_pdf_duplicate_candidates
from app.services.load_rate_confirmation_duplicate import (
    apply_broker_reference_duplicate_to_parse_context,
    evaluate_broker_reference_duplicate,
)
from app.services.load_parser_tenant_identity_exclusion import (
    get_load_parser_tenant_identity_exclusion,
)
from app.utils.broker_identity import normalize_alias

logger = logging.getLogger(__name__)

_PARSE_PATH = "load_rate_con_v2"
_SCHEMA_NAME = "load_document_parse_guarded_truckerjson_v1"
_SKIPPED_WARNING = "[rate_con_v2] Semantic LLM not configured; extraction skipped."
_OCR_REQUIRED_WARNING = (
    "ocr_required: mixed digital/scanned PDF; OCR fallback applies only to "
    "image-only PDFs with no usable embedded text — semantic parse was not attempted."
)
_OCR_FAILED_WARNING = "ocr_failed: image-only PDF could not be OCR'd — semantic parse was not attempted."
_EMPTY_EXCLUSION: dict[str, Any] = {
    "names": [],
    "mc_numbers": [],
    "usdot_numbers": [],
    "phones": [],
    "emails": [],
    "email_domains": [],
    "addresses": [],
}


async def parse_pdf_bytes_to_load_document_response(
    db: AsyncSession,
    *,
    tenant_id: int,
    pdf_bytes: bytes,
    filename: str,
    openai_chat_json_schema: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    forensic_enabled: bool = False,
    continue_anyway: bool = False,
    exclude_load_id: int | None = None,
    incoming_broker_id: int | None = None,
    attach_pdf: bool = True,
) -> LoadDocumentParseResponse:
    """Parse a rate-confirmation PDF into ``LoadDocumentParseResponse`` (New Load hydration).

    ``attach_pdf=False`` (re-parse) sends the AI the extracted page text only, never the PDF file.
    """
    _ = forensic_enabled, continue_anyway
    fn = (filename or "upload.pdf")[:512]
    parse_started = time.perf_counter()

    validate_load_parser_pdf(pdf_bytes)
    acquisition = acquire_load_parser_pdf_pages(pdf_bytes)
    page_objs = list(acquisition.get("pages") or [])
    usable_texts = [
        str(p.get("text") or "")
        for p in page_objs
        if isinstance(p, dict) and not p.get("requires_ocr")
    ]
    handoff_pages = [
        {"page_number": int(p.get("page_number") or i + 1), "text": str(p.get("text") or "")}
        for i, p in enumerate(page_objs)
        if isinstance(p, dict) and not p.get("requires_ocr")
    ]
    raw_text = "\n".join(usable_texts)
    base_warnings = list(acquisition.get("warnings") or [])

    if acquisition.get("requires_ocr") and acquisition.get("pdf_type") != PDF_SCANNED:
        return LoadDocumentParseResponse(
            document=LoadParseDocumentMeta(filename=fn),
            extracted=LoadParseExtractedFields(),
            raw_text=raw_text,
            warnings=base_warnings + [_OCR_REQUIRED_WARNING],
            field_confidence={},
            context={
                "parse_path": _PARSE_PATH,
                "requires_ocr": True,
                "pdf_type": acquisition.get("pdf_type"),
                "page_count": acquisition.get("page_count"),
                "ocr_pages": [
                    int(p.get("page_number") or 0)
                    for p in page_objs
                    if isinstance(p, dict) and p.get("requires_ocr")
                ],
                "semantic_outcome": "blocked_ocr_required",
            },
        )

    if acquisition.get("pdf_type") == PDF_SCANNED:
        return await _parse_scanned_image_with_ocr(
            db,
            tenant_id=int(tenant_id),
            pdf_bytes=pdf_bytes,
            filename=fn,
            acquisition=acquisition,
            base_warnings=base_warnings,
            openai_chat_json_schema=openai_chat_json_schema,
            exclude_load_id=exclude_load_id,
            incoming_broker_id=incoming_broker_id,
        )

    duplicates = await find_exact_pdf_duplicate_candidates(
        db,
        tenant_id=int(tenant_id),
        pdf_bytes=pdf_bytes,
        exclude_load_id=exclude_load_id,
    )
    if duplicates:
        return _duplicate_review_response(
            filename=fn,
            raw_text=raw_text,
            acquisition=acquisition,
            warnings=base_warnings,
            candidates=duplicates,
            match_basis="exact_pdf_sha256",
        )

    exclusion, excl_warnings = await _load_tenant_identity_exclusion(
        tenant_db=db, tenant_id=int(tenant_id)
    )
    base_warnings.extend(excl_warnings)

    page_count = int(acquisition.get("page_count") or len(handoff_pages) or 0)
    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=_strip_exclusion_internal_keys(exclusion),
        pages=handoff_pages,
        filename=fn,
        extraction_method="product_pdf_text",
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
        acquisition_method=str(acquisition.get("pdf_type") or "digital_text"),
        include_page_text_in_ai_handoff=not attach_pdf,
        page_count=page_count,
    )

    if openai_chat_json_schema is None and not load_parser_semantic_configured():
        return LoadDocumentParseResponse(
            document=LoadParseDocumentMeta(filename=fn),
            extracted=LoadParseExtractedFields(),
            raw_text=raw_text,
            warnings=base_warnings + [_SKIPPED_WARNING],
            field_confidence={},
            context={
                "parse_path": _PARSE_PATH,
                "requires_ocr": False,
                "pdf_type": acquisition.get("pdf_type"),
                "page_count": acquisition.get("page_count"),
                "semantic_outcome": "skipped_missing_client",
                "llm_provider": load_parser_semantic_provider(),
            },
        )

    model = load_parser_semantic_model()
    reasoning_effort = _load_parser_reasoning_effort()
    client = openai_chat_json_schema or default_load_parser_semantic_client()
    api_key = load_parser_semantic_api_key()
    ai_started = time.perf_counter()
    ai_payload = await client(
        api_key=api_key,
        model=model,
        system=build_v2_openai_system_prompt(pdf_bytes_attached=attach_pdf),
        user_text=build_v2_openai_user_message(handoff, pdf_bytes_attached=attach_pdf),
        schema=ParseDocumentSemanticModelOutput.model_json_schema(),
        schema_name=_SCHEMA_NAME,
        input_file_bytes=pdf_bytes if attach_pdf else None,
        input_filename=fn,
        reasoning_effort=reasoning_effort,
    )
    ai_ms = int((time.perf_counter() - ai_started) * 1000)

    response = _map_semantic_payload_to_response(
        filename=fn,
        raw_text=raw_text,
        ai_payload=ai_payload,
        acquisition=acquisition,
        extra_warnings=base_warnings,
    )
    response = apply_load_parser_mechanical_validation(
        response,
        tenant_identity_exclusion=_exclusion_for_mechanical_validation(exclusion),
        page_texts=[str(p.get("text") or "") for p in handoff_pages],
    )
    response = await _canonicalize_broker_snapshot_from_tenant_registry(
        db, tenant_id=int(tenant_id), response=response
    )
    total_ms = int((time.perf_counter() - parse_started) * 1000)
    payload = response.model_dump(mode="json")
    ctx = dict(payload.get("context") or {})
    ctx["openai_ms"] = ai_ms
    ctx["semantic_ms"] = ai_ms
    ctx["server_parse_ms"] = total_ms
    if reasoning_effort:
        ctx["reasoning_effort"] = reasoning_effort
    ctx["llm_provider"] = load_parser_semantic_provider()
    ctx["llm_model"] = model
    payload["context"] = ctx
    response = LoadDocumentParseResponse.model_validate(payload)
    _log_parse_timing(
        filename=fn,
        pdf_type=str(acquisition.get("pdf_type") or ""),
        page_count=int(acquisition.get("page_count") or 0),
        model=model,
        openai_ms=ai_ms,
        total_ms=total_ms,
        semantic_input="pdf_bytes",
    )
    response = await _apply_broker_reference_duplicate_after_parse(
        db,
        tenant_id=int(tenant_id),
        response=response,
        filename=fn,
        raw_text=raw_text,
        acquisition=acquisition,
        warnings=base_warnings,
        exclude_load_id=exclude_load_id,
        incoming_broker_id=incoming_broker_id,
    )
    return postgres_safe_load_document_parse_response(response)


async def _parse_scanned_image_with_ocr(
    db: AsyncSession,
    *,
    tenant_id: int,
    pdf_bytes: bytes,
    filename: str,
    acquisition: dict[str, Any],
    base_warnings: list[str],
    openai_chat_json_schema: Callable[..., Awaitable[dict[str, Any]]] | None,
    exclude_load_id: int | None,
    incoming_broker_id: int | None,
) -> LoadDocumentParseResponse:
    """Image-only PDF: OCR pages, then same v2 JSON rules/schema → OpenAI (no PDF bytes)."""
    parse_started = time.perf_counter()
    ocr_pages, ocr_warnings = ocr_load_parser_pdf_pages(pdf_bytes)
    warnings = list(base_warnings) + list(ocr_warnings)
    if not ocr_pages:
        return LoadDocumentParseResponse(
            document=LoadParseDocumentMeta(filename=filename),
            extracted=LoadParseExtractedFields(),
            raw_text="",
            warnings=warnings + [_OCR_FAILED_WARNING],
            field_confidence={},
            context={
                "parse_path": _PARSE_PATH,
                "requires_ocr": True,
                "pdf_type": acquisition.get("pdf_type"),
                "page_count": acquisition.get("page_count"),
                "ocr_engine": "tesseract+pdftoppm",
                "semantic_outcome": "ocr_failed",
            },
        )

    handoff_pages = [
        {
            "page_number": int(p.get("page_number") or i + 1),
            "text": str(p.get("text") or ""),
        }
        for i, p in enumerate(ocr_pages)
    ]
    raw_text = "\n".join(str(p.get("text") or "") for p in handoff_pages)

    duplicates = await find_exact_pdf_duplicate_candidates(
        db,
        tenant_id=int(tenant_id),
        pdf_bytes=pdf_bytes,
        exclude_load_id=exclude_load_id,
    )
    if duplicates:
        return _duplicate_review_response(
            filename=filename,
            raw_text=raw_text,
            acquisition=acquisition,
            warnings=warnings,
            candidates=duplicates,
            match_basis="exact_pdf_sha256",
        )

    exclusion, excl_warnings = await _load_tenant_identity_exclusion(
        tenant_db=db, tenant_id=int(tenant_id)
    )
    warnings.extend(excl_warnings)

    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=_strip_exclusion_internal_keys(exclusion),
        pages=handoff_pages,
        filename=filename,
        extraction_method="product_pdf_ocr",
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
        acquisition_method="scanned_image_ocr",
    )

    if openai_chat_json_schema is None and not load_parser_semantic_configured():
        return LoadDocumentParseResponse(
            document=LoadParseDocumentMeta(filename=filename),
            extracted=LoadParseExtractedFields(),
            raw_text=raw_text,
            warnings=warnings + [_SKIPPED_WARNING],
            field_confidence={},
            context={
                "parse_path": _PARSE_PATH,
                "requires_ocr": True,
                "pdf_type": acquisition.get("pdf_type"),
                "page_count": acquisition.get("page_count"),
                "ocr_engine": "tesseract+pdftoppm",
                "semantic_outcome": "skipped_missing_client",
                "llm_provider": load_parser_semantic_provider(),
            },
        )

    model = load_parser_semantic_model()
    reasoning_effort = _load_parser_reasoning_effort()
    client = openai_chat_json_schema or default_load_parser_semantic_client()
    api_key = load_parser_semantic_api_key()
    ai_started = time.perf_counter()
    ai_payload = await client(
        api_key=api_key,
        model=model,
        system=build_v2_openai_system_prompt(pdf_bytes_attached=False),
        user_text=build_v2_openai_user_message(handoff, pdf_bytes_attached=False),
        schema=ParseDocumentSemanticModelOutput.model_json_schema(),
        schema_name=_SCHEMA_NAME,
        input_file_bytes=None,
        input_filename=filename,
        reasoning_effort=reasoning_effort,
    )
    ai_ms = int((time.perf_counter() - ai_started) * 1000)

    response = _map_semantic_payload_to_response(
        filename=filename,
        raw_text=raw_text,
        ai_payload=ai_payload,
        acquisition=acquisition,
        extra_warnings=warnings,
    )
    payload = response.model_dump(mode="json")
    context = dict(payload.get("context") or {})
    context["requires_ocr"] = True
    context["ocr_engine"] = "tesseract+pdftoppm"
    context["semantic_input"] = "ocr_text"
    context["openai_ms"] = ai_ms
    context["semantic_ms"] = ai_ms
    context["server_parse_ms"] = int((time.perf_counter() - parse_started) * 1000)
    if reasoning_effort:
        context["reasoning_effort"] = reasoning_effort
    context["llm_provider"] = load_parser_semantic_provider()
    context["llm_model"] = model
    payload["context"] = context
    response = LoadDocumentParseResponse.model_validate(payload)
    response = apply_load_parser_mechanical_validation(
        response,
        tenant_identity_exclusion=_exclusion_for_mechanical_validation(exclusion),
        page_texts=[str(p.get("text") or "") for p in handoff_pages],
    )
    response = await _canonicalize_broker_snapshot_from_tenant_registry(
        db, tenant_id=int(tenant_id), response=response
    )
    _log_parse_timing(
        filename=filename,
        pdf_type=str(acquisition.get("pdf_type") or ""),
        page_count=int(acquisition.get("page_count") or len(handoff_pages)),
        model=model,
        openai_ms=ai_ms,
        total_ms=int((time.perf_counter() - parse_started) * 1000),
        semantic_input="ocr_text",
    )
    response = await _apply_broker_reference_duplicate_after_parse(
        db,
        tenant_id=int(tenant_id),
        response=response,
        filename=filename,
        raw_text=raw_text,
        acquisition=acquisition,
        warnings=warnings,
        exclude_load_id=exclude_load_id,
        incoming_broker_id=incoming_broker_id,
    )
    return postgres_safe_load_document_parse_response(response)


async def _apply_broker_reference_duplicate_after_parse(
    db: AsyncSession,
    *,
    tenant_id: int,
    response: LoadDocumentParseResponse,
    filename: str,
    raw_text: str,
    acquisition: dict[str, Any],
    warnings: list[str],
    exclude_load_id: int | None,
    incoming_broker_id: int | None,
) -> LoadDocumentParseResponse:
    ctx = dict(response.context or {})
    if ctx.get("semantic_outcome") == "blocked_duplicate_review":
        return response
    broker_ref = (response.extracted.broker_load_reference or "").strip()
    if not broker_ref:
        return response
    broker_id = incoming_broker_id
    if broker_id is None:
        name = (response.extracted.broker_name_snapshot or "").strip()
        if name:
            broker = await _find_broker_by_name_or_alias(db, tenant_id=tenant_id, name=name)
            if broker is not None:
                broker_id = int(broker.id)
    severity, candidates = await evaluate_broker_reference_duplicate(
        db,
        tenant_id=tenant_id,
        broker_load_reference=broker_ref,
        broker_id=broker_id,
        exclude_load_id=exclude_load_id,
    )
    if severity is None:
        return response
    if severity == "hard":
        return _duplicate_review_response(
            filename=filename,
            raw_text=raw_text,
            acquisition=acquisition,
            warnings=warnings,
            candidates=candidates,
            match_basis="broker_load_reference",
        )
    merged_warnings = list(response.warnings) + [
        "rate_confirmation_duplicate_warning: another load uses this broker reference number"
    ]
    new_ctx = apply_broker_reference_duplicate_to_parse_context(
        ctx, severity=severity, candidates=candidates
    )
    return response.model_copy(update={"warnings": merged_warnings, "context": new_ctx})


def _duplicate_review_response(
    *,
    filename: str,
    raw_text: str,
    acquisition: dict[str, Any],
    warnings: list[str],
    candidates: list[dict],
    match_basis: str,
) -> LoadDocumentParseResponse:
    """Return a review-only result. No semantic call or fields are generated."""
    from app.services.load_rate_confirmation_duplicate import LOAD_RATE_CONFIRMATION_DUPLICATE

    return postgres_safe_load_document_parse_response(
        LoadDocumentParseResponse(
            document=LoadParseDocumentMeta(filename=filename),
            extracted=LoadParseExtractedFields(),
            raw_text=raw_text,
            warnings=warnings,
            field_confidence={},
            context={
                "parse_path": _PARSE_PATH,
                "pdf_type": acquisition.get("pdf_type"),
                "page_count": acquisition.get("page_count"),
                "semantic_outcome": "blocked_duplicate_review",
                "duplicate_match_basis": match_basis,
                "duplicate_severity": "hard",
                "duplicate_code": LOAD_RATE_CONFIRMATION_DUPLICATE,
                "duplicate_candidates": candidates,
            },
        )
    )


def _load_parser_reasoning_effort() -> str | None:
    raw = (settings.load_parser_reasoning_effort or settings.openai_reasoning_effort or "").strip().lower()
    return raw or None


def _log_parse_timing(
    *,
    filename: str,
    pdf_type: str,
    page_count: int,
    model: str,
    openai_ms: int,
    total_ms: int,
    semantic_input: str,
) -> None:
    logger.info(
        "load_parser_parse_complete filename=%s pdf_type=%s pages=%s model=%s openai_ms=%s total_ms=%s semantic_input=%s",
        filename[:120],
        pdf_type,
        page_count,
        model,
        openai_ms,
        total_ms,
        semantic_input,
    )


def _strip_exclusion_internal_keys(excl: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in excl.items() if not str(k).startswith("_")}


def _exclusion_for_mechanical_validation(excl: dict[str, Any]) -> dict[str, Any] | None:
    """Do not treat failed lookup as a successful empty exclusion set (Issue I21)."""
    if excl.get("_exclusion_lookup_failed"):
        return None
    return _strip_exclusion_internal_keys(excl)


async def _load_tenant_identity_exclusion(
    *,
    tenant_db: AsyncSession,
    tenant_id: int,
) -> tuple[dict[str, Any], list[str]]:
    """Load exclusion from platform DB."""
    try:
        async with AsyncSessionLocal() as platform_db:
            excl = await get_load_parser_tenant_identity_exclusion(
                platform_db, tenant_id=int(tenant_id)
            )
        if not isinstance(excl, dict):
            failed = dict(_EMPTY_EXCLUSION)
            failed["_exclusion_lookup_failed"] = True
            return failed, ["tenant_identity_exclusion_unavailable: invalid shape"]
        if excl.get("_exclusion_lookup_failed"):
            return excl, ["tenant_identity_exclusion_unavailable: tenant_lookup_failed"]
        return excl, []
    except Exception as exc:  # noqa: BLE001 — parse must not hard-fail on exclusion lookup
        failed = dict(_EMPTY_EXCLUSION)
        failed["_exclusion_lookup_failed"] = True
        return failed, [
            f"tenant_identity_exclusion_unavailable: {type(exc).__name__}"
        ]


def _map_semantic_payload_to_response(
    *,
    filename: str,
    raw_text: str,
    ai_payload: dict[str, Any],
    acquisition: dict[str, Any],
    extra_warnings: list[str],
) -> LoadDocumentParseResponse:
    payload = dict(ai_payload or {})
    payload.pop("parse_diagnostics", None)
    doc_type = payload.pop("document_type", None)
    classification_reasoning = payload.pop("classification_reasoning", None)

    context = dict(payload.get("context") or {})
    context.pop("parse_diagnostics", None)
    context["parse_path"] = _PARSE_PATH
    context["requires_ocr"] = False
    context["pdf_type"] = acquisition.get("pdf_type")
    context["page_count"] = acquisition.get("page_count")
    if doc_type is not None:
        context["document_type"] = doc_type
    if classification_reasoning:
        context["classification_reasoning"] = str(classification_reasoning)[:2000]

    doc_meta = payload.get("document") or {"filename": filename[:512]}
    if not isinstance(doc_meta, dict):
        doc_meta = {"filename": filename[:512]}
    product_extracted = map_semantic_extracted_to_product(payload.get("extracted"))
    extracted_dump = _sanitize_extracted_references(product_extracted.model_dump(mode="json"))

    return LoadDocumentParseResponse(
        document=LoadParseDocumentMeta(filename=str(doc_meta.get("filename") or filename)[:512]),
        extracted=LoadParseExtractedFields.model_validate(extracted_dump),
        raw_text=(
            payload["raw_text"] if isinstance(payload.get("raw_text"), str) else raw_text
        ),
        warnings=list(extra_warnings) + list(payload.get("warnings") or []),
        field_confidence=dict(payload.get("field_confidence") or {}),
        context=context,
    )


def _sanitize_extracted_references(extracted: dict[str, Any]) -> dict[str, Any]:
    out = dict(extracted)
    refs = out.get("references")
    if not isinstance(refs, list):
        return out
    clean: list[dict[str, Any]] = []
    for item in refs:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        value = item.get("value")
        if not isinstance(kind, str) or not kind.strip():
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        clean.append({**item, "kind": kind.strip(), "value": value.strip()})
    out["references"] = clean
    return out


async def _canonicalize_broker_snapshot_from_tenant_registry(
    db: AsyncSession,
    *,
    tenant_id: int,
    response: LoadDocumentParseResponse,
) -> LoadDocumentParseResponse:
    """If broker_name matches tenant broker registry, prefer display_name (hydration only)."""
    name = (response.extracted.broker_name_snapshot or "").strip()
    if not name:
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
    warnings.append(
        "[rate_con_v2] broker_name_snapshot canonicalized from tenant broker registry."
    )
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
        ).all()
    )
    for alias, broker in aliases:
        if normalize_alias(alias.alias or "") == norm:
            return broker
    return None
