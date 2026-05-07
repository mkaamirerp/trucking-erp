"""Orchestration for POST /loads/parse-document.

Product parse-document always uses the guarded product parser. The old regex parser
remains in the repo only for cleanup after successful UI parity testing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_parse_guarded import parse_pdf_bytes_to_load_document_response


async def parse_load_workspace_document_orchestrated(
    pdf_bytes: bytes,
    *,
    filename: str,
    email_thread_id: int | None = None,
    load_id: int | None = None,
    openai_chat_json_schema: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    tenant_id: int | None = None,
    db: AsyncSession | None = None,
) -> LoadDocumentParseResponse:
    """
    Parse PDF for workspace hydration only (no DB, no load/trip mutation).

    No feature flag and no legacy fallback: this route is the product guarded parser path.
    """
    _ = email_thread_id, load_id
    fn = (filename or "upload.pdf")[:512]

    if tenant_id is None or db is None:
        raise RuntimeError("tenant_id and db are required for guarded parse-document")

    return await parse_pdf_bytes_to_load_document_response(
        db,
        tenant_id=tenant_id,
        pdf_bytes=pdf_bytes,
        filename=fn,
        openai_chat_json_schema=openai_chat_json_schema,
    )
