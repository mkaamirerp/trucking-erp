"""Anthropic Messages API — structured extraction via tool_use (same contract as OpenAI helper)."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

DEFAULT_ANTHROPIC_CHAT_TIMEOUT_S = 120.0
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicChatCompletionError(Exception):
    """Base for Anthropic response handling errors."""


class AnthropicChatCompletionStructureError(AnthropicChatCompletionError):
    """Response missing usable tool_use input."""


def _build_user_content_blocks(
    *,
    user_text: str,
    input_file_bytes: bytes | None,
    input_filename: str,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if input_file_bytes:
        lower = (input_filename or "").lower()
        if lower.endswith(".pdf") or input_file_bytes[:4] == b"%PDF":
            media_type = "application/pdf"
        elif lower.endswith(".png") or input_file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            media_type = "image/png"
        else:
            media_type = "image/jpeg"
        encoded = base64.standard_b64encode(input_file_bytes).decode("ascii")
        if media_type == "application/pdf":
            blocks.append(
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": media_type, "data": encoded},
                }
            )
        else:
            blocks.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": encoded},
                }
            )
    blocks.append({"type": "text", "text": user_text})
    return blocks


def extract_tool_use_input_json(raw: dict[str, Any], tool_name: str) -> dict[str, Any]:
    content = raw.get("content")
    if not isinstance(content, list):
        raise AnthropicChatCompletionStructureError("Anthropic response missing content list")
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        if block.get("name") != tool_name:
            continue
        inp = block.get("input")
        if isinstance(inp, dict):
            return inp
        raise AnthropicChatCompletionStructureError("tool_use input is not an object")
    # Fallback: single text block with JSON
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text") or "").strip()
            if text.startswith("{"):
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise AnthropicChatCompletionStructureError(
                        f"text block is not valid JSON: {exc}"
                    ) from exc
                if isinstance(obj, dict):
                    return obj
    raise AnthropicChatCompletionStructureError(f"no tool_use block named {tool_name}")


async def anthropic_chat_json_schema_content(
    *,
    api_key: str,
    model: str,
    system: str,
    user_text: str,
    schema: dict[str, Any],
    schema_name: str,
    input_file_bytes: bytes | None = None,
    input_filename: str = "upload.pdf",
    url: str = ANTHROPIC_MESSAGES_URL,
    timeout_seconds: float = DEFAULT_ANTHROPIC_CHAT_TIMEOUT_S,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    """POST /v1/messages with tool_choice forcing schema-shaped JSON (reasoning_effort ignored)."""
    _ = reasoning_effort
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    tool_name = (schema_name or "extract")[:64]
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": 16384,
        "system": system,
        "messages": [
            {
                "role": "user",
                "content": _build_user_content_blocks(
                    user_text=user_text,
                    input_file_bytes=input_file_bytes,
                    input_filename=input_filename,
                ),
            }
        ],
        "tools": [
            {
                "name": tool_name,
                "description": "Extract rate confirmation fields matching the TruckERP semantic schema.",
                "input_schema": schema,
            }
        ],
        "tool_choice": {"type": "tool", "name": tool_name},
    }
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        raw = r.json()
    return extract_tool_use_input_json(raw, tool_name)
