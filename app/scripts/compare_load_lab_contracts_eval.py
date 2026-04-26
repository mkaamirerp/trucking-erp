"""
Compare `truckerjson` vs `critical_v1_1` **ai_proposed** field-learning snapshots
for the same Load Lab run(s), using `extraction_field_learning_events` only.

Run inside the API container (tenant env loaded; ALEMBIC_TENANT_DATABASE_URL required):

  set -a && . /run/secrets/truckerp.env && set +a && cd /app
  python -m app.scripts.compare_load_lab_contracts_eval --tenant-id 53 --run-ids 43

Use when both contracts have been run on the same run (two semantic passes); filter
by `response_contract` on GET field-learning or use this report so rows are not mixed.

Output: JSON with per-run field diffs and a coarse `safety_hints` object (heuristic, not a verdict).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.extraction_field_learning import (
    ORIGIN_LOAD_LAB_RUN,
    ExtractionFieldLearningEvent,
)
from app.services.extraction_field_learning import _dedupe_latest_per_field_path

RC_TRUCK = "truckerjson"
RC_CRIT = "critical_v1_1"

# Evaluation groups (for reporting) — best-effort mapping to `field_path` prefixes/suffixes.
GROUPS: dict[str, tuple[str, ...]] = {
    "broker_load_reference": ("extracted.broker_load_reference",),
    "rate": ("extracted.rate",),
    "stops_address": (
        "extracted.stops.0.street",
        "extracted.stops.0.city",
        "extracted.stops.0.state_or_province",
        "extracted.stops.0.postal_code",
        "extracted.stops.0.facility_name",
        "extracted.stops.1.street",
        "extracted.stops.1.city",
        "extracted.stops.1.state_or_province",
        "extracted.stops.1.postal_code",
        "extracted.stops.1.facility_name",
    ),
    "stops_date_time": (
        "extracted.stops.0.appointment_date",
        "extracted.stops.0.appointment_time_text",
        "extracted.stops.1.appointment_date",
        "extracted.stops.1.appointment_time_text",
    ),
    "equipment": ("extracted.equipment_type", "extracted.trailer_type"),
    "temperature": ("extracted.temperature_requirement",),
    "commodity": ("extracted.commodity",),
    "weight": ("extracted.estimated_weight",),
}


@dataclass
class HeuristicHint:
    """Loose, machine-readable hints; human review still required for “safer” claims."""

    both_null: bool
    t_null_c_set: bool
    c_null_t_set: bool
    values_equal: bool
    notes: list[str]


def _norm(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    if isinstance(v, (int, float, bool)):
        return v
    return v


def _hints(path: str, t_val: Any, c_val: Any) -> HeuristicHint:
    notes: list[str] = []
    t_n, c_n = _norm(t_val), _norm(c_val)
    both_null = t_n is None and c_n is None
    t_null = t_n is None
    c_null = c_n is None
    eq = t_n == c_n
    if "broker_load_reference" in path or path.endswith("broker_load_reference"):
        for label, s in (("T", t_n), ("C", c_n)):
            if isinstance(s, str) and s:
                alnum = re.sub(r"[^0-9A-Za-z]", "", s)
                digit_ratio = sum(1 for ch in s if ch.isdigit()) / max(len(s), 1)
                if alnum and len(alnum) < 4 and digit_ratio > 0.5:
                    notes.append(f"{label} broker_load_reference looks like a short/numeric token (review)")
    if "rate" in path and path.endswith("rate"):
        for label, v in (("T", t_n), ("C", c_n)):
            if v is not None and isinstance(v, (int, float)) and (v < 0 or v > 500000):
                notes.append(f"{label} rate out of common range (review)")
    if "stops" in path and (".city" in path or ".state_or_province" in path or ".postal" in path):
        if isinstance(t_n, str) and isinstance(c_n, str) and t_n and c_n and t_n.casefold() != c_n.casefold():
            notes.append("stop geo fields differ (compare for hallucination / OCR)")
    if not eq and not both_null and (t_n is not None) and (c_n is not None):
        notes.append("value mismatch: review for critical contract guard vs legacy parse")
    return HeuristicHint(
        both_null=both_null,
        t_null_c_set=t_null and not c_null,
        c_null_t_set=c_null and not t_null,
        values_equal=eq,
        notes=notes,
    )


async def _load_by_contract(
    db: AsyncSession, *, tenant_id: int, run_id: int, response_contract: str
) -> dict[str, Any]:
    stmt = (
        select(ExtractionFieldLearningEvent)
        .where(
            and_(
                ExtractionFieldLearningEvent.tenant_id == tenant_id,
                ExtractionFieldLearningEvent.origin_type == ORIGIN_LOAD_LAB_RUN,
                ExtractionFieldLearningEvent.origin_id == run_id,
                ExtractionFieldLearningEvent.event_kind == "ai_proposed",
                ExtractionFieldLearningEvent.response_contract == response_contract,
            )
        )
        .order_by(ExtractionFieldLearningEvent.id.desc())
    )
    r = await db.execute(stmt)
    rows = _dedupe_latest_per_field_path(list(r.scalars().all()))
    out: dict[str, Any] = {}
    for ev in rows:
        out[ev.field_path] = ev.proposed_value_json
    return out


def _group_report(
    t_map: dict[str, Any], c_map: dict[str, Any]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for gname, paths in GROUPS.items():
        fields_out: dict[str, Any] = {}
        for fp in paths:
            if fp not in t_map and fp not in c_map:
                continue
            tv, cv = t_map.get(fp), c_map.get(fp)
            fields_out[fp] = {
                "truckerjson": tv,
                "critical_v1_1": cv,
                "hints": asdict(_hints(fp, tv, cv)),
            }
        if fields_out:
            out[gname] = fields_out
    return out


async def _run_ids_for_sha(db: AsyncSession, tenant_id: int, file_sha: str) -> list[int]:
    r = await db.execute(
        text("SELECT id FROM load_lab_extraction_runs WHERE tenant_id = :t AND file_sha256 = :h ORDER BY id"),
        {"t": tenant_id, "h": file_sha},
    )
    return [int(x[0]) for x in r.fetchall()]


async def amain() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant-id", type=int, required=True)
    p.add_argument("--run-ids", type=str, help="Comma-separated e.g. 43,44")
    p.add_argument("--file-sha256", type=str, help="If set, compare all runs for this PDF (same bytes)")
    args = p.parse_args()

    url = os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not url:
        print("ALEMBIC_TENANT_DATABASE_URL is required", flush=True)
        return 1

    run_ids: list[int] = []
    if args.run_ids:
        run_ids = [int(x.strip()) for x in args.run_ids.split(",") if x.strip()]
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    if args.file_sha256:
        async with Session() as db:
            run_ids = await _run_ids_for_sha(db, args.tenant_id, args.file_sha256.strip().lower())
    if not run_ids:
        print("No run ids. Pass --run-ids or --file-sha256", flush=True)
        return 1

    report: dict[str, Any] = {"tenant_id": args.tenant_id, "runs": []}

    async with Session() as db:
        for rid in run_ids:
            t_map = await _load_by_contract(
                db, tenant_id=args.tenant_id, run_id=rid, response_contract=RC_TRUCK
            )
            c_map = await _load_by_contract(
                db, tenant_id=args.tenant_id, run_id=rid, response_contract=RC_CRIT
            )
            if not t_map and not c_map:
                report["runs"].append(
                    {
                        "run_id": rid,
                        "error": f"no {RC_TRUCK!r} or {RC_CRIT!r} ai_proposed rows; run semantic for both contracts on this run",
                    }
                )
                continue
            if not t_map:
                report["runs"].append(
                    {
                        "run_id": rid,
                        "error": f"missing {RC_TRUCK!r} snapshots; run: POST .../semantic-extract?force=true&response_contract=truckerjson",
                    }
                )
                continue
            if not c_map:
                report["runs"].append(
                    {
                        "run_id": rid,
                        "error": f"missing {RC_CRIT!r} snapshots; run: POST .../semantic-extract?force=true&response_contract=critical_v1_1",
                    }
                )
                continue
            all_fp = set(t_map) | set(c_map)
            flat = []
            for fp in sorted(all_fp):
                tv, cv = t_map.get(fp), c_map.get(fp)
                h = asdict(_hints(fp, tv, cv))
                flat.append(
                    {
                        "field_path": fp,
                        "truckerjson": tv,
                        "critical_v1_1": cv,
                        "match": h["values_equal"],
                        "hints": h,
                    }
                )
            report["runs"].append(
                {
                    "run_id": rid,
                    "field_count_compared": len(flat),
                    "by_group": _group_report(t_map, c_map),
                    "all_fields": flat,
                }
            )
    print(json.dumps(report, indent=2, default=str))
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
