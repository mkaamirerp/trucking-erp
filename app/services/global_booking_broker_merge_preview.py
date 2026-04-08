"""Global booking broker merge preview (platform): read-only analysis + optional persisted preview row."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.global_booking_broker import GlobalBookingBroker, GlobalBookingBrokerMergePreview
from app.utils.broker_identity import (
    normalize_cvor_number_digits,
    normalize_dot_number_digits,
    normalize_mc_number_digits,
)
from app.utils import global_booking_broker_merge as merge_guard

FieldClassification = Literal["aligned", "safe_default", "operator_choice_required", "blocking_conflict"]

PREVIEW_SCHEMA_VERSION = 1


def _norm_name_for_compare(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return s.casefold()


def _norm_cvor_safe(raw: str | None) -> str | None:
    if raw is None:
        return None
    if not str(raw).strip():
        return None
    try:
        return normalize_cvor_number_digits(raw)
    except ValueError:
        return None


def classify_regulatory_pair(
    source_norm: str | None,
    survivor_norm: str | None,
) -> FieldClassification:
    if source_norm == survivor_norm:
        return "aligned"
    if source_norm is None or survivor_norm is None:
        return "safe_default"
    return "blocking_conflict"


def classify_name_pair(source_norm: str | None, survivor_norm: str | None) -> FieldClassification:
    """Compare *normalized* parent names (e.g. strip + ``casefold`` via ``_norm_name_for_compare``)."""
    if source_norm == survivor_norm:
        return "aligned"
    if source_norm is None or survivor_norm is None:
        return "safe_default"
    return "operator_choice_required"


def _merged_at_iso(b: GlobalBookingBroker) -> str | None:
    if b.merged_at is None:
        return None
    return b.merged_at.isoformat()


def _broker_snapshot(b: GlobalBookingBroker) -> dict[str, Any]:
    mc = normalize_mc_number_digits(b.mc_number)
    dot = normalize_dot_number_digits(b.dot_number)
    cvor = _norm_cvor_safe(b.cvor_number)
    return {
        "global_broker_id": b.id,
        "name": b.name,
        "legal_name": b.legal_name,
        "display_name": b.display_name,
        "mc_number_normalized": mc,
        "dot_number_normalized": dot,
        "cvor_number_normalized": cvor,
        "merged_into_global_broker_id": b.merged_into_global_broker_id,
        "merged_at": _merged_at_iso(b),
    }


def _stable_blockers(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(ev: dict[str, Any]) -> tuple[str, str]:
        detail = ev.get("detail")
        detail_s = json.dumps(detail, sort_keys=True, separators=(",", ":")) if detail is not None else ""
        return (str(ev.get("code", "")), detail_s)

    return sorted(blockers, key=key)


def _canonical_for_hash(
    *,
    source_id: int,
    survivor_id: int,
    duplicate_candidate_id: int | None,
    blockers: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": PREVIEW_SCHEMA_VERSION,
        "source_global_broker_id": source_id,
        "survivor_global_broker_id": survivor_id,
        "duplicate_candidate_id": duplicate_candidate_id,
        "blockers": _stable_blockers(blockers),
        "field_comparisons": sorted(comparisons, key=lambda x: str(x.get("field", ""))),
    }


def compute_preview_hash(canonical: dict[str, Any]) -> str:
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MergePreviewBuilt:
    preview_body: dict[str, Any]
    canonical: dict[str, Any]
    preview_hash: str
    persist_eligible: bool


def build_merge_preview(
    *,
    source: GlobalBookingBroker,
    survivor: GlobalBookingBroker,
    duplicate_candidate_id: int | None,
) -> MergePreviewBuilt:
    blockers: list[dict[str, Any]] = []

    if source.id == survivor.id:
        blockers.append({"code": "merge_self_not_allowed", "detail": {"global_broker_id": source.id}})
    else:
        src_v = merge_guard.global_booking_broker_merge_source_violation(source)
        if src_v is not None:
            blockers.append(
                {
                    "code": src_v,
                    "detail": {
                        "global_broker_id": source.id,
                        "role": "source",
                        "merged_into_global_broker_id": source.merged_into_global_broker_id,
                        "merged_at": _merged_at_iso(source),
                    },
                }
            )
        sur_v = merge_guard.global_booking_broker_merge_survivor_violation(survivor)
        if sur_v is not None:
            blockers.append(
                {
                    "code": sur_v,
                    "detail": {
                        "global_broker_id": survivor.id,
                        "role": "survivor",
                        "merged_into_global_broker_id": survivor.merged_into_global_broker_id,
                        "merged_at": _merged_at_iso(survivor),
                    },
                }
            )

    comparisons: list[dict[str, Any]] = []

    smc = normalize_mc_number_digits(source.mc_number)
    zmc = normalize_mc_number_digits(survivor.mc_number)
    mc_cls = classify_regulatory_pair(smc, zmc)
    comparisons.append(
        {
            "field": "mc_number",
            "kind": "regulatory",
            "classification": mc_cls,
            "source_normalized": smc,
            "survivor_normalized": zmc,
        }
    )

    sdot = normalize_dot_number_digits(source.dot_number)
    zdot = normalize_dot_number_digits(survivor.dot_number)
    dot_cls = classify_regulatory_pair(sdot, zdot)
    comparisons.append(
        {
            "field": "dot_number",
            "kind": "regulatory",
            "classification": dot_cls,
            "source_normalized": sdot,
            "survivor_normalized": zdot,
        }
    )

    scvor = _norm_cvor_safe(source.cvor_number)
    zcvor = _norm_cvor_safe(survivor.cvor_number)
    cvor_cls = classify_regulatory_pair(scvor, zcvor)
    comparisons.append(
        {
            "field": "cvor_number",
            "kind": "regulatory",
            "classification": cvor_cls,
            "source_normalized": scvor,
            "survivor_normalized": zcvor,
        }
    )

    sn = _norm_name_for_compare(source.name)
    zn = _norm_name_for_compare(survivor.name)
    n_cls = classify_name_pair(sn, zn)
    comparisons.append(
        {
            "field": "name",
            "kind": "parent_name",
            "classification": n_cls,
            "source_normalized": sn,
            "survivor_normalized": zn,
        }
    )

    sl = _norm_name_for_compare(source.legal_name)
    zl = _norm_name_for_compare(survivor.legal_name)
    ln_cls = classify_name_pair(sl, zl)
    comparisons.append(
        {
            "field": "legal_name",
            "kind": "parent_name",
            "classification": ln_cls,
            "source_normalized": sl,
            "survivor_normalized": zl,
        }
    )

    sd = _norm_name_for_compare(source.display_name)
    zd = _norm_name_for_compare(survivor.display_name)
    dn_cls = classify_name_pair(sd, zd)
    comparisons.append(
        {
            "field": "display_name",
            "kind": "parent_name",
            "classification": dn_cls,
            "source_normalized": sd,
            "survivor_normalized": zd,
        }
    )

    blocking = [c["field"] for c in comparisons if c["classification"] == "blocking_conflict"]
    op_choice = [c["field"] for c in comparisons if c["classification"] == "operator_choice_required"]
    safe_default = [c["field"] for c in comparisons if c["classification"] == "safe_default"]
    has_blockers = len(blockers) > 0
    has_blocking_conflict = len(blocking) > 0
    persist_eligible = (not has_blockers) and (not has_blocking_conflict)

    summary = {
        "has_blockers": has_blockers,
        "has_blocking_conflict": has_blocking_conflict,
        "blocking_conflict_fields": sorted(blocking),
        "operator_choice_required_fields": sorted(op_choice),
        "safe_default_fields": sorted(safe_default),
        "persist_eligible": persist_eligible,
    }

    preview_body: dict[str, Any] = {
        "schema_version": PREVIEW_SCHEMA_VERSION,
        "source_global_broker_id": source.id,
        "survivor_global_broker_id": survivor.id,
        "duplicate_candidate_id": duplicate_candidate_id,
        "source_snapshot": _broker_snapshot(source),
        "survivor_snapshot": _broker_snapshot(survivor),
        "blockers": _stable_blockers(blockers),
        "field_comparisons": sorted(comparisons, key=lambda x: str(x["field"])),
        "summary": summary,
    }

    canonical = _canonical_for_hash(
        source_id=source.id,
        survivor_id=survivor.id,
        duplicate_candidate_id=duplicate_candidate_id,
        blockers=blockers,
        comparisons=comparisons,
    )
    ph = compute_preview_hash(canonical)
    return MergePreviewBuilt(
        preview_body=preview_body,
        canonical=canonical,
        preview_hash=ph,
        persist_eligible=persist_eligible,
    )


async def build_and_persist_merge_preview(
    db: AsyncSession,
    *,
    source: GlobalBookingBroker,
    survivor: GlobalBookingBroker,
    duplicate_candidate_id: int | None,
) -> tuple[int | None, str, dict[str, Any]]:
    """Return ``(preview_id, preview_hash, preview_body)``. Persists platform row only when ``persist_eligible``."""
    built = build_merge_preview(
        source=source,
        survivor=survivor,
        duplicate_candidate_id=duplicate_candidate_id,
    )
    preview_id: int | None = None
    if built.persist_eligible:
        row = GlobalBookingBrokerMergePreview(
            source_global_broker_id=source.id,
            survivor_global_broker_id=survivor.id,
            duplicate_candidate_id=duplicate_candidate_id,
            preview_hash=built.preview_hash,
            preview_payload=json.dumps(built.preview_body, separators=(",", ":"), ensure_ascii=False),
        )
        db.add(row)
        await db.flush()
        preview_id = row.id
    return preview_id, built.preview_hash, built.preview_body
