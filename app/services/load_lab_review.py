"""Load Lab v3 — heuristic confidence + contradiction flags (lab only, no operational writes).

Design goals:
- Grounding checks: non-null scalar values should appear in normalized source text (loosely) or we label low/unknown.
- Contradictions: simple regex / structural checks on (raw text, candidate JSON) only — no ML.
- Prefer ``unknown`` / ``review_required`` over overconfident labels.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.load_lab import LoadLabExtractionRun
from app.schemas.load_document_parse import LoadDocumentParseResponse, LoadParseExtractedFields, LoadParseStopItem

REVIEW_ENGINE_VERSION = "load_lab_review_heuristic_v1"

ConfidenceLevel = Literal["unknown", "low", "medium", "high"]
ReviewStatus = Literal["not_applicable", "candidate_ok", "review_required", "blocked"]

def _digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _in_text(raw: str, needle: str | None, *, min_len: int = 3) -> bool:
    if not needle or len(needle.strip()) < min_len:
        return False
    return _norm_ws(needle) in _norm_ws(raw)


def _in_text_digits(raw: str, needle: str | None) -> bool:
    d = _digits(needle or "")
    if len(d) < 7:
        return False
    return d in _digits(raw)


def _money_floats_in_text(raw: str) -> list[float]:
    """Distinct dollar-like amounts (coarse; lab heuristic only)."""
    out: list[float] = []
    for m in re.finditer(r"\$\s*([\d,]+(?:\.\d{1,2})?)", raw):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    # de-dupe near-equal
    uniq: list[float] = []
    for x in sorted(out):
        if not any(abs(x - u) / max(u, 1e-6) < 0.01 for u in uniq):
            uniq.append(x)
    return uniq


def _mc_in_text(raw: str) -> list[str]:
    return [m.group(1).upper() for m in re.finditer(r"\bMC[\s#:-]*(\d{5,8})\b", raw, re.I)]


def _dot_in_text(raw: str) -> list[str]:
    found: list[str] = []
    for m in re.finditer(r"\bDOT[\s#:-]*(\d{5,10})\b", raw, re.I):
        found.append(m.group(1))
    for m in re.finditer(r"\bUSDOT[\s#:-]*(\d{5,10})\b", raw, re.I):
        found.append(m.group(1))
    return found


def _group_block(level: ConfidenceLevel, reasons: list[str]) -> dict[str, Any]:
    return {"level": level, "reasons": reasons[:6]}


def _confidence_string_field(raw: str, val: str | None, label: str) -> dict[str, Any]:
    if not val or not str(val).strip():
        return _group_block("unknown", [f"{label} not extracted"])
    if _in_text(raw, str(val)):
        return _group_block("medium", ["Plain-text substring appears in source"])
    if _in_text_digits(raw, str(val)):
        return _group_block("medium", ["Digit sequence appears in source (e.g. phone)"])
    return _group_block("low", ["Value not found as substring in source — possible mismatch or OCR noise"])


def _confidence_money(raw: str, ex: LoadParseExtractedFields) -> dict[str, Any]:
    reasons: list[str] = []
    lows = 0
    unknowns = 0
    for name, val in (("rate", ex.rate), ("customer_rate", ex.customer_rate), ("miles", ex.miles)):
        if val is None:
            unknowns += 1
            reasons.append(f"{name} not set")
            continue
        if isinstance(val, float) and name != "miles":
            s_plain = f"{val:.2f}".rstrip("0").rstrip(".")
            s_int = f"{int(val)}" if val == int(val) else None
            raw_n = raw.replace(",", "")
            ok = s_plain in raw_n or (s_int and s_int in raw_n) or f"{val:.0f}" in raw_n
            if ok:
                reasons.append(f"{name} numeric form seen in text")
            else:
                lows += 1
                reasons.append(f"{name} set but simple numeric match not found in text")
        elif name == "miles" and isinstance(val, float):
            s = str(int(val)) if val == int(val) else f"{val:.1f}".rstrip("0").rstrip(".")
            if s in raw.replace(",", ""):
                reasons.append("miles numeric form seen in text")
            else:
                lows += 1
                reasons.append("miles set but simple match not found in text")
    if unknowns == 3:
        return _group_block("unknown", ["No money fields extracted"])
    if lows > 0:
        return _group_block("low", reasons[:5])
    return _group_block("medium", reasons[:5])


def _confidence_references(raw: str, ex: LoadParseExtractedFields) -> dict[str, Any]:
    if not ex.references:
        return _group_block("unknown", ["No reference items extracted"])
    lows = 0
    for i, ref in enumerate(ex.references):
        v = (ref.value or "").strip()
        if len(v) < 3:
            continue
        if not _in_text(raw, v, min_len=3):
            lows += 1
    if lows:
        return _group_block("low", [f"{lows} reference value(s) not found verbatim in source"])
    return _group_block("medium", ["Reference values appear in source text"])


def _confidence_stops(raw: str, stops: list[LoadParseStopItem]) -> dict[str, Any]:
    if not stops:
        return _group_block("unknown", ["No stops extracted"])
    lows = 0
    for st in stops:
        parts = [st.facility_name, st.city, st.street, st.reference_number]
        any_set = any((p or "").strip() for p in parts)
        if not any_set:
            continue
        hit = any(_in_text(raw, p, min_len=4) for p in parts if p)
        if not hit:
            lows += 1
    if lows:
        return _group_block("low", [f"{lows} stop row(s): location fields not found as substring in source"])
    return _group_block("medium", ["Stop location tokens appear in source"])


def _confidence_equipment(raw: str, ex: LoadParseExtractedFields) -> dict[str, Any]:
    fields = [
        ("mode", ex.mode),
        ("equipment_type", ex.equipment_type),
        ("trailer_type", ex.trailer_type),
        ("commodity", ex.commodity),
        ("temperature_requirement", ex.temperature_requirement),
    ]
    if not any((v or "").strip() for _, v in fields):
        return _group_block("unknown", ["No equipment fields extracted"])
    lows = 0
    for label, val in fields:
        if val and str(val).strip() and not _in_text(raw, str(val), min_len=3):
            lows += 1
    if lows:
        return _group_block("low", [f"{lows} equipment field(s) not found in source text"])
    return _group_block("medium", ["Equipment keywords appear in source"])


def _confidence_customs(raw: str, ex: LoadParseExtractedFields) -> dict[str, Any]:
    if not (ex.customs_broker_name or "").strip():
        return _group_block("unknown", ["No customs broker extracted"])
    return _confidence_string_field(raw, ex.customs_broker_name, "customs_broker_name")


def _confidence_broker_identity(raw: str, ex: LoadParseExtractedFields) -> dict[str, Any]:
    parts = [
        _confidence_string_field(raw, ex.broker_name_snapshot, "broker_name"),
        _confidence_string_field(raw, ex.broker_mc_number_snapshot, "broker_mc"),
        _confidence_string_field(raw, ex.broker_dot_number_snapshot, "broker_dot"),
    ]
    levels = [p["level"] for p in parts]
    if all(x == "unknown" for x in levels):
        return _group_block("unknown", ["No broker identity fields extracted"])
    if "low" in levels:
        return _group_block("low", [r for p in parts for r in p.get("reasons", [])][:5])
    return _group_block("medium", ["Broker identity fields partially grounded in source"])


def _confidence_broker_contact(raw: str, ex: LoadParseExtractedFields) -> dict[str, Any]:
    parts = [
        _confidence_string_field(raw, ex.broker_contact_name_snapshot, "contact_name"),
        _confidence_string_field(raw, ex.broker_contact_phone_snapshot, "contact_phone"),
        _confidence_string_field(raw, ex.broker_contact_email_snapshot, "contact_email"),
    ]
    levels = [p["level"] for p in parts]
    if all(x == "unknown" for x in levels):
        return _group_block("unknown", ["No broker contact extracted"])
    if "low" in levels:
        return _group_block("low", [r for p in parts for r in p.get("reasons", [])][:5])
    return _group_block("medium", ["Broker contact fields partially grounded in text"])


def _document_confidence(groups: dict[str, dict[str, Any]]) -> dict[str, Any]:
    levels = [g["level"] for g in groups.values()]
    if all(l == "unknown" for l in levels):
        return _group_block("unknown", ["No extracted groups to evaluate"])
    if "low" in levels:
        return _group_block("low", ["At least one group has low text grounding"])
    if "medium" in levels:
        return _group_block("medium", ["Extracted values largely appear in source (heuristic)"])
    return _group_block("unknown", ["Insufficient signal for document-level confidence"])


def _detect_contradictions(raw: str, ex: LoadParseExtractedFields) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []

    money_vals = _money_floats_in_text(raw)
    if ex.rate is not None and len(money_vals) >= 3:
        close = [m for m in money_vals if abs(m - float(ex.rate)) / max(float(ex.rate), 1e-6) < 0.02]
        if len(close) == 1 and len(money_vals) >= 3:
            flags.append(
                {
                    "id": "multiple_money_amounts_in_text",
                    "severity": "warning",
                    "detail": f"Source shows {len(money_vals)} distinct dollar-like amounts; extracted rate matches one — verify total vs line haul vs fuel.",
                }
            )

    # Reference-like density (very coarse)
    ref_like = len(re.findall(r"\b(?:PRO|PO|REF|BOL|LOAD)\s*[#:]?\s*[A-Z0-9]{4,}\b", raw, re.I))
    if ref_like >= 4 and len(ex.references) < 2:
        flags.append(
            {
                "id": "sparse_reference_capture",
                "severity": "info",
                "detail": "Many reference-like tokens in text but few structured references extracted.",
            }
        )

    # Stops
    stops = ex.stops
    if stops:
        seqs = [s.sequence for s in stops]
        if sorted(seqs) != list(range(len(stops))) or len(set(seqs)) != len(seqs):
            flags.append(
                {
                    "id": "stop_sequence_irregular",
                    "severity": "warning",
                    "detail": "Stop sequence numbers are not a clean 0..n-1 permutation.",
                }
            )
        types = [s.stop_type for s in sorted(stops, key=lambda x: x.sequence)]
        if "pickup" in types and "delivery" in types:
            fi = types.index("pickup")
            li = types.index("delivery")
            if fi > li:
                flags.append(
                    {
                        "id": "pickup_after_delivery",
                        "severity": "warning",
                        "detail": "A pickup stop is ordered after a delivery stop by sequence.",
                    }
                )
        if len(stops) == 1:
            flags.append(
                {
                    "id": "single_stop_only",
                    "severity": "info",
                    "detail": "Only one stop extracted — typical rate cons have pickup + delivery.",
                }
            )

    # Broker MC / DOT vs text
    mc_cand = (ex.broker_mc_number_snapshot or "").replace("-", "").replace(" ", "").upper()
    if mc_cand:
        text_mcs = _mc_in_text(raw)
        norm_c = re.sub(r"\D", "", mc_cand)
        if text_mcs and all(re.sub(r"\D", "", t) != norm_c for t in text_mcs):
            flags.append(
                {
                    "id": "broker_mc_mismatch",
                    "severity": "error",
                    "detail": "Extracted MC number does not match MC tokens found in source text.",
                }
            )

    dot_cand = re.sub(r"\D", "", ex.broker_dot_number_snapshot or "")
    if len(dot_cand) >= 6:
        text_dots = _dot_in_text(raw)
        if text_dots and all(d != dot_cand for d in text_dots):
            flags.append(
                {
                    "id": "broker_dot_mismatch",
                    "severity": "error",
                    "detail": "Extracted DOT number does not match DOT/USDOT tokens found in source text.",
                }
            )

    # Competing rate-like in extracted (rare)
    if ex.rate is not None and ex.customer_rate is not None and ex.rate > 0 and ex.customer_rate > 0:
        if abs(ex.rate - ex.customer_rate) / max(ex.rate, ex.customer_rate) > 0.5:
            flags.append(
                {
                    "id": "rate_and_customer_rate_diverge",
                    "severity": "warning",
                    "detail": "rate and customer_rate differ by more than 50% — verify which is carrier pay.",
                }
            )

    return flags


def _any_group_low_with_data(groups: dict[str, dict[str, Any]], ex: LoadParseExtractedFields) -> bool:
    """True if a group marked low still has user-visible extracted data (should review)."""
    if groups.get("money", {}).get("level") == "low" and (
        ex.rate is not None or ex.customer_rate is not None or ex.miles is not None
    ):
        return True
    if groups.get("references", {}).get("level") == "low" and ex.references:
        return True
    if groups.get("stops", {}).get("level") == "low" and ex.stops:
        return True
    if groups.get("equipment", {}).get("level") == "low" and any(
        [ex.mode, ex.equipment_type, ex.trailer_type, ex.commodity, ex.temperature_requirement]
    ):
        return True
    if groups.get("broker_identity", {}).get("level") == "low" and any(
        [ex.broker_name_snapshot, ex.broker_mc_number_snapshot, ex.broker_dot_number_snapshot]
    ):
        return True
    if groups.get("broker_contact", {}).get("level") == "low" and any(
        [ex.broker_contact_name_snapshot, ex.broker_contact_phone_snapshot, ex.broker_contact_email_snapshot]
    ):
        return True
    if groups.get("customs", {}).get("level") == "low" and (ex.customs_broker_name or "").strip():
        return True
    return False


def _decide_review_status(flags: list[dict[str, Any]], groups: dict[str, dict[str, Any]], ex: LoadParseExtractedFields) -> ReviewStatus:
    sev = [f.get("severity") for f in flags]
    if "error" in sev:
        return "blocked"
    if "warning" in sev:
        return "review_required"
    if _any_group_low_with_data(groups, ex):
        return "review_required"
    if groups.get("document", {}).get("level") == "low":
        return "review_required"
    return "candidate_ok"


def _build_summary(status: ReviewStatus, flags: list[dict[str, Any]], groups: dict[str, dict[str, Any]]) -> str:
    parts = [f"Review: {status}", f"engine={REVIEW_ENGINE_VERSION}"]
    if flags:
        parts.append(f"{len(flags)} contradiction flag(s)")
    low_groups = [k for k, v in groups.items() if k != "document" and v.get("level") == "low"]
    if low_groups:
        parts.append(f"low grounding: {', '.join(low_groups)}")
    return "; ".join(parts)[:2000]


def build_lab_review_payload(raw_text: str, parsed: LoadDocumentParseResponse) -> dict[str, Any]:
    """Pure function for tests and batch use."""
    ex = parsed.extracted
    groups = {
        "broker_identity": _confidence_broker_identity(raw_text, ex),
        "broker_contact": _confidence_broker_contact(raw_text, ex),
        "references": _confidence_references(raw_text, ex),
        "equipment": _confidence_equipment(raw_text, ex),
        "money": _confidence_money(raw_text, ex),
        "stops": _confidence_stops(raw_text, ex.stops),
        "customs": _confidence_customs(raw_text, ex),
    }
    groups["document"] = _document_confidence({k: v for k, v in groups.items() if k != "document"})
    flags = _detect_contradictions(raw_text, ex)
    status = _decide_review_status(flags, groups, ex)
    summary = _build_summary(status, flags, groups)
    confidence = {
        "engine_version": REVIEW_ENGINE_VERSION,
        "document": groups["document"],
        "groups": {k: v for k, v in groups.items() if k != "document"},
        "review_summary": summary,
    }
    return {"confidence": confidence, "contradictions": flags, "lab_review_status": status, "lab_review_summary": summary}


def clear_lab_review_on_run(run: LoadLabExtractionRun) -> None:
    run.lab_confidence = None
    run.lab_review_status = "not_applicable"
    run.lab_review_summary = None
    run.contradictions = None


def clear_lab_review_if_no_candidate(run: LoadLabExtractionRun) -> None:
    """Drop v3 fields when there is no persisted candidate JSON."""
    if run.parse_response is None:
        clear_lab_review_on_run(run)


def attach_lab_review_to_run(run: LoadLabExtractionRun) -> None:
    """Mutate run with v3 fields; caller commits. Expects parse_response set."""
    raw = run.normalized_package or {}
    raw_text = raw.get("raw_full_text") if isinstance(raw.get("raw_full_text"), str) else ""
    if not run.parse_response:
        clear_lab_review_on_run(run)
        return
    try:
        parsed = LoadDocumentParseResponse.model_validate(run.parse_response)
    except Exception:  # noqa: BLE001
        run.lab_confidence = {
            "engine_version": REVIEW_ENGINE_VERSION,
            "document": _group_block("unknown", ["parse_response failed validation"]),
            "groups": {},
            "review_summary": "Review skipped: invalid parse_response",
        }
        run.contradictions = [
            {"id": "invalid_parse_response", "severity": "error", "detail": "Candidate JSON did not validate as LoadDocumentParseResponse."}
        ]
        run.lab_review_status = "blocked"
        run.lab_review_summary = run.lab_confidence["review_summary"]
        return

    payload = build_lab_review_payload(raw_text, parsed)
    run.lab_confidence = payload["confidence"]
    run.contradictions = payload["contradictions"]
    run.lab_review_status = payload["lab_review_status"]
    run.lab_review_summary = payload["lab_review_summary"]


def strip_lab_review_warning_prefixes(warnings: list[Any] | None) -> list[Any]:
    if not warnings:
        return []
    return [w for w in warnings if not (isinstance(w, str) and w.startswith("[lab_review]"))]


def strip_semantic_warning_prefixes(warnings: list[Any] | None) -> list[Any]:
    if not warnings:
        return []
    return [w for w in warnings if not (isinstance(w, str) and w.startswith("[semantic]"))]


def warning_base_without_semantic_or_lab_review(warnings: list[Any] | None) -> list[Any]:
    return strip_lab_review_warning_prefixes(strip_semantic_warning_prefixes(warnings))


async def recompute_lab_review_for_run(
    db: AsyncSession,
    *,
    tenant_id: int,
    run_id: int,
) -> LoadLabExtractionRun | None:
    """Re-run v3 heuristics from current parse_response + normalized text (no OpenAI)."""
    from app.services import load_lab as load_lab_v1

    run = await load_lab_v1.get_run(db, tenant_id, run_id)
    if run is None:
        return None
    preserved_semantic = [w for w in (run.warnings or []) if isinstance(w, str) and w.startswith("[semantic]")]
    base = warning_base_without_semantic_or_lab_review(run.warnings)
    attach_lab_review_to_run(run)
    merge_lab_review_warnings(run, base + preserved_semantic)
    run.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


def merge_lab_review_warnings(run: LoadLabExtractionRun, base: list[Any]) -> None:
    """Append a single summary line for operators (optional duplicate of lab_review_summary)."""
    summary = run.lab_review_summary
    status = run.lab_review_status
    if summary and status and status not in ("not_applicable", None, ""):
        line = f"[lab_review] {status}: {summary[:400]}"
        run.warnings = list(base) + [line]
        return
    run.warnings = list(base)
