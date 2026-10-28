"""HTTP helper for POST /loads/parse-document.

This module is not a second parser. It validates caller context and forwards bytes to the
single product entrypoint ``parse_pdf_bytes_to_load_document_response``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
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


_COMPARE_SCHEMA = {
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
                    "label": {"type": "string"},
                    "current_value": {},
                    "revised_value": {},
                },
                "required": ["field", "label", "current_value", "revised_value"],
            },
        }
    },
    "required": ["changes"],
}

_COMPARE_INSTRUCTIONS = (
    "You are comparing one revised rate confirmation against the load's one saved verified JSON. "
    "saved_verified_json is the baseline currently on the load. "
    "revised_extraction is the new PDF after the existing parser normalized it. "
    "Return only fields whose value changed. Any field may change, including city, address, "
    "temperature, rate, stops, equipment, and the broker load number, PO number, or order number. "
    "A different PO or load number is a normal proposed change. Do not reject the PDF for that. "
    "Do not return unchanged fields. "
    "field is a path such as rate, temperature_requirement, broker_load_reference, or stops[0].city. "
    "current_value is the saved JSON value. revised_value is the new PDF value."
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
        deterministic_reparse_changes,
        known_pdf_reuse_message,
        parse_json_for_compare,
        reparse_document_block_reason,
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
    reuse = known_pdf_reuse_message(evidence, pdf_bytes)
    if reuse:
        raise LoadReparseError(422, reuse)
    try:
        other_loads = await find_exact_pdf_duplicate_candidates(
            db, tenant_id=tenant_id, pdf_bytes=pdf_bytes, exclude_load_id=load_id
        )
    except DuplicatePrecheckUnavailable as exc:
        raise LoadReparseError(503, "Duplicate check unavailable; AI parsing was not started.") from exc
    if other_loads:
        raise LoadReparseError(409, "This PDF matches a different load. Nothing was changed.")

    revised = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename=filename,
        tenant_id=tenant_id,
        db=db,
        load_id=load_id,
        openai_chat_json_schema=openai_chat_json_schema,
    )
    if (revised.context or {}).get("semantic_outcome") == "blocked_duplicate_review":
        raise LoadReparseError(409, "This PDF matches a different load. Nothing was changed.")

    saved = parse_json_for_compare(evidence.accepted_parse_json)
    revised_document = revised.model_dump(mode="json")
    revised_doc = parse_json_for_compare(revised_document)
    block_reason = reparse_document_block_reason(revised_doc)
    if block_reason:
        raise LoadReparseError(422, block_reason)
    identity = assess_same_load(saved, revised_doc)
    if identity["verdict"] == "blocked":
        raise LoadReparseError(422, identity["summary"])
    compare_kwargs = {
        "system": _COMPARE_INSTRUCTIONS,
        "user_text": (
            "saved_verified_json:\n"
            + json.dumps(saved, default=str)
            + "\n\nrevised_extraction:\n"
            + json.dumps(revised_doc, default=str)
        ),
        "schema": _COMPARE_SCHEMA,
        "schema_name": "load_reparse_changes",
    }
    try:
        if openai_chat_json_schema is not None:
            compared = await openai_chat_json_schema(**compare_kwargs)
        else:
            from app.services.load_document_parse_semantic_llm import (
                load_parser_semantic_configured,
                parse_document_semantic_chat_json_schema,
            )

            if not load_parser_semantic_configured():
                raise LoadReparseError(503, "The parser model is not configured.")
            compared = await parse_document_semantic_chat_json_schema(**compare_kwargs)
    except LoadReparseError:
        raise
    except Exception as exc:
        raise LoadReparseError(422, "The revised PDF could not be compared.") from exc
    raw_changes = compared.get("changes") if isinstance(compared, dict) else None
    if not isinstance(raw_changes, list):
        raise LoadReparseError(422, "The revised PDF could not be compared.")
    changes = deterministic_reparse_changes(saved, revised_doc)
    version_value = await db.scalar(select(Load.concurrency_version).where(Load.tenant_id == tenant_id, Load.id == load_id))
    concurrency_version = version_value if isinstance(version_value, int) else int(getattr(evidence, "concurrency_version", 1) or 1)
    expires_at = int(time.time()) + 30 * 60
    return {
        "changes": changes,
        "revised_parse": revised,
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
        "summary": identity["summary"],
        "reasons": identity["reasons"],
        "acknowledgement_required": bool(identity["acknowledgement_required"]),
        "expires_at": expires_at,
    }
