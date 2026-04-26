"""Tenant-private extraction field learning: record/list events; platform pattern safety checks."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extraction_field_learning import (
    ORIGIN_LOAD_LAB_RUN,
    ExtractionFieldLearningEvent,
)
from app.models.load_lab import LoadLabExtractionRun

log = logging.getLogger(__name__)


def _ctx_contract(pr: dict[str, Any] | None) -> str | None:
    c = (pr or {}).get("context")
    if not isinstance(c, dict):
        return None
    v = c.get("load_lab_response_contract")
    return v if isinstance(v, str) else None


def parser_version_for_load_lab_run(run: LoadLabExtractionRun) -> str:
    parts = [
        run.parser_version or "",
        run.semantic_schema_version or "",
        run.schema_version or "",
    ]
    return "|".join(p for p in parts if p)[:120] or "unknown"


def _extract_paths(extracted: dict[str, Any]) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = [
        ("extracted.broker_name_snapshot", extracted.get("broker_name_snapshot")),
        ("extracted.broker_load_reference", extracted.get("broker_load_reference")),
        ("extracted.broker_contact_email_snapshot", extracted.get("broker_contact_email_snapshot")),
        ("extracted.rate", extracted.get("rate")),
        ("extracted.miles", extracted.get("miles")),
        ("extracted.estimated_weight", extracted.get("estimated_weight")),
        ("extracted.commodity", extracted.get("commodity")),
        ("extracted.temperature_requirement", extracted.get("temperature_requirement")),
        ("extracted.equipment_type", extracted.get("equipment_type")),
        ("extracted.trailer_type", extracted.get("trailer_type")),
    ]
    stops = extracted.get("stops")
    if isinstance(stops, list):
        for i, s in enumerate(stops[:4]):
            if not isinstance(s, dict):
                continue
            for k in (
                "city",
                "state_or_province",
                "postal_code",
                "facility_name",
                "stop_type",
                "street",
                "appointment_date",
                "appointment_time_text",
            ):
                out.append((f"extracted.stops.{i}.{k}", s.get(k)))
    return out


def _to_jsonable(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(a): _to_jsonable(b) for a, b in list(v.items())[:80]}
    if isinstance(v, (list, tuple)):
        return [_to_jsonable(x) for x in v[:50]]
    return str(v)[:2000]


async def record_extraction_field_learning_load_lab_ai_snapshot(
    db: AsyncSession,
    *,
    tenant_id: int,
    run: LoadLabExtractionRun,
    parse_response: dict[str, Any] | None,
) -> None:
    """
    `ai_proposed` rows: proposed_value_json set, final_value_json null (until operator confirms elsewhere).
    """
    if not parse_response or not isinstance(parse_response, dict):
        return
    ex = parse_response.get("extracted")
    if not isinstance(ex, dict):
        return
    contract = _ctx_contract(parse_response) or "truckerjson"
    meta: dict[str, Any] = {
        "semantic_schema_version": run.semantic_schema_version,
        "semantic_prompt_version": run.semantic_prompt_version,
    }
    pd = parse_response.get("parse_diagnostics")
    if isinstance(pd, dict) and "critical_extraction_v1_1_guardrails" in pd:
        meta["guardrail_count"] = len(pd.get("critical_extraction_v1_1_guardrails") or [])

    pv = parser_version_for_load_lab_run(run)
    for field_path, raw in _extract_paths(ex):
        db.add(
            ExtractionFieldLearningEvent(
                tenant_id=tenant_id,
                origin_type=ORIGIN_LOAD_LAB_RUN,
                origin_id=run.id,
                field_path=field_path,
                event_kind="ai_proposed",
                proposed_value_json=_to_jsonable(raw),
                final_value_json=None,
                previous_value_json=None,
                source_label=None,
                source_section=None,
                source_text=None,
                source_page=None,
                response_contract=contract,
                parser_version=pv,
                correction_type=None,
                event_meta=meta,
                actor_user_id=run.created_by_platform_user_id,
            )
        )
    try:
        await db.flush()
    except Exception:  # noqa: BLE001
        log.exception("extraction field learning (load lab AI snapshot) flush failed (non-fatal)")


async def record_extraction_field_learning_operator_event(
    db: AsyncSession,
    *,
    tenant_id: int,
    origin_type: str,
    origin_id: int,
    platform_user_id: str,
    field_path: str,
    final_value_json: Any,
    proposed_value_json: Any | None = None,
    previous_value_json: Any | None = None,
    source_text: str | None = None,
    source_page: int | None = None,
    source_label: str | None = None,
    source_section: str | None = None,
    correction_type: str = "operator_override",
    response_contract: str | None = None,
    parser_version: str | None = None,
) -> ExtractionFieldLearningEvent:
    ev = ExtractionFieldLearningEvent(
        tenant_id=tenant_id,
        origin_type=origin_type[:32],
        origin_id=origin_id,
        field_path=field_path[:512],
        event_kind="operator_override",
        proposed_value_json=_to_jsonable(proposed_value_json) if proposed_value_json is not None else None,
        final_value_json=_to_jsonable(final_value_json),
        previous_value_json=_to_jsonable(previous_value_json) if previous_value_json is not None else None,
        source_label=source_label[:256] if source_label else None,
        source_section=source_section[:256] if source_section else None,
        source_text=source_text,
        source_page=source_page,
        response_contract=response_contract[:64] if response_contract else None,
        parser_version=parser_version[:128] if parser_version else None,
        correction_type=correction_type[:32],
        event_meta=None,
        actor_user_id=platform_user_id,
    )
    db.add(ev)
    await db.flush()
    return ev


def _dedupe_latest_per_field_path(rows: list[ExtractionFieldLearningEvent]) -> list[ExtractionFieldLearningEvent]:
    """Rows must be ordered by id desc; keep the first (newest) row per field_path."""
    seen: set[str] = set()
    out: list[ExtractionFieldLearningEvent] = []
    for ev in rows:
        if ev.field_path in seen:
            continue
        seen.add(ev.field_path)
        out.append(ev)
    return out


async def list_extraction_field_learning_by_origin(
    db: AsyncSession,
    *,
    tenant_id: int,
    origin_type: str,
    origin_id: int,
    limit: int = 200,
    response_contract: str | None = None,
    dedupe_latest_per_field_path: bool = False,
) -> list[ExtractionFieldLearningEvent]:
    stmt = select(ExtractionFieldLearningEvent).where(
        ExtractionFieldLearningEvent.tenant_id == tenant_id,
        ExtractionFieldLearningEvent.origin_type == origin_type,
        ExtractionFieldLearningEvent.origin_id == origin_id,
    )
    if response_contract is not None and str(response_contract).strip():
        rc = str(response_contract).strip()
        stmt = stmt.where(ExtractionFieldLearningEvent.response_contract == rc)
    stmt = stmt.order_by(ExtractionFieldLearningEvent.id.desc())
    cap = 500 if dedupe_latest_per_field_path else max(1, min(limit, 500))
    stmt = stmt.limit(cap)
    r = await db.execute(stmt)
    rows = list(r.scalars().all())
    if dedupe_latest_per_field_path:
        rows = _dedupe_latest_per_field_path(rows)
        rows = rows[: max(1, min(limit, 500))]
    return rows


# --- platform upsert safety (no tenant values in free-text) ---

EMAILISH = re.compile(r"[a-z0-9._%+-]@[a-z0-9.-]", re.IGNORECASE)
STREETISH = re.compile(r"\b\d{2,5}\s+[A-Za-z]{2,20}\s+(st|ave|blvd|rd|dr|ln|ct)\b", re.IGNORECASE)


def sanitized_pattern_looks_unsafe(
    broker_family_key: str,
    source_label_pattern: str,
    source_section_pattern: str,
    notes: str | None = None,
) -> str | None:
    for s in (broker_family_key, source_label_pattern, source_section_pattern, notes or ""):
        if not s or not str(s).strip():
            continue
        if EMAILISH.search(s):
            return "pattern or notes look like an email/address; store structural tokens only"
        if STREETISH.search(s):
            return "pattern looks like a street address; use section_role / structural keys only"
    if len(broker_family_key) > 120:
        return "broker_family_key too long (possible pasted blob)"
    return None
