"""Compatibility re-export of the shared OpenAI JSON-schema transport.

Implementation: ``app.document_platform.capabilities.openai.chat_json_schema``.
"""

from app.document_platform.capabilities.openai.chat_json_schema import (
    DEFAULT_OPENAI_CHAT_TIMEOUT_S,
    OPENAI_CHAT_COMPLETIONS_URL,
    OpenAIChatCompletionError,
    OpenAIChatCompletionJsonError,
    OpenAIChatCompletionStructureError,
    extract_chat_completion_content_json,
    openai_chat_json_schema_content,
    openai_chat_json_schema_raw,
)

__all__ = [
    "DEFAULT_OPENAI_CHAT_TIMEOUT_S",
    "OPENAI_CHAT_COMPLETIONS_URL",
    "OpenAIChatCompletionError",
    "OpenAIChatCompletionJsonError",
    "OpenAIChatCompletionStructureError",
    "extract_chat_completion_content_json",
    "openai_chat_json_schema_content",
    "openai_chat_json_schema_raw",
]
