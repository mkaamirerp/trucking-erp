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


def _looks_like_phone_or_authority_not_load_ref(s: str) -> bool:
    """
    Reject *only* values that are clearly a phone, fax, or MC/DOT line — not long numeric
    load/PO/EL reference IDs. The previous `[\d\-]{7,30}`-style test incorrectly nulled
    high-value fields like 34307972, 25180652398968, and 3872125-1.
    """
    t = s.strip()
    if not t:
        return False
    if re.match(r"^(?:MC|DOT|USDOT)\s*[#:]*\s*\d{4,8}$", t, re.IGNORECASE):
        return True
    digits = re.sub(r"[^\d]", "", t)
    if 4 <= len(digits) <= 24 and "(" not in t and "+" not in t:
        if re.fullmatch(r"[\dA-Za-z\-\#\/\.\,]+", t) or re.fullmatch(r"[\d\-]+", t):
            return False
    if re.search(r"\(\d{3}\)\s*[\d\-\s]{6,12}\d{4}", t) or re.search(
        r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", t
    ):
        if re.search(r"[\s().+\-x]", t) and 10 <= len(digits) <= 11:
            return True
    if re.match(r"^\+?\d{1,2}\s*[\d\s().\-]{7,20}$", t) and 10 <= len(digits) <= 15 and re.search(
        r"[\s().x]", t
    ):
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
    elif _looks_like_phone_or_authority_not_load_ref(v):
        d["value"] = None
        d["needs_review"] = True
        d["reason"] = _append_reason(
            d.get("reason") if isinstance(d.get("reason"), str) else None,
            "guardrail: value looks like phone or authority number — cleared",
        )
        log.append("broker_load_reference: cleared (phone/authority-shaped)")

    # Re-read value after possible clears. Do *not* clear when model confidence is "low" —
    # digit-heavy refs are still useful for dispatch; `needs_review` is enough (schema default).
    v2 = (d.get("value") or "").strip() if isinstance(d.get("value"), str) else ""
    c_low = str(d.get("confidence") or "").strip().casefold()
    if v2 and c_low == "low":
        d["needs_review"] = True
        d["reason"] = _append_reason(
            d.get("reason") if isinstance(d.get("reason"), str) else None,
            "note: model confidence low; keep value for review (not cleared by guardrails)",
        )
        log.append("broker_load_reference: kept (low model confidence; needs_review)")

    return CriticalBrokerLoadReference.model_validate(d), log


def apply_critical_extraction_v11_guardrails(
    root: CriticalExtractionV11Root,
    *,
    raw_text: str = "",
) -> tuple[CriticalExtractionV11Root, list[str], dict[str, Any]]:
    """
    Returns (possibly-mutated root, guardrail log lines, small diagnostics for parse_diagnostics).
    """
    log: list[str] = []
    _ = (raw_text or "")[:200000]  # reserved for future text-pinned checks
    pre_blr = root.broker_load_reference.model_dump(mode="json")

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
    trace = {
        "broker_load_reference": {
            "model_before_sanitize": pre_blr,
            "after_sanitize": blr.model_dump(mode="json"),
            "guardrail_lines": list(lg),
        }
    }
    return out, log, trace


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
