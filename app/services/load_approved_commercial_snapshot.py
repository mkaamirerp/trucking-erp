"""Creation-time commercial JSON snapshot (load_approved_snapshot_v2).

Reads the flushed Load. Does not change parser output, money defaults, or evidence JSON.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.load import Load
from app.models.load_approved_commercial_snapshot import LoadApprovedCommercialSnapshot
from app.models.load_commercial_evidence import LoadCommercialEvidence
from app.services.load_parser_mechanical_validation import _CONTEXT_LEAK_KEYS

SCHEMA_VERSION = "load_approved_snapshot_v2"
MILESTONE_CREATION = "creation"
CREATION_REVISION = 1
SOURCE_PROMOTION = "workspace_promotion"
SOURCE_DIRECT = "direct_create"
CLAIM_NONE = "none"
CLAIM_WORKSPACE_REVIEWED = "workspace_promotion_reviewed"
EVIDENCE_CLASS = "unverified_parser_extraction"
COMPARE_BASELINE_NOTE = "creation_only_until_dispatcher_commercial_approved_milestone"

_CONTEXT_ALLOW = frozenset(
    {
        "parse_path",
        "pdf_type",
        "page_count",
        "requires_ocr",
        "ocr_engine",
        "semantic_outcome",
        "acquisition_method",
        "extraction_method",
    }
)
_LEAK_TOKENS = ("handoff", "prompt", "schema", "raw_text")


def money_string(value: Decimal | None) -> str | None:
    """Column scale only. Does not copy rate into customer_rate or call rate parsers."""
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return money_string(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _wrap(value: Any) -> dict[str, Any]:
    return {"value": _jsonable(value), "evidence_class": EVIDENCE_CLASS}


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (list, dict)) and len(value) == 0:
        return False
    return True


def build_approved_db_fields(load: Load) -> dict[str, Any]:
    stops = sorted(list(load.stops or []), key=lambda stop: (stop.sequence is None, stop.sequence or 0, stop.id or 0))
    return {
        "load_number": load.load_number,
        "broker_load_reference": load.broker_load_reference,
        "references": _jsonable(list(load.operational_references or [])),
        "broker_id": load.broker_id,
        "broker_contact_id": load.broker_contact_id,
        "customs_broker_id": load.customs_broker_id,
        "broker_name_snapshot": load.broker_name_snapshot,
        "broker_contact_name_snapshot": load.broker_contact_name_snapshot,
        "broker_contact_phone_snapshot": load.broker_contact_phone_snapshot,
        "broker_contact_extension_snapshot": load.broker_contact_extension_snapshot,
        "broker_contact_email_snapshot": load.broker_contact_email_snapshot,
        "broker_match_method": load.broker_match_method,
        "broker_match_confidence_tier": load.broker_match_confidence_tier,
        "broker_match_explanation": load.broker_match_explanation,
        "review_required": bool(load.review_required),
        "is_duplicate_of_load_id": load.is_duplicate_of_load_id,
        "promotion_origin_workspace_draft_id": _jsonable(load.promotion_origin_workspace_draft_id),
        "status": load.status,
        "mode": load.mode,
        "equipment_type": load.equipment_type,
        "trailer_type": load.trailer_type,
        "trailer_size": load.trailer_size,
        "commodity": load.commodity,
        "estimated_weight": load.estimated_weight,
        "hazmat_flag": load.hazmat_flag,
        "temperature_requirement": load.temperature_requirement,
        "pallet_case_count": load.pallet_case_count,
        "miles": load.miles,
        "internal_notes": load.internal_notes,
        "rate": money_string(load.rate),
        "customer_rate": money_string(load.customer_rate),
        "stops": [
            {
                "id": stop.id,
                "stop_type": stop.stop_type,
                "sequence": stop.sequence,
                "facility_name": stop.facility_name,
                "street": stop.street,
                "city": stop.city,
                "state_or_province": stop.state_or_province,
                "postal_code": stop.postal_code,
                "country": stop.country,
                "reference_number": stop.reference_number,
                "appointment_type": stop.appointment_type,
                "appointment_date": _jsonable(stop.appointment_date),
                "appointment_time_text": stop.appointment_time_text,
                "notes": stop.notes,
                "commodity_notes": stop.commodity_notes,
            }
            for stop in stops
        ],
    }


def _context_allowlist(context: Any) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    kept: dict[str, Any] = {}
    for key, value in context.items():
        name = str(key)
        folded = name.casefold()
        if name in _CONTEXT_LEAK_KEYS or folded.startswith("diagnostic"):
            continue
        if any(token in folded for token in _LEAK_TOKENS):
            continue
        if name not in _CONTEXT_ALLOW:
            continue
        kept[name] = value
    return kept


def project_original_rc_reference(
    accepted: dict[str, Any] | None,
    *,
    evidence_id: int | None,
    evidence_sha256: str | None,
    accepted_parse_pdf_sha256: str | None,
    workspace_draft_id: uuid.UUID | None,
    parse_schema_version: str | None,
) -> dict[str, Any]:
    evidence_sha = (evidence_sha256 or "").strip() or None
    parse_sha = (accepted_parse_pdf_sha256 or "").strip() or None
    if evidence_sha and parse_sha:
        sha_match: bool | None = evidence_sha == parse_sha
    else:
        sha_match = None

    document = accepted.get("document") if isinstance(accepted, dict) else None
    filename = None
    if isinstance(document, dict):
        raw_name = document.get("filename")
        if isinstance(raw_name, str) and raw_name.strip():
            filename = raw_name.strip()

    extracted = accepted.get("extracted") if isinstance(accepted, dict) else None
    extracted_ok = isinstance(extracted, dict) and len(extracted) > 0

    if evidence_id is None:
        status_name = "pdf_missing"
        detail = "no_commercial_evidence"
        source = "none"
        extracted_ok = False
        accepted = None
    elif not isinstance(accepted, dict) or not accepted:
        status_name = "parse_missing"
        detail = "accepted_parse_missing"
        source = "commercial_evidence"
    elif sha_match is False:
        status_name = "parse_present_pdf_mismatch"
        detail = "pdf_sha256_mismatch"
        source = "commercial_evidence"
    elif not extracted_ok:
        status_name = "parse_unusable" if accepted else "parse_missing"
        detail = "extracted_missing"
        source = "commercial_evidence"
    elif sha_match is None:
        status_name = "parse_unusable"
        detail = "pdf_sha256_incomplete"
        source = "commercial_evidence"
    else:
        status_name = "usable"
        detail = "pdf_sha256_match"
        source = "commercial_evidence"

    body: dict[str, Any] = {
        "association_status": status_name,
        "association_detail": detail,
        "source": source,
        "accepted_parse_schema_version": parse_schema_version,
        "pdf_sha256_evidence": evidence_sha,
        "pdf_sha256_parse_accepted": parse_sha,
        "pdf_sha256_match": sha_match,
        "commercial_evidence_id": evidence_id,
        "workspace_draft_id": _jsonable(workspace_draft_id),
        "document_filename": filename if evidence_id is not None else None,
    }
    if evidence_id is None or not extracted_ok or not isinstance(extracted, dict):
        return body
    if status_name == "parse_missing":
        return body

    def take(key: str) -> Any:
        return extracted.get(key)

    broker_party: dict[str, Any] = {}
    for key, dest in (
        ("broker_name_snapshot", "name"),
        ("broker_phone_snapshot", "phone"),
        ("broker_mc_number_snapshot", "mc_number"),
        ("broker_dot_number_snapshot", "dot_number"),
    ):
        if _present(take(key)):
            broker_party[dest] = _wrap(take(key))
    contact: dict[str, Any] = {}
    for key, dest in (
        ("broker_contact_name_snapshot", "name"),
        ("broker_contact_phone_snapshot", "phone"),
        ("broker_contact_email_snapshot", "email"),
    ):
        if _present(take(key)):
            contact[dest] = _wrap(take(key))
    if contact:
        broker_party["contact"] = contact
    if broker_party:
        body["broker_party"] = broker_party

    commercial: dict[str, Any] = {}
    for key, dest in (
        ("broker_load_reference", "broker_load_reference"),
        ("rate", "document_linehaul_rate"),
        ("customer_rate", "document_customer_rate"),
        ("miles", "miles"),
        ("mode", "mode"),
        ("equipment_type", "equipment_type"),
        ("trailer_type", "trailer_type"),
        ("trailer_size", "trailer_size"),
        ("commodity", "commodity"),
        ("estimated_weight", "estimated_weight"),
        ("temperature_requirement", "temperature_requirement"),
        ("customs_broker_name", "customs_broker_name"),
    ):
        if _present(take(key)):
            commercial[dest] = _wrap(take(key))
    if commercial:
        body["commercial"] = commercial
    if _present(take("references")):
        body["document_references"] = _wrap(take("references"))
    if _present(take("stops")):
        body["document_stops"] = _wrap(take("stops"))

    if isinstance(accepted, dict):
        if _present(accepted.get("field_confidence")):
            body["parser_field_confidence"] = _wrap(accepted.get("field_confidence"))
        if _present(accepted.get("warnings")):
            body["parser_warnings"] = _wrap(accepted.get("warnings"))
        context = _context_allowlist(accepted.get("context"))
        if context:
            body["parse_context"] = _wrap(context)
    return body


def build_creation_payload(
    load: Load,
    *,
    creation_source: str,
    dispatcher_review_claim: str,
    created_by_platform_user_id: str | None,
    snapshot_taken_at: datetime,
    original_rc_reference: dict[str, Any],
    commercial_evidence_id: int | None,
    workspace_draft_id: uuid.UUID | None,
) -> dict[str, Any]:
    metadata = {
        "tenant_id": int(load.tenant_id),
        "load_id": int(load.id),
        "milestone": MILESTONE_CREATION,
        "revision": CREATION_REVISION,
        "schema_version": SCHEMA_VERSION,
        "load_concurrency_version": int(load.concurrency_version),
        "creation_source": creation_source,
        "load_status_at_snapshot": load.status,
        "dispatcher_review_claim": dispatcher_review_claim,
        "snapshot_taken_at": snapshot_taken_at.isoformat(),
        "created_by_platform_user_id": created_by_platform_user_id,
        "commercial_evidence_id": commercial_evidence_id,
        "workspace_draft_id": _jsonable(workspace_draft_id),
        "compare_baseline_note": COMPARE_BASELINE_NOTE,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "approved_db_fields": build_approved_db_fields(load),
        "original_rc_reference": original_rc_reference,
        "metadata": metadata,
        "storage_policy": {
            "operator_private_fields": ["approved_db_fields.internal_notes"],
            "future_ai_comparable_excludes": ["approved_db_fields.internal_notes"],
        },
    }


def _abort_evidence_link(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "LOAD_APPROVED_SNAPSHOT_EVIDENCE_LINK_INVALID", "message": detail},
    )


async def insert_creation_snapshot_uncommitted(
    db: AsyncSession,
    load: Load,
    *,
    creation_source: str,
    dispatcher_review_claim: str,
    created_by_platform_user_id: str | None,
    evidence: LoadCommercialEvidence | None,
    workspace_draft_id: uuid.UUID | None,
    accepted_parse_pdf_sha256: str | None,
) -> None:
    """Insert the creation row in the caller's transaction. A second creation row is a no-op."""
    if evidence is not None:
        if int(evidence.tenant_id) != int(load.tenant_id) or int(evidence.load_id) != int(load.id):
            _abort_evidence_link("commercial evidence tenant or load does not match the new load")
        if workspace_draft_id is not None and evidence.workspace_draft_id != workspace_draft_id:
            _abort_evidence_link("commercial evidence draft does not match the promoted draft")
        if evidence.id is None:
            _abort_evidence_link("commercial evidence has no id after flush")

    existing = await db.scalar(
        select(LoadApprovedCommercialSnapshot.id).where(
            LoadApprovedCommercialSnapshot.tenant_id == int(load.tenant_id),
            LoadApprovedCommercialSnapshot.load_id == int(load.id),
            LoadApprovedCommercialSnapshot.milestone == MILESTONE_CREATION,
        )
    )
    if existing is not None:
        return

    taken_at = datetime.now(timezone.utc)
    original = project_original_rc_reference(
        evidence.accepted_parse_json if evidence is not None else None,
        evidence_id=int(evidence.id) if evidence is not None else None,
        evidence_sha256=evidence.file_sha256 if evidence is not None else None,
        accepted_parse_pdf_sha256=accepted_parse_pdf_sha256,
        workspace_draft_id=workspace_draft_id,
        parse_schema_version=evidence.parse_schema_version if evidence is not None else None,
    )
    payload = build_creation_payload(
        load,
        creation_source=creation_source,
        dispatcher_review_claim=dispatcher_review_claim,
        created_by_platform_user_id=created_by_platform_user_id,
        snapshot_taken_at=taken_at,
        original_rc_reference=original,
        commercial_evidence_id=int(evidence.id) if evidence is not None else None,
        workspace_draft_id=workspace_draft_id,
    )
    db.add(
        LoadApprovedCommercialSnapshot(
            tenant_id=int(load.tenant_id),
            load_id=int(load.id),
            milestone=MILESTONE_CREATION,
            revision=CREATION_REVISION,
            schema_version=SCHEMA_VERSION,
            load_concurrency_version=int(load.concurrency_version),
            creation_source=creation_source,
            load_status_at_snapshot=str(load.status),
            dispatcher_review_claim=dispatcher_review_claim,
            commercial_evidence_id=int(evidence.id) if evidence is not None else None,
            workspace_draft_id=workspace_draft_id,
            created_by_platform_user_id=created_by_platform_user_id,
            snapshot_taken_at=taken_at,
            payload_json=payload,
        )
    )
    await db.flush()
