"""HTTP helper for POST /loads/parse-document.

This module is not a second parser. It validates caller context and forwards bytes to the
single product entrypoint ``parse_pdf_bytes_to_load_document_response``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_product_parser import parse_pdf_bytes_to_load_document_response

logger = logging.getLogger(__name__)


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


_REPARSE_TEXT_DIFF_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "field": {"type": "string"},
                    "current_value": {},
                    "revised_value": {},
                    "label": {"type": "string"},
                },
                "required": ["field", "current_value", "revised_value"],
            },
        }
    },
    "required": ["changes"],
}

_REPARSE_TEXT_DIFF_INSTRUCTIONS = (
    "You compare saved verified load JSON against new rate-confirmation PDF text. "
    "Return ONLY fields whose value in the PDF text differs from the saved JSON. "
    "Use JSON field paths exactly (e.g. rate, miles, broker_load_reference, stops[0].city). "
    "current_value must copy the saved JSON value. revised_value must copy the value read from the PDF text. "
    "Do not propose customer_rate. Do not invent fields. "
    "Formatting-only differences (FTL vs Full Truckload, pickup vs PICKUP, equivalent money) are NOT changes. "
    "If nothing meaningful changed, return an empty changes array."
)


def canonical_reparse_document(document: dict) -> str:
    """Stable JSON for the Save token. Key order and client reserialization do not matter."""
    round_tripped = json.loads(json.dumps(document, default=str, ensure_ascii=False))
    return json.dumps(round_tripped, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _reparse_signing_key() -> bytes:
    from app.core.config import settings

    secret = (settings.jwt_secret or "").strip()
    if not secret:
        raise LoadReparseError(503, "Re-parse signing is not configured.")
    return secret.encode()


def reparse_integrity_token(
    *,
    tenant_id: int,
    load_id: int,
    pdf_bytes: bytes,
    revised_parse: dict,
    baseline: dict,
    concurrency_version: int,
    acknowledgement_required: bool,
    expires_at: int,
) -> str:
    """Bind the proposal to this PDF, the verified baseline, and the load version."""
    from app.services.load_workspace_draft_document import parse_json_for_compare

    pdf_digest = hashlib.sha256(pdf_bytes).hexdigest()
    body_digest = hashlib.sha256(canonical_reparse_document(revised_parse).encode()).hexdigest()
    baseline_digest = hashlib.sha256(canonical_reparse_document(parse_json_for_compare(baseline)).encode()).hexdigest()
    message = (
        f"{int(tenant_id)}|{int(load_id)}|{pdf_digest}|{body_digest}|{baseline_digest}|"
        f"{int(concurrency_version)}|{int(bool(acknowledgement_required))}|{int(expires_at)}"
    ).encode()
    return hmac.new(_reparse_signing_key(), message, hashlib.sha256).hexdigest()


def verify_reparse_integrity(
    *,
    tenant_id: int,
    load_id: int,
    pdf_bytes: bytes,
    revised_parse: dict,
    token: str,
    baseline: dict,
    concurrency_version: int,
    acknowledgement_required: bool,
    expires_at: int,
) -> None:
    if not isinstance(revised_parse, dict) or not pdf_bytes or not isinstance(token, str) or not token.strip():
        raise LoadReparseError(422, "This re-parse does not match the uploaded PDF.")
    if not isinstance(expires_at, int):
        raise LoadReparseError(422, "This re-parse does not match the uploaded PDF.")
    expected = reparse_integrity_token(
        tenant_id=tenant_id,
        load_id=load_id,
        pdf_bytes=pdf_bytes,
        revised_parse=revised_parse,
        baseline=baseline,
        concurrency_version=concurrency_version,
        acknowledgement_required=acknowledgement_required,
        expires_at=expires_at,
    )
    if not hmac.compare_digest(expected, token.strip()):
        raise LoadReparseError(422, "This re-parse does not match the uploaded PDF.")
    if expires_at < int(time.time()):
        raise LoadReparseError(422, "This re-parse expired. Upload the PDF again. Nothing was changed.")


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


async def propose_load_reparse(
    db: AsyncSession,
    *,
    tenant_id: int,
    load_id: int,
    pdf_bytes: bytes,
    filename: str,
    openai_chat_json_schema: Callable[..., Awaitable[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Read a revised PDF with the existing parser and ask what changed. Writes nothing."""
    import json

    from sqlalchemy import select

    from app.models.load import Load
    from app.models.load_commercial_evidence import LoadCommercialEvidence
    from app.services.load_parser_duplicate_precheck import (
        DuplicatePrecheckUnavailable,
        find_exact_pdf_duplicate_candidates,
    )
    from app.services.load_workspace_draft_document import (
        assess_same_load,
        build_reparse_proposal_document,
        classify_load_pdf_reuse,
        extract_reparse_pdf_plain_text,
        parse_json_for_compare,
        reparse_text_document_block_reason,
        validate_ai_reparse_changes,
    )

    evidence = await db.scalar(
        select(LoadCommercialEvidence).where(
            LoadCommercialEvidence.tenant_id == tenant_id,
            LoadCommercialEvidence.load_id == load_id,
            LoadCommercialEvidence.evidence_kind == "rate_confirmation_pdf",
        )
    )
    if evidence is None or not isinstance(evidence.accepted_parse_json, dict):
        raise LoadReparseError(422, "This load has no saved parser JSON to compare against.")
    reuse_status = classify_load_pdf_reuse(evidence, pdf_bytes)
    # Re-parse means READ and compare. Identical attachments must not be added
    # again on Save, but their hashes do not forbid checking saved Load fields.
    # Only a strictly older revised attachment is review-only. Re-reading the load's
    # original rate confirmation must still allow correcting saved fields (e.g. linehaul).
    historical_pdf = reuse_status == "existing_prior_revision"
    try:
        other_loads = await find_exact_pdf_duplicate_candidates(
            db, tenant_id=tenant_id, pdf_bytes=pdf_bytes, exclude_load_id=load_id
        )
    except DuplicatePrecheckUnavailable as exc:
        raise LoadReparseError(503, "Duplicate check unavailable; AI parsing was not started.") from exc
    if other_loads:
        raise LoadReparseError(409, "This PDF matches a different load. Nothing was changed.")

    from app.services.load_document_parse_semantic_llm import LoadDocumentParseProviderError

    try:
        pdf_text = extract_reparse_pdf_plain_text(pdf_bytes)
    except ValueError as exc:
        raise LoadReparseError(422, str(exc)) from exc
    block_reason = reparse_text_document_block_reason(pdf_text)
    if block_reason:
        raise LoadReparseError(422, block_reason)

    saved = parse_json_for_compare(evidence.accepted_parse_json)
    saved_extracted = saved.get("extracted") if isinstance(saved.get("extracted"), dict) else {}
    diff_kwargs = {
        "system": _REPARSE_TEXT_DIFF_INSTRUCTIONS,
        "user_text": (
            "Saved verified JSON (extracted):\n"
            + json.dumps(saved_extracted, default=str, ensure_ascii=False)
            + "\n\nNew PDF text:\n"
            + pdf_text
        ),
        "schema": _REPARSE_TEXT_DIFF_SCHEMA,
        "schema_name": "load_reparse_text_diff",
        "input_file_bytes": None,
    }
    ai_started = time.perf_counter()
    try:
        if openai_chat_json_schema is not None:
            compared = await openai_chat_json_schema(**diff_kwargs)
        else:
            from app.services.load_document_parse_semantic_llm import (
                load_parser_semantic_configured,
                parse_document_semantic_chat_json_schema,
            )

            if not load_parser_semantic_configured():
                raise LoadReparseError(503, "The parser model is not configured.")
            compared = await parse_document_semantic_chat_json_schema(**diff_kwargs)
    except LoadReparseError:
        raise
    except LoadDocumentParseProviderError as exc:
        raise LoadReparseError(503, exc.user_message) from exc
    except Exception as exc:
        raise LoadReparseError(422, "The revised PDF could not be compared.") from exc
    ai_ms = int((time.perf_counter() - ai_started) * 1000)
    logger.info(
        "load_parser_reparse_ai_complete tenant_id=%s load_id=%s ai_calls=1 ai_ms=%s pdf_text_chars=%s",
        tenant_id,
        load_id,
        ai_ms,
        len(pdf_text),
    )
    raw_changes = compared.get("changes") if isinstance(compared, dict) else None
    if not isinstance(raw_changes, list):
        raise LoadReparseError(422, "The revised PDF could not be compared.")
    changes = validate_ai_reparse_changes(saved, pdf_text, raw_changes)
    revised_document = build_reparse_proposal_document(
        saved,
        filename=filename,
        pdf_text=pdf_text,
        changes=changes,
    )
    revised_doc = parse_json_for_compare(revised_document)
    identity = assess_same_load(
        saved,
        revised_doc,
        broker_aliases=await _broker_aliases(db, tenant_id, saved, revised_doc),
    )
    if identity["verdict"] == "blocked":
        if reuse_status == "new_revision":
            raise LoadReparseError(422, identity["summary"])
        # The SHA-256 is already trusted evidence for THIS Load. The Load may
        # have manually edited fields; expose disagreements for dispatcher review.
        identity = {
            "verdict": "needs_confirmation",
            "summary": "This PDF is already accepted on this Load, but its shipment fields disagree with saved values. Review manually.",
            "reasons": [identity["summary"]],
            "acknowledgement_required": True,
        }
    if historical_pdf:
        identity = {
            **identity,
            "verdict": "needs_confirmation",
            "summary": "Historical PDF version — review differences, but do not apply an older version as an amendment.",
            "reasons": [*identity["reasons"], identity["summary"]],
            "acknowledgement_required": True,
        }
    if historical_pdf:
        locked: list[dict] = []
        for item in changes:
            current = item.get("current_value")
            blank = current is None or (isinstance(current, str) and not current.strip())
            if blank and item.get("editable") is True:
                locked.append(item)
                continue
            locked.append(
                {
                    **item,
                    "editable": False,
                    "explanation": (
                        "Historical PDF: review-only. " + str(item.get("explanation") or "")
                    ).strip(),
                }
            )
        changes = locked
    version_value = await db.scalar(
        select(Load.concurrency_version).where(Load.tenant_id == tenant_id, Load.id == load_id)
    )
    concurrency_version = (
        version_value if isinstance(version_value, int) else int(getattr(evidence, "concurrency_version", 1) or 1)
    )
    expires_at = int(time.time()) + 30 * 60
    return {
        "changes": changes,
        "pdf_reuse_status": reuse_status,
        "store_new_pdf": reuse_status == "new_revision",
        "revised_parse": revised_document,
        "integrity": reparse_integrity_token(
            tenant_id=tenant_id,
            load_id=load_id,
            pdf_bytes=pdf_bytes,
            revised_parse=revised_document,
            baseline=saved,
            concurrency_version=concurrency_version,
            acknowledgement_required=bool(identity["acknowledgement_required"]),
            expires_at=expires_at,
        ),
        "verdict": identity["verdict"],
        "summary": identity["summary"] if changes else "No changes found.",
        "reasons": identity["reasons"] if changes else [],
        "acknowledgement_required": bool(identity["acknowledgement_required"]) if changes else False,
        "expires_at": expires_at,
    }
