"""Orchestration for POST /loads/parse-document: legacy regex vs semantic adapter (Track B1).

When semantic is enabled, only the semantic path runs — no silent fallback to regex.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_parse import parse_load_workspace_from_pdf_bytes
from app.services.load_document_parse_semantic import parse_load_workspace_from_pdf_semantic_stateless


def _normalize_semantic_context(res: LoadDocumentParseResponse) -> LoadDocumentParseResponse:
    """Expose parse_path=semantic for operators (skeleton internally used semantic_stateless)."""
    ctx = dict(res.context) if res.context else {}
    ctx["parse_path"] = "semantic"
    return res.model_copy(update={"context": ctx})


async def parse_load_workspace_document_orchestrated(
    pdf_bytes: bytes,
    *,
    filename: str,
    email_thread_id: int | None = None,
    load_id: int | None = None,
    semantic_enabled: bool = False,
    openai_chat_json_schema: Callable[..., Awaitable[dict[str, Any]]] | None = None,
) -> LoadDocumentParseResponse:
    """
    Parse PDF for workspace hydration only (no DB, no load/trip mutation).

    - ``semantic_enabled=False``: legacy ``parse_load_workspace_from_pdf_bytes`` only;
      response includes ``context.parse_path == \"legacy\"``.
    - ``semantic_enabled=True``: ``parse_load_workspace_from_pdf_semantic_stateless`` only;
      successes and failures return semantic-shaped ``LoadDocumentParseResponse`` with
      ``context.semantic_outcome``; **no** regex fallback and **no** mixing regex fields
      into semantic responses. ``context.parse_path`` is normalized to ``\"semantic\"``.
    """
    fn = (filename or "upload.pdf")[:512]

    if not semantic_enabled:
        raw = parse_load_workspace_from_pdf_bytes(
            pdf_bytes,
            filename=fn,
            email_thread_id=email_thread_id,
            load_id=load_id,
        )
        resp = LoadDocumentParseResponse.model_validate(raw)
        ctx = dict(resp.context) if resp.context else {}
        ctx["parse_path"] = "legacy"
        return resp.model_copy(update={"context": ctx})

    context_echo: dict[str, Any] = {}
    if email_thread_id is not None:
        context_echo["email_thread_id"] = email_thread_id
    if load_id is not None:
        context_echo["load_id"] = load_id

    out = await parse_load_workspace_from_pdf_semantic_stateless(
        pdf_bytes,
        filename=fn,
        context_echo=context_echo if context_echo else None,
        openai_chat_json_schema=openai_chat_json_schema,
    )
    return _normalize_semantic_context(out)
