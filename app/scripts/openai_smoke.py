"""
Verify OpenAI API connectivity (models list). Does not run extraction.

Run inside the API container with secrets loaded (same pattern as other app scripts):

  docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -m app.scripts.openai_smoke'

Exit: 0 on success, 1 on missing key or failure.
"""

from __future__ import annotations

import os
import sys

import httpx


def main() -> int:
    # NOTE: Do not import app.core.config.settings here. Settings requires DATABASE_URL and other
    # runtime env, but this script is intended to be runnable as a pure connectivity probe.
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        print("OPENAI_API_KEY is not set or empty.", file=sys.stderr)
        return 1
    try:
        with httpx.Client(timeout=45.0) as client:
            r = client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
        if r.status_code != 200:
            print(f"OpenAI HTTP {r.status_code}: {r.text[:500]}", file=sys.stderr)
            return 1
        data = r.json()
        items = data.get("data") or []
        first = items[0].get("id") if items else "(no models in page)"
        print(f"OK — OpenAI reachable. Sample model id: {first}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
