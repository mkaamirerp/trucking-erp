"""HTTP helper for POST /loads/parse-document.

This module is not a second parser. It validates caller context and forwards bytes to the
single product entrypoint ``parse_pdf_bytes_to_load_document_response``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_product_parser import parse_pdf_bytes_to_load_document_response


async def parse_load_workspace_document_orchestrated(
    pdf_bytes: bytes,
    *,
    filename: str,
    email_thread_id: int | None = None,
    load_id: int | None = None,
    openai_chat_json_schema: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    tenant_id: int | None = None,
    db: AsyncSession | None = None,
    continue_anyway: bool = False,
    incoming_broker_id: int | None = None,
) -> LoadDocumentParseResponse:
    """Parse a PDF for a new load form. Does not write a load."""
    _ = email_thread_id, load_id
    fn = (filename or "upload.pdf")[:512]

    if tenant_id is None or db is None:
        raise RuntimeError("tenant_id and db are required for parse-document")

    out = await parse_pdf_bytes_to_load_document_response(
        db,
        tenant_id=tenant_id,
        pdf_bytes=pdf_bytes,
        filename=fn,
        openai_chat_json_schema=openai_chat_json_schema,
        continue_anyway=continue_anyway,
        exclude_load_id=load_id,
        incoming_broker_id=incoming_broker_id,
    )
    ctx = dict(out.context or {})
    if email_thread_id is not None:
        ctx["email_thread_id"] = int(email_thread_id)
    if load_id is not None:
        ctx["load_id"] = int(load_id)
    if ctx != out.context:
        out = out.model_copy(update={"context": ctx})
    return out


class LoadReparseError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def _broker_aliases(db: AsyncSession, tenant_id: int, saved: dict, revised: dict) -> list[str]:
    """Names and aliases already stored for one broker. A lookup failure does not invent a match."""
    try:
        from sqlalchemy import select

        from app.models.broker import BrokerAlias
        from app.services.load_document_parse_rate_con import _find_broker_by_name_or_alias

        saved_name = ((saved.get("extracted") or {}) if isinstance(saved.get("extracted"), dict) else {}).get("broker_name_snapshot")
        revised_name = ((revised.get("extracted") or {}) if isinstance(revised.get("extracted"), dict) else {}).get(
            "broker_name_snapshot"
        )
        found = []
        for name in (saved_name, revised_name):
            if not str(name or "").strip():
                continue
            broker = await _find_broker_by_name_or_alias(db, tenant_id=tenant_id, name=str(name))
            if broker is not None:
                found.append(broker)
        if len({int(broker.id) for broker in found}) != 1:
            return []
        broker = found[0]
        labels = [broker.name, getattr(broker, "legal_name", None), getattr(broker, "display_name", None)]
        alias_rows = (
            await db.execute(
                select(BrokerAlias).where(
                    BrokerAlias.tenant_id == tenant_id,
                    BrokerAlias.broker_id == broker.id,
                    BrokerAlias.is_active.is_(True),
                )
            )
        ).scalars().all()
        labels.extend(row.alias for row in alias_rows)
        return [str(label) for label in labels if str(label or "").strip()]
    except Exception:
        return []


async def parse_attached_rate_confirmation_reference(
    db: AsyncSession,
    *,
    tenant_id: int,
    load_id: int,
    revision: int,
    tenant_slug: str,
    openai_chat_json_schema: Callable[..., Awaitable[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Parse one attached revised RC with the first parser only. Writes nothing."""
    from sqlalchemy import select

    from app.models.load_commercial_evidence import LoadCommercialEvidence
    from app.services.load_parser_duplicate_precheck import DuplicatePrecheckUnavailable
    from app.services.loads import read_revised_rate_confirmation_pdf_bytes
    from app.services.load_workspace_draft_document import (
        build_parse_reference_field_rows,
        classify_load_pdf_reuse,
        parse_json_for_compare,
        reparse_document_block_reason,
    )

    if revision < 1:
        raise LoadReparseError(422, "Select a revised rate confirmation to parse.")

    evidence = await db.scalar(
        select(LoadCommercialEvidence).where(
            LoadCommercialEvidence.tenant_id == tenant_id,
            LoadCommercialEvidence.load_id == load_id,
            LoadCommercialEvidence.evidence_kind == "rate_confirmation_pdf",
        )
    )
    if evidence is None or not isinstance(evidence.accepted_parse_json, dict):
        raise LoadReparseError(422, "This load has no rate confirmation evidence to parse.")

    try:
        filename, pdf_bytes = await read_revised_rate_confirmation_pdf_bytes(
            db, tenant_id, load_id, revision=revision, tenant_slug=tenant_slug
        )
    except Exception as exc:
        raise LoadReparseError(404, "That revised PDF could not be read.") from exc

    reuse_status = classify_load_pdf_reuse(evidence, pdf_bytes)
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    from app.services.load_document_parse_semantic_llm import LoadDocumentParseProviderError

    try:
        parsed = await parse_load_workspace_document_orchestrated(
            pdf_bytes,
            filename=filename or f"revised-rc-{revision}.pdf",
            tenant_id=tenant_id,
            db=db,
            load_id=load_id,
            openai_chat_json_schema=openai_chat_json_schema,
        )
    except LoadDocumentParseProviderError as exc:
        raise LoadReparseError(503, exc.user_message) from exc

    if (parsed.context or {}).get("semantic_outcome") == "blocked_duplicate_review":
        raise LoadReparseError(409, "This PDF matches a different load. Nothing was changed.")

    revised_document = parsed.model_dump(mode="json")
    revised_doc = parse_json_for_compare(revised_document)
    block_reason = reparse_document_block_reason(revised_doc)
    if block_reason:
        raise LoadReparseError(422, block_reason)

    saved = parse_json_for_compare(evidence.accepted_parse_json)
    field_rows = build_parse_reference_field_rows(saved, revised_doc)
    warnings: list[str] = []
    try:
        from app.services.load_workspace_draft_document import assess_same_load

        identity = assess_same_load(
            saved,
            revised_doc,
            broker_aliases=await _broker_aliases(db, tenant_id, saved, revised_doc),
        )
        if identity.get("verdict") == "blocked":
            raise LoadReparseError(422, str(identity.get("summary") or "This document does not match this load."))
        if identity.get("verdict") == "needs_confirmation":
            summary = str(identity.get("summary") or "").strip()
            if summary:
                warnings.append(summary)
            for reason in identity.get("reasons") or []:
                text = str(reason or "").strip()
                if text and text not in warnings:
                    warnings.append(text)
    except LoadReparseError:
        raise
    except DuplicatePrecheckUnavailable:
        warnings.append("Shipment identity check was unavailable; review extracted values carefully.")

    return {
        "revision": int(revision),
        "filename": filename or f"revised-rc-{revision}.pdf",
        "pdf_sha256": pdf_sha256,
        "pdf_reuse_status": reuse_status,
        "parse": parsed,
        "field_rows": field_rows,
        "warnings": warnings,
    }
