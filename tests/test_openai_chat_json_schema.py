"""Unit tests for app.services.openai_chat_json_schema — mocked httpx only."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.openai_chat_json_schema import (
    OpenAIChatCompletionJsonError,
    OpenAIChatCompletionStructureError,
    extract_chat_completion_content_json,
    openai_chat_json_schema_content,
    openai_chat_json_schema_raw,
)


def test_extract_chat_completion_content_json_valid() -> None:
    raw = {
        "choices": [{"message": {"content": '  {"ok": true, "n": 1}  '}}],
        "usage": {"total_tokens": 10},
    }
    out = extract_chat_completion_content_json(raw)
    assert out == {"ok": True, "n": 1}


def test_extract_chat_completion_content_json_no_choices() -> None:
    with pytest.raises(OpenAIChatCompletionStructureError, match="no choices"):
        extract_chat_completion_content_json({})


def test_extract_chat_completion_content_json_empty_choices() -> None:
    with pytest.raises(OpenAIChatCompletionStructureError, match="no choices"):
        extract_chat_completion_content_json({"choices": []})


def test_extract_chat_completion_content_json_bad_choice_shape() -> None:
    with pytest.raises(OpenAIChatCompletionStructureError, match="not an object"):
        extract_chat_completion_content_json({"choices": [None]})


def test_extract_chat_completion_content_json_missing_message() -> None:
    with pytest.raises(OpenAIChatCompletionStructureError, match="message object"):
        extract_chat_completion_content_json({"choices": [{}]})


def test_extract_chat_completion_content_json_empty_content() -> None:
    with pytest.raises(OpenAIChatCompletionStructureError, match="empty message"):
        extract_chat_completion_content_json({"choices": [{"message": {"content": "   "}}]})


def test_extract_chat_completion_content_json_invalid_json() -> None:
    with pytest.raises(OpenAIChatCompletionJsonError, match="not valid JSON"):
        extract_chat_completion_content_json(
            {"choices": [{"message": {"content": "not-json"}}]},
        )


def test_extract_chat_completion_content_json_non_object() -> None:
    with pytest.raises(OpenAIChatCompletionStructureError, match="must be an object"):
        extract_chat_completion_content_json(
            {"choices": [{"message": {"content": "[1, 2]"}}]},
        )


def _mock_async_client(post_impl: AsyncMock) -> MagicMock:
    mock_client = MagicMock()
    mock_client.post = post_impl
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_openai_chat_json_schema_raw_200_returns_wire_json() -> None:
    wire = {"choices": [{"message": {"content": "{}"}}], "id": "chatcmpl-test"}
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = wire
    post = AsyncMock(return_value=resp)
    mock_client = _mock_async_client(post)

    with patch("app.services.openai_chat_json_schema.httpx.AsyncClient", return_value=mock_client):
        out = await openai_chat_json_schema_raw(
            api_key="sk-test",
            model="gpt-4o-mini",
            system="sys",
            user_text="hello",
            schema={"type": "object"},
            schema_name="test_schema",
        )

    assert out == wire
    post.assert_awaited_once()
    body = post.await_args.kwargs["json"]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "test_schema"
    assert body["response_format"]["json_schema"]["strict"] is False
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert post.await_args.kwargs["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_openai_chat_json_schema_raw_400_json_schema_retries_fallback() -> None:
    resp400 = MagicMock()
    resp400.status_code = 400
    resp400.text = "Invalid parameter: response_format type json_schema not supported"

    wire = {"choices": [{"message": {"content": '{"x": 1}'}}]}
    resp200 = MagicMock()
    resp200.status_code = 200
    resp200.json.return_value = wire

    post = AsyncMock(side_effect=[resp400, resp200])
    mock_client = _mock_async_client(post)

    with patch("app.services.openai_chat_json_schema.httpx.AsyncClient", return_value=mock_client):
        out = await openai_chat_json_schema_raw(
            api_key="k",
            model="m",
            system="s",
            user_text="body",
            schema={},
            schema_name="n",
        )

    assert out == wire
    assert post.await_count == 2
    first = post.await_args_list[0].kwargs["json"]
    assert first["response_format"]["type"] == "json_schema"
    second = post.await_args_list[1].kwargs["json"]
    assert second["response_format"] == {"type": "json_object"}
    assert "Extract load fields" in second["messages"][1]["content"]


@pytest.mark.asyncio
async def test_openai_chat_json_schema_raw_non_fallback_400_raises() -> None:
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp = httpx.Response(400, request=req, content=b"bad request unrelated")
    post = AsyncMock(return_value=resp)
    mock_client = _mock_async_client(post)

    with patch("app.services.openai_chat_json_schema.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await openai_chat_json_schema_raw(
                api_key="k",
                model="m",
                system="s",
                user_text="u",
                schema={},
                schema_name="n",
            )


@pytest.mark.asyncio
async def test_openai_chat_json_schema_content_combines_raw_and_extract() -> None:
    wire = {"choices": [{"message": {"content": '{"parsed": true}'}}]}
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = wire
    post = AsyncMock(return_value=resp)
    mock_client = _mock_async_client(post)

    with patch("app.services.openai_chat_json_schema.httpx.AsyncClient", return_value=mock_client):
        out = await openai_chat_json_schema_content(
            api_key="k",
            model="m",
            system="s",
            user_text="u",
            schema={"type": "object"},
            schema_name="sn",
        )

    assert out == {"parsed": True}


def test_module_has_no_load_lab_import_path() -> None:
    import app.services.openai_chat_json_schema as mod

    src = open(mod.__file__, encoding="utf-8").read().lower()
    assert "load_lab" not in src
    assert "sqlalchemy" not in src


def test_openai_capability_namespace_reexports_same_callables() -> None:
    import app.document_platform.capabilities.openai.chat_json_schema as new
    import app.services.openai_chat_json_schema as old

    assert new.openai_chat_json_schema_raw is old.openai_chat_json_schema_raw
    assert new.extract_chat_completion_content_json is old.extract_chat_completion_content_json
    assert new.openai_chat_json_schema_content is old.openai_chat_json_schema_content
