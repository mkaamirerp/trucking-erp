"""
Load Lab — 6-PDF evaluation harness (Phase 4).

Inputs:
- expected JSON fixtures (workspace-facing parse_response shape, or selected fields)
- run_ids to evaluate

Outputs:
- field-by-field mismatches
- categorized failure buckets:
  - booking_broker_wrong
  - customs_collapsed_into_booking
  - primary_reference_wrong
  - decimal_reference_confusion
  - stop_extraction_drift
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy import select

from app.deps.tenant_db import open_tenant_session_by_id
from app.models.load_lab import LoadLabExtractionRun


DEFAULT_FIELDS = [
    ("extracted.broker_name_snapshot",),
    ("extracted.customs_broker_name",),
    ("extracted.broker_load_reference",),
    ("extracted.broker_mc_number_snapshot",),
]


def _get(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _norm(v: Any) -> Any:
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return v


def _norm_broker_name(s: str | None) -> str | None:
    if not isinstance(s, str):
        return None
    t = s.strip().casefold()
    if not t:
        return None
    # Remove common legal suffixes / punctuation for normalization-only comparisons.
    for x in ("capacity solutions", "llc", "l.l.c", "inc", "inc.", "corp", "corp.", "corporation", "company", "co.", ","):
        t = t.replace(x, " ")
    t = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in t)
    t = " ".join(t.split())
    return t or None


def _categorize(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    cats: list[str] = []
    eb = _norm(_get(expected, "extracted.broker_name_snapshot"))
    ab = _norm(_get(actual, "extracted.broker_name_snapshot"))
    if eb != ab:
        # If the only difference is display-name normalization, don't count as a true identity failure.
        neb = _norm_broker_name(eb) if isinstance(eb, str) else None
        nab = _norm_broker_name(ab) if isinstance(ab, str) else None
        if neb and nab and neb == nab:
            cats.append("broker_name_normalization_only")
        else:
            cats.append("booking_broker_wrong")

    ec = _norm(_get(expected, "extracted.customs_broker_name"))
    ac = _norm(_get(actual, "extracted.customs_broker_name"))
    if ec != ac and ac and ab and ac == ab:
        cats.append("customs_collapsed_into_booking")

    er = _norm(_get(expected, "extracted.broker_load_reference"))
    ar = _norm(_get(actual, "extracted.broker_load_reference"))
    if er != ar:
        cats.append("primary_reference_wrong")

    # Trailer mapping
    if isinstance(_get(expected, "extracted"), dict) and "trailer_type" in (_get(expected, "extracted") or {}):
        et = _norm(_get(expected, "extracted.trailer_type"))
        at = _norm(_get(actual, "extracted.trailer_type"))
        if et != at:
            cats.append("trailer_type_wrong")
    if isinstance(_get(expected, "extracted"), dict) and "trailer_size" in (_get(expected, "extracted") or {}):
        esz = _norm(_get(expected, "extracted.trailer_size"))
        asz = _norm(_get(actual, "extracted.trailer_size"))
        if esz != asz:
            cats.append("trailer_size_wrong")

    # Temperature label-vs-value
    if isinstance(_get(expected, "extracted"), dict) and "temperature_requirement" in (_get(expected, "extracted") or {}):
        etmp = _norm(_get(expected, "extracted.temperature_requirement"))
        atmp = _norm(_get(actual, "extracted.temperature_requirement"))
        if etmp != atmp:
            cats.append("temperature_requirement_wrong")

    # decimal/reference confusion
    if isinstance(ar, str) and "." in ar and any(ch.isdigit() for ch in ar):
        cats.append("decimal_reference_confusion")

    # stops drift (very coarse)
    es = _get(expected, "extracted.stops")
    a_s = _get(actual, "extracted.stops")
    if isinstance(es, list):
        if not isinstance(a_s, list):
            cats.append("stop_missing")
        else:
            if len(es) != len(a_s):
                cats.append("stop_count_wrong")
            exp_types = [(_norm((x or {}).get("stop_type")) if isinstance(x, dict) else None) for x in es]
            act_types = [(_norm((x or {}).get("stop_type")) if isinstance(x, dict) else None) for x in a_s]
            if exp_types != act_types:
                cats.append("stop_types_wrong")
            if es and a_s and isinstance(es[0], dict) and isinstance(a_s[0], dict):
                if _norm(es[0].get("city")) != _norm(a_s[0].get("city")) or _norm(es[0].get("state_or_province")) != _norm(a_s[0].get("state_or_province")):
                    cats.append("stop_first_location_wrong")
            if es and a_s and isinstance(es[-1], dict) and isinstance(a_s[-1], dict):
                if _norm(es[-1].get("city")) != _norm(a_s[-1].get("city")) or _norm(es[-1].get("state_or_province")) != _norm(a_s[-1].get("state_or_province")):
                    cats.append("stop_last_location_wrong")

            # Appointment normalization checks (per-stop)
            def _appt_pair(st: dict[str, Any]) -> tuple[Any, Any]:
                return (_norm(st.get("appointment_type")), _norm(st.get("appointment_time_text")))

            for idx, (e, a) in enumerate(zip(es, a_s)):
                if not isinstance(e, dict) or not isinstance(a, dict):
                    continue
                if _appt_pair(e) != _appt_pair(a):
                    cats.append("appointment_fields_wrong")
                    break
                # per-stop basics
                for f in ("facility_name", "city", "state_or_province", "appointment_date", "appointment_time_text"):
                    if f in e and _norm(e.get(f)) != _norm(a.get(f)):
                        cats.append("stop_fields_wrong")
                        break
            cats = sorted(set(cats))

    return sorted(set(cats))


@dataclass
class DiffRow:
    field: str
    expected: Any
    actual: Any


def _diff(expected: dict[str, Any], actual: dict[str, Any], fields: list[str]) -> list[DiffRow]:
    out: list[DiffRow] = []
    for f in fields:
        ev = _norm(_get(expected, f))
        av = _norm(_get(actual, f))
        if ev != av:
            out.append(DiffRow(field=f, expected=ev, actual=av))
    return out


def _stop_diff(expected: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, Any]]:
    es = _get(expected, "extracted.stops")
    a_s = _get(actual, "extracted.stops")
    if not isinstance(es, list) or not isinstance(a_s, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, (e, a) in enumerate(zip(es, a_s)):
        if not isinstance(e, dict) or not isinstance(a, dict):
            continue
        for f in ("stop_type", "facility_name", "city", "state_or_province", "appointment_date", "appointment_type", "appointment_time_text"):
            if f in e and _norm(e.get(f)) != _norm(a.get(f)):
                out.append(
                    {
                        "stop_index": idx,
                        "field": f,
                        "expected": _norm(e.get(f)),
                        "actual": _norm(a.get(f)),
                    }
                )
    return out[:40]


async def _load_run_parse_response(tenant_id: int, run_id: int) -> dict[str, Any] | None:
    async for db in open_tenant_session_by_id(tenant_id):
        pr = (
            await db.execute(
                select(LoadLabExtractionRun.parse_response)
                .where(LoadLabExtractionRun.tenant_id == tenant_id)
                .where(LoadLabExtractionRun.id == run_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        return pr if isinstance(pr, dict) else None
    return None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant-id", type=int, required=True)
    ap.add_argument("--expected", type=str, required=True, help="Path to expected fixtures JSON")
    ap.add_argument("--run-ids", type=str, required=True, help="Comma-separated LoadLabExtractionRun IDs")
    ap.add_argument(
        "--fields",
        type=str,
        default="extracted.broker_name_snapshot,extracted.customs_broker_name,extracted.broker_load_reference",
        help="Comma-separated dotted fields to compare",
    )
    args = ap.parse_args()

    expected_path = Path(args.expected)
    expected_data = json.loads(expected_path.read_text())
    if not isinstance(expected_data, dict):
        raise SystemExit("expected JSON must be an object keyed by run_id (string) or filename")

    run_ids = [int(x.strip()) for x in args.run_ids.split(",") if x.strip()]
    fields = [x.strip() for x in args.fields.split(",") if x.strip()]

    summary: dict[str, Any] = {"runs": [], "category_counts": {}}

    for rid in run_ids:
        key = str(rid)
        exp = expected_data.get(key)
        if not isinstance(exp, dict):
            summary["runs"].append({"run_id": rid, "error": "missing_expected_fixture"})
            continue

        act = await _load_run_parse_response(args.tenant_id, rid)
        if not act:
            summary["runs"].append({"run_id": rid, "error": "missing_parse_response"})
            continue

        diffs = _diff(exp, act, fields)
        cats = _categorize(exp, act)
        for c in cats:
            summary["category_counts"][c] = int(summary["category_counts"].get(c) or 0) + 1

        summary["runs"].append(
            {
                "run_id": rid,
                "categories": cats,
                "diffs": [{"field": d.field, "expected": d.expected, "actual": d.actual} for d in diffs],
                "stop_diffs": _stop_diff(exp, act),
            }
        )

    print(json.dumps(summary, indent=2)[:20000])
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))

