"""Parse ``EmailThread.routing_reason`` into primary code + structured detail (bridge until sources write codes).

Keep parsed ``detail`` keys to known review fields per category; do not accumulate arbitrary leftovers here.
"""

from __future__ import annotations

import json
import re
from typing import Any

_QR_TAIL = re.compile(r"\|qr_extractions=\d+$", re.IGNORECASE)


def parse_routing_reason_structured(raw: str | None) -> tuple[str | None, dict[str, Any]]:
    """
    First ``|`` segment = ``primary_code`` (stable machine id). Remaining segments as ``k=v`` → detail dict.

    Always includes ``routing_reason_full`` when raw is non-empty.
    """
    if not raw or not str(raw).strip():
        return None, {}
    s = str(raw).strip()
    base = _QR_TAIL.sub("", s).strip()
    parts = [p.strip() for p in base.split("|") if p.strip()]
    if not parts:
        return None, {"routing_reason_full": s}
    primary = parts[0]
    detail: dict[str, Any] = {"routing_reason_full": s}
    for seg in parts[1:]:
        if "=" in seg:
            k, _, v = seg.partition("=")
            detail[k.strip()] = v.strip()
        else:
            detail.setdefault("extra_segments", []).append(seg)
    return primary, detail


def detail_json_normalized(d: dict[str, Any] | None) -> str:
    if not d:
        return "{}"
    return json.dumps(d, sort_keys=True, default=str)
