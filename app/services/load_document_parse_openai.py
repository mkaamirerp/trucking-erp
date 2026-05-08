"""Parse-document OpenAI injectable: delegates to shared chat JSON helper (Track B2-B).

No database, Load Lab, router, or persistence.
"""

from __future__ import annotations

from typing import Any

from app.services.openai_chat_json_schema import openai_chat_json_schema_content


async def parse_document_openai_chat_json_schema(**kwargs: Any) -> dict[str, Any]:
    """Injectable for guarded parse (``parse_pdf_bytes_to_load_document_response``) — JSON object dict."""
    return await openai_chat_json_schema_content(**kwargs)
