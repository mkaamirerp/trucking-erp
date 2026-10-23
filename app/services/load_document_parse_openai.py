"""Backward-compatible import path for the load parser semantic LLM client."""

from __future__ import annotations

from typing import Any

from app.services.load_document_parse_semantic_llm import parse_document_semantic_chat_json_schema


async def parse_document_openai_chat_json_schema(**kwargs: Any) -> dict[str, Any]:
    """Injectable for guarded parse — routes OpenAI or Anthropic per ``LOAD_PARSER_LLM_PROVIDER``."""
    return await parse_document_semantic_chat_json_schema(**kwargs)
