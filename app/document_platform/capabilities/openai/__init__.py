"""OpenAI JSON-schema chat transport capability.

Implementation is owned by this Document Platform OpenAI capability.
``app.services.openai_chat_json_schema`` remains a compatibility shim.
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
