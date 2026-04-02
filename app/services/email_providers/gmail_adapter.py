"""Gmail adapter: HTTP fetch only. Normalization + persistence live in `email_engine`."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.services.email_ingestion_gmail import _gmail_get_json


async def fetch_thread_full(access_token: str, external_thread_id: str) -> dict[str, Any]:
    """Returns Gmail `users.threads.get` JSON (`format=full`)."""
    return await _gmail_get_json(
        access_token,
        f"/threads/{quote(external_thread_id, safe='')}",
        params={"format": "full"},
    )
