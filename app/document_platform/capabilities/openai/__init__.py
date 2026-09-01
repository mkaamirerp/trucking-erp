"""OpenAI JSON-schema chat transport capability (Slice 1A).

Re-exports the existing implementation in ``app.services.openai_chat_json_schema``.
This package does not own the implementation yet.
"""

from app.document_platform.capabilities.openai.chat_json_schema import (
    extract_chat_completion_content_json,
    openai_chat_json_schema_content,
    openai_chat_json_schema_raw,
)

__all__ = [
    "extract_chat_completion_content_json",
    "openai_chat_json_schema_content",
    "openai_chat_json_schema_raw",
]
