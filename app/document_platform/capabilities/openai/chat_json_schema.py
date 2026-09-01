"""Slice 1A re-export of the existing OpenAI JSON-schema transport.

Implementation remains in ``app.services.openai_chat_json_schema``.
This module must not import Load, DL, router, or profile code.
"""

from app.services.openai_chat_json_schema import (
    extract_chat_completion_content_json,
    openai_chat_json_schema_content,
    openai_chat_json_schema_raw,
)

__all__ = [
    "extract_chat_completion_content_json",
    "openai_chat_json_schema_content",
    "openai_chat_json_schema_raw",
]
