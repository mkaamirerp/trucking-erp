"""Load parser semantic LLM switch — OpenAI vs Anthropic; pipeline unchanged above this layer."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import settings
from app.document_platform.capabilities.anthropic.chat_json_schema import (
    anthropic_chat_json_schema_content,
)
from app.document_platform.capabilities.openai.chat_json_schema import openai_chat_json_schema_content

SemanticChatJsonSchemaFn = Callable[..., Awaitable[dict[str, Any]]]


def normalize_load_parser_llm_provider(raw: str | None = None) -> str:
    value = (raw if raw is not None else settings.load_parser_llm_provider or "openai").strip().lower()
    if value in ("openai", "gpt", "openai_gpt"):
        return "openai"
    if value in ("anthropic", "claude"):
        return "anthropic"
    raise ValueError(
        f"Invalid load_parser_llm_provider '{value}' (use openai or anthropic; env LOAD_PARSER_LLM_PROVIDER)"
    )


def load_parser_semantic_provider() -> str:
    return normalize_load_parser_llm_provider()


def load_parser_semantic_api_key() -> str:
    if load_parser_semantic_provider() == "anthropic":
        return (settings.anthropic_api_key or "").strip()
    return (settings.openai_api_key or "").strip()


def load_parser_semantic_model() -> str:
    if load_parser_semantic_provider() == "anthropic":
        raw = (settings.load_parser_anthropic_model or settings.anthropic_extraction_model or "").strip()
        return raw or "claude-haiku-4-5-20251001"
    return (settings.openai_extraction_model or "gpt-4o-mini").strip() or "gpt-4o-mini"


def load_parser_semantic_configured() -> bool:
    return bool(load_parser_semantic_api_key())


def default_load_parser_semantic_client() -> SemanticChatJsonSchemaFn:
    if load_parser_semantic_provider() == "anthropic":
        return anthropic_chat_json_schema_content
    return openai_chat_json_schema_content


async def parse_document_semantic_chat_json_schema(**kwargs: Any) -> dict[str, Any]:
    """
    Product rate-con semantic call. Routes to OpenAI or Anthropic from settings.
    Injectable in tests via ``openai_chat_json_schema=`` on ``parse_pdf_bytes_to_load_document_response``.
    """
    provider = load_parser_semantic_provider()
    if provider == "anthropic":
        fn = anthropic_chat_json_schema_content
    else:
        fn = openai_chat_json_schema_content
    api_key = (kwargs.pop("api_key", None) or load_parser_semantic_api_key()).strip()
    if not api_key:
        raise RuntimeError(f"{provider} API key not configured for load parser")
    model = (kwargs.pop("model", None) or load_parser_semantic_model()).strip()
    return await fn(api_key=api_key, model=model, **kwargs)
