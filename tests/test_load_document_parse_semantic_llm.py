"""Load parser LLM provider switch (OpenAI vs Anthropic) — no pipeline tests."""

from __future__ import annotations

import pytest

from app.services.load_document_parse_semantic_llm import (
    default_load_parser_semantic_client,
    load_parser_semantic_api_key,
    load_parser_semantic_model,
    load_parser_semantic_provider,
    normalize_load_parser_llm_provider,
)


def test_normalize_provider_aliases() -> None:
    assert normalize_load_parser_llm_provider("openai") == "openai"
    assert normalize_load_parser_llm_provider("anthropic") == "anthropic"
    assert normalize_load_parser_llm_provider("claude") == "anthropic"


def test_normalize_provider_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid load_parser_llm_provider"):
        normalize_load_parser_llm_provider("azure")


def test_default_client_routes_by_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "load_parser_llm_provider", "openai")
    from app.document_platform.capabilities.openai.chat_json_schema import (
        openai_chat_json_schema_content,
    )

    assert default_load_parser_semantic_client() is openai_chat_json_schema_content

    monkeypatch.setattr(settings, "load_parser_llm_provider", "anthropic")
    from app.document_platform.capabilities.anthropic.chat_json_schema import (
        anthropic_chat_json_schema_content,
    )

    assert default_load_parser_semantic_client() is anthropic_chat_json_schema_content


def test_model_and_key_follow_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "load_parser_llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-openai")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant")
    monkeypatch.setattr(settings, "openai_extraction_model", "gpt-5-mini")
    assert load_parser_semantic_provider() == "openai"
    assert load_parser_semantic_api_key() == "sk-openai"
    assert load_parser_semantic_model() == "gpt-5-mini"

    monkeypatch.setattr(settings, "load_parser_llm_provider", "anthropic")
    monkeypatch.setattr(settings, "load_parser_anthropic_model", "claude-haiku-4-5-20251001")
    assert load_parser_semantic_provider() == "anthropic"
    assert load_parser_semantic_api_key() == "sk-ant"
    assert load_parser_semantic_model() == "claude-haiku-4-5-20251001"
