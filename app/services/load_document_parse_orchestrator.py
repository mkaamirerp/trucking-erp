"""HTTP helper for POST /loads/parse-document.

This module is not a second parser. It validates caller context and forwards bytes to the
single product entrypoint ``parse_pdf_bytes_to_load_document_response``.
"""

from __future__ import annotations

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


def _display_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


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

    from app.models.load_commercial_evidence import LoadCommercialEvidence
    from app.services.load_document_parse_semantic_llm import (
        default_load_parser_semantic_client,
        load_parser_semantic_configured,
    )
    from app.services.load_workspace_draft_document import parse_json_for_compare, values_equivalent

    evidence = await db.scalar(
        select(LoadCommercialEvidence).where(
            LoadCommercialEvidence.tenant_id == tenant_id,
            LoadCommercialEvidence.load_id == load_id,
            LoadCommercialEvidence.evidence_kind == "rate_confirmation_pdf",
        )
    )
    if evidence is None or not isinstance(evidence.accepted_parse_json, dict):
        raise LoadReparseError(422, "This load has no saved parser JSON to compare against.")

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
    revised_doc = parse_json_for_compare(revised.model_dump(mode="json"))
    client = openai_chat_json_schema or (
        default_load_parser_semantic_client() if load_parser_semantic_configured() else None
    )
    if client is None:
        raise LoadReparseError(503, "The parser model is not configured.")
    try:
        compared = await client(
            system=_COMPARE_INSTRUCTIONS,
            user_text=(
                "saved_verified_json:\n"
                + json.dumps(saved, default=str)
                + "\n\nrevised_extraction:\n"
                + json.dumps(revised_doc, default=str)
            ),
            schema=_COMPARE_SCHEMA,
            schema_name="load_reparse_changes",
        )
    except Exception as exc:
        raise LoadReparseError(422, "The revised PDF could not be compared.") from exc
    raw_changes = compared.get("changes") if isinstance(compared, dict) else None
    if not isinstance(raw_changes, list):
        raise LoadReparseError(422, "The revised PDF could not be compared.")
    changes: list[dict[str, Any]] = []
    for item in raw_changes:
        if not isinstance(item, dict):
            continue
        field = _display_text(item.get("field"))
        if not field or values_equivalent(item.get("current_value"), item.get("revised_value")):
            continue
        changes.append(
            {
                "field": field,
                "label": _display_text(item.get("label")) or field,
                "current_value": item.get("current_value"),
                "revised_value": item.get("revised_value"),
            }
        )
    return {"changes": changes, "revised_parse": revised}
