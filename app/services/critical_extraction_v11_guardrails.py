"""Deterministic post-AI rules for `CriticalExtractionV11Root` (contract v1.1)."""

from __future__ import annotations

import re
from typing import Any

from app.schemas.critical_extraction_v11 import (
    CriticalBrokerLoadReference,
    CriticalExtractionV11Root,
    CriticalReferenceNumberItem,
    CriticalStopV11,
)

# Instruction-like / non-reference tokens (case-insensitive).
_FORBIDDEN_BROKER_REF_TOKENS = frozenset(
    {
        "yes",
        "no",
        "true",
        "false",
        "relates",
        "will",
        "must",
        "shall",
        "required",
        "information",
        "shipment",
        "optional",
    }
)

# If source text suggests broker/bill/corporate/remit, not a driver stop.
_BAD_STOP_SOURCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(bill\s*to|remit(?:tance)?|payment|invoice|mailing|corporate|broker\s*office|"
        r"carrier\s*address|factoring|accounts\s*receivable|ach\s*info)\b",
        re.IGNORECASE,
    ),
)


def _has_digit(s: str) -> bool:
    return bool(re.search(r"\d", s))


def _looks_like_phone_or_mc(s: str) -> bool:
    t = s.strip()
    if re.match(r"^[\d\s().+\-x]{7,30}$", t):
        return True
    if re.match(r"^(?:MC|DOT)[\s#:-]*\d{4,8}$", t, re.IGNORECASE):
        return True
    return False


def _append_reason(existing: str | None, addition: str) -> str:
    a = addition.strip()
    e = (existing or "").strip()
    if not e:
        return a
    if a in e:
        return e
    return f"{e} {a}".strip()


def _sanitize_broker_load_reference(
    blr: CriticalBrokerLoadReference,
) -> tuple[CriticalBrokerLoadReference, list[str]]:
    log: list[str] = []
    d = blr.model_dump()
    v = (d.get("value") or "").strip() if isinstance(d.get("value"), str) else ""
    if not v:
        return blr, log

    v_lower = v.casefold()
    token = re.sub(r"[^a-z0-9]+", "", v_lower)
    single_word = " " not in v.strip() and len(v.split()) == 1

    if v_lower in _FORBIDDEN_BROKER_REF_TOKENS or (single_word and token in _FORBIDDEN_BROKER_REF_TOKENS):
        d["value"] = None
        d["needs_review"] = True
        d["reason"] = _append_reason(
            d.get("reason") if isinstance(d.get("reason"), str) else None,
            "guardrail: rejected instruction-like broker_load_reference token",
        )
        log.append("broker_load_reference: cleared (forbidden token)")
    elif not _has_digit(v):
        d["value"] = None
        d["needs_review"] = True
        d["reason"] = _append_reason(
            d.get("reason") if isinstance(d.get("reason"), str) else None,
            "guardrail: broker_load_reference must include at least one digit (no learned mapping) — cleared",
        )
        log.append("broker_load_reference: cleared (no digit)")
    elif _looks_like_phone_or_mc(v):
        d["value"] = None
        d["needs_review"] = True
        d["reason"] = _append_reason(
            d.get("reason") if isinstance(d.get("reason"), str) else None,
            "guardrail: value looks like phone or authority number — cleared",
        )
        log.append("broker_load_reference: cleared (phone/authority-shaped)")

    # Re-read value after possible clears
    v2 = (d.get("value") or "").strip() if isinstance(d.get("value"), str) else ""
    c_low = str(d.get("confidence") or "").strip().casefold()
    if v2 and c_low == "low":
        d["value"] = None
        d["needs_review"] = True
        d["reason"] = _append_reason(
            d.get("reason") if isinstance(d.get("reason"), str) else None,
            "guardrail: low confidence — return null, not a weak guess",
        )
        log.append("broker_load_reference: cleared (low confidence)")

    return CriticalBrokerLoadReference.model_validate(d), log


def apply_critical_extraction_v11_guardrails(
    root: CriticalExtractionV11Root,
    *,
    raw_text: str = "",
) -> tuple[CriticalExtractionV11Root, list[str]]:
    """
    Returns (possibly-mutated root, human-readable guardrail log lines for diagnostics).
    """
    log: list[str] = []
    _ = (raw_text or "")[:200000]  # reserved for future text-pinned checks

    blr, lg = _sanitize_broker_load_reference(root.broker_load_reference)
    log.extend(lg)
    root = root.model_copy(update={"broker_load_reference": blr})

    # --- stops: mark review if source looks like non-stop section ---
    new_stops: list[CriticalStopV11] = []
    for s in root.stops:
        ss = s.source_section or ""
        stx = s.source_text or ""
        combined = f"{ss}\n{stx}"
        if combined.strip() and any(p.search(combined) for p in _BAD_STOP_SOURCE_PATTERNS):
            s = s.model_copy(
                update={
                    "needs_review": True,
                    "reason": (s.reason or "")
                    + "; guardrail: source may be bill-to/remit/corporate — verify not used as stop",
                }
            )
            log.append(f"stops[{s.stop_sequence}]: flagged (bad section heuristic)")
        aq = (s.address_quality or "").strip().casefold()
        if aq == "partial" and s.needs_review is not True:
            s = s.model_copy(update={"needs_review": True})
            log.append(f"stops[{s.stop_sequence}]: needs_review (partial address)")
        if not (s.street or "").strip() and ((s.city or "").strip() or (s.state_province or "").strip()):
            s = s.model_copy(
                update={
                    "address_quality": s.address_quality or "partial",
                    "needs_review": True,
                }
            )
        # Normalize reference_numbers: drop empty items
        refs: list[CriticalReferenceNumberItem] = []
        for r in s.reference_numbers:
            if (r.value or "").strip() or (r.label or "").strip():
                refs.append(r)
        s = s.model_copy(update={"reference_numbers": refs})
        new_stops.append(s)

    out = root.model_copy(
        update={
            "broker_load_reference": blr,
            "stops": new_stops,
        }
    )
    return out, log


def coercive_prune_critical_payload(obj: Any) -> dict[str, Any]:
    """Prune unknown keys; normalize minimal shapes before Pydantic validate."""
    if not isinstance(obj, dict):
        return {}
    allowed = set(CriticalExtractionV11Root.model_fields.keys())
    o: dict[str, Any] = {k: obj[k] for k in obj if k in allowed}
    return ensure_critical_subobjects(o)


def ensure_critical_subobjects(o: dict[str, Any]) -> dict[str, Any]:
    """Default missing top-level object/list keys so the model can partially fill."""
    d = dict(o)
    if d.get("critical_extraction_contract_version") is None:
        d["critical_extraction_contract_version"] = "1.1"
    for key in (
        "broker_name",
        "broker_load_reference",
        "carrier_rate_total",
        "equipment",
        "temperature_requirement",
        "commodity",
        "weight",
    ):
        if d.get(key) is None:
            d[key] = {}
    if not isinstance(d.get("stops"), list):
        d["stops"] = []
    return d
