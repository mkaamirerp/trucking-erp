"""Load parser LLM provider switch (OpenAI vs Anthropic) — no pipeline tests."""

from __future__ import annotations

import pytest

from app.services.load_document_parse_semantic_llm import (
    default_load_parser_semantic_client,
    load_parser_semantic_api_key,
    load_parser_semantic_model,
    load_parser_semantic_provider,
    normalize_load_parser_llm_provider,
    parse_document_semantic_chat_json_schema,
    _log_semantic_provider_http_admin_hint,
)


def test_normalize_provider_aliases() -> None:
    assert normalize_load_parser_llm_provider("openai") == "openai"
    assert normalize_load_parser_llm_provider("anthropic") == "anthropic"
    assert normalize_load_parser_llm_provider("claude") == "anthropic"


def test_normalize_provider_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid load_parser_llm_provider"):
        normalize_load_parser_llm_provider("azure")


def test_default_client_routes_by_settings() -> None:
    assert default_load_parser_semantic_client() is parse_document_semantic_chat_json_schema


def test_admin_log_hint_on_anthropic_credit_error(caplog: pytest.LogCaptureFixture) -> None:
    body = (
        '{"type":"error","error":{"type":"invalid_request_error",'
        '"message":"Your credit balance is too low to access the Anthropic API."}}'
    )
    with caplog.at_level("ERROR"):
        _log_semantic_provider_http_admin_hint(provider="anthropic", body=body)
    assert any("ADMIN: Anthropic API credits exhausted" in r.message for r in caplog.records)
    caplog.clear()
    with caplog.at_level("ERROR"):
        _log_semantic_provider_http_admin_hint(provider="openai", body=body)
        _log_semantic_provider_http_admin_hint(provider="anthropic", body='{"error":"rate_limit"}')
    assert not caplog.records


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
