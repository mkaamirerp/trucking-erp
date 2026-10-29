"""Load parser semantic LLM switch — OpenAI vs Anthropic; pipeline unchanged above this layer."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.core.config import settings
from app.document_platform.capabilities.anthropic.chat_json_schema import (
    anthropic_chat_json_schema_content,
)
from app.document_platform.capabilities.openai.chat_json_schema import openai_chat_json_schema_content

logger = logging.getLogger(__name__)

SemanticChatJsonSchemaFn = Callable[..., Awaitable[dict[str, Any]]]


class LoadDocumentParseProviderError(Exception):
    """Upstream LLM HTTP failure — map to 503 for operators, log provider body server-side."""

    def __init__(
        self,
        *,
        provider: str,
        http_status: int | None,
        provider_message: str,
        user_message: str,
    ) -> None:
        super().__init__(user_message)
        self.provider = provider
        self.http_status = http_status
        self.provider_message = provider_message
        self.user_message = user_message


def _operator_message_for_http_status(http_status: int | None) -> str:
    if http_status == 429:
        return "The document parser is busy. Wait a moment and try again."
    if http_status in {401, 403}:
        return "The document parser is not configured correctly. Contact your administrator."
    return "The document parser is unavailable right now. Try again later or contact your administrator."


def _log_semantic_provider_http_admin_hint(*, provider: str, body: str) -> None:
    """One-line ops hint in server logs only (never shown to dispatchers)."""
    if provider != "anthropic":
        return
    lowered = body.casefold()
    if "credit balance" not in lowered or "anthropic" not in lowered:
        return
    logger.error(
        "ADMIN: Anthropic API credits exhausted — add billing credits or set "
        "LOAD_PARSER_LLM_PROVIDER=openai in SSM (/truckerp/prod/platform/)."
    )


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
    return parse_document_semantic_chat_json_schema


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
    try:
        return await fn(api_key=api_key, model=model, **kwargs)
    except httpx.HTTPStatusError as exc:
        resp = exc.response
        body = (resp.text or "")[:1500] if resp is not None else ""
        code = resp.status_code if resp is not None else None
        logger.warning(
            "load_parser_semantic_http_error provider=%s http_status=%s body=%s",
            provider,
            code,
            body[:800],
        )
        _log_semantic_provider_http_admin_hint(provider=provider, body=body)
        raise LoadDocumentParseProviderError(
            provider=provider,
            http_status=code,
            provider_message=body,
            user_message=_operator_message_for_http_status(code),
        ) from exc
