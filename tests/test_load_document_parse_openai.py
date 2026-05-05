"""parse-document OpenAI injectable wrapper — delegates only; mocked downstream."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.load_document_parse_openai import parse_document_openai_chat_json_schema


@pytest.mark.asyncio
async def test_parse_document_openai_delegates_to_content_helper() -> None:
    wire_dict = {"document": {"filename": "a.pdf"}, "extracted": {"references": [], "stops": []}}
    mock_content = AsyncMock(return_value=wire_dict)
    with patch(
        "app.services.load_document_parse_openai.openai_chat_json_schema_content",
        mock_content,
    ):
        out = await parse_document_openai_chat_json_schema(
            api_key="k",
            model="m",
            system="s",
            user_text="u",
            schema={},
            schema_name="sn",
        )
    assert out == wire_dict
    mock_content.assert_awaited_once()
