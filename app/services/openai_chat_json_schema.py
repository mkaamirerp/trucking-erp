"""Minimal OpenAI Chat Completions helpers (B2-A): json_schema + json_object fallback.

Stateless: no database, Load Lab, tenant/session, routers, or parsers.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

DEFAULT_OPENAI_CHAT_TIMEOUT_S = 120.0
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIChatCompletionError(Exception):
    """Base for chat completion response handling errors."""


class OpenAIChatCompletionStructureError(OpenAIChatCompletionError):
    """choices / message / content missing or not usable."""


class OpenAIChatCompletionJsonError(OpenAIChatCompletionError):
    """message.content is not valid JSON object."""


def extract_chat_completion_content_json(raw: dict[str, Any]) -> dict[str, Any]:
    """Return the JSON object from ``choices[0].message.content`` (parsed).

    Raises:
        OpenAIChatCompletionStructureError: missing/invalid shape or empty content.
        OpenAIChatCompletionJsonError: content is not valid JSON.
    """
    choices = raw.get("choices")
    if not isinstance(choices, list) or len(choices) == 0:
        raise OpenAIChatCompletionStructureError("OpenAI response has no choices")
    choice0 = choices[0]
    if not isinstance(choice0, dict):
        raise OpenAIChatCompletionStructureError("OpenAI response choice[0] is not an object")
    msg = choice0.get("message")
    if not isinstance(msg, dict):
        raise OpenAIChatCompletionStructureError("OpenAI response missing message object")
    content = msg.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OpenAIChatCompletionStructureError("OpenAI response has empty message content")
    try:
        obj = json.loads(content.strip())
    except json.JSONDecodeError as exc:
        raise OpenAIChatCompletionJsonError(f"message.content is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise OpenAIChatCompletionStructureError("message.content JSON must be an object")
    return obj


async def openai_chat_json_schema_raw(
    *,
    api_key: str,
    model: str,
    system: str,
    user_text: str,
    schema: dict[str, Any],
    schema_name: str,
    url: str = OPENAI_CHAT_COMPLETIONS_URL,
    timeout_seconds: float = DEFAULT_OPENAI_CHAT_TIMEOUT_S,
) -> dict[str, Any]:
    """POST ``/v1/chat/completions`` with ``response_format`` json_schema.

    On HTTP 400 whose body mentions ``json_schema``, retries once with
    ``response_format: json_object`` (same behavior as legacy Load Lab helper).
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body_schema: dict[str, Any] = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": False, "schema": schema},
        },
    }
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        r = await client.post(url, headers=headers, json=body_schema)
        if r.status_code == 200:
            return r.json()
        err_snip = (r.text or "")[:800]
        if r.status_code == 400 and "json_schema" in err_snip.lower():
            body_obj = {
                "model": model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": system + " Respond with a single JSON object only."},
                    {
                        "role": "user",
                        "content": (
                            "Extract load fields. Output one JSON object with keys: document (object with "
                            "filename), extracted (broker fields, references, stops), warnings (array of "
                            "strings), field_confidence (object mapping field paths to strings, optional). "
                            "Do not include raw_text or context.\n\n---\n\n"
                            f"{user_text}"
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
            }
            r2 = await client.post(url, headers=headers, json=body_obj)
            r2.raise_for_status()
            return r2.json()
        r.raise_for_status()
        return r.json()


async def openai_chat_json_schema_content(
    *,
    api_key: str,
    model: str,
    system: str,
    user_text: str,
    schema: dict[str, Any],
    schema_name: str,
    url: str = OPENAI_CHAT_COMPLETIONS_URL,
    timeout_seconds: float = DEFAULT_OPENAI_CHAT_TIMEOUT_S,
) -> dict[str, Any]:
    """Raw completion then parse ``choices[0].message.content`` as JSON object."""
    raw = await openai_chat_json_schema_raw(
        api_key=api_key,
        model=model,
        system=system,
        user_text=user_text,
        schema=schema,
        schema_name=schema_name,
        url=url,
        timeout_seconds=timeout_seconds,
    )
    return extract_chat_completion_content_json(raw)
