"""S1 creation snapshot projector. No database and no email-intake path."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.load_approved_commercial_snapshot import (
    build_approved_db_fields,
    build_creation_payload,
    money_string,
    project_original_rc_reference,
)


def _stop(**kwargs):
    base = dict(
        id=1,
        sequence=0,
        stop_type="pickup",
        facility_name=None,
        street=None,
        city="Chicago",
        state_or_province="IL",
        postal_code=None,
        country=None,
        reference_number="PU-1",
        appointment_type=None,
        appointment_date=date(2026, 10, 28),
        appointment_time_text=None,
        notes=None,
        commodity_notes=None,
        scheduled_at="must-not-copy",
        arrived_at="must-not-copy",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _load(**kwargs):
    base = dict(
        id=9,
        tenant_id=3,
        load_number="Oct-26-0332",
        broker_load_reference="ARM-100",
        operational_references=[{"kind": "po", "value": "PO-9"}],
        broker_id=4,
        broker_contact_id=None,
        customs_broker_id=None,
        broker_name_snapshot="Armstrong",
        broker_contact_name_snapshot=None,
        broker_contact_phone_snapshot=None,
        broker_contact_extension_snapshot=None,
        broker_contact_email_snapshot=None,
        broker_match_method=None,
        broker_match_confidence_tier=None,
        broker_match_explanation=None,
        review_required=False,
        is_duplicate_of_load_id=None,
        promotion_origin_workspace_draft_id=None,
        status="draft",
        mode=None,
        equipment_type=None,
        trailer_type=None,
        trailer_size=None,
        commodity=None,
        estimated_weight=None,
        hazmat_flag=False,
        temperature_requirement=None,
        pallet_case_count=None,
        miles=None,
        internal_notes="private note",
        rate=Decimal("0"),
        customer_rate=None,
        concurrency_version=1,
        driver_id=99,
        truck_id=98,
        trailer_id=97,
        active_trip_id=96,
        trip_number="T-SHOULD-NOT-COPY",
        stops=[_stop()],
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_money_string_uses_column_scale_and_preserves_null():
    assert money_string(None) is None
    assert money_string(Decimal("0")) == "0.00"
    assert money_string(Decimal("1800")) == "1800.00"


def test_approved_fields_keep_broker_ref_separate_from_po_and_drop_trip_fields():
    fields = build_approved_db_fields(_load())
    assert fields["broker_load_reference"] == "ARM-100"
    assert fields["references"] == [{"kind": "po", "value": "PO-9"}]
    assert fields["rate"] == "0.00"
    assert fields["customer_rate"] is None
    assert fields["internal_notes"] == "private note"
    assert fields["stops"][0]["appointment_date"] == "2026-10-28"
    assert "scheduled_at" not in fields["stops"][0]
    assert "driver_id" not in fields
    assert "trip_number" not in fields
    assert "active_trip_id" not in fields


def test_direct_create_has_no_invented_rate_confirmation():
    ref = project_original_rc_reference(
        {"extracted": {"rate": "999"}},
        evidence_id=None,
        evidence_sha256=None,
        accepted_parse_pdf_sha256="abc",
        workspace_draft_id=None,
        parse_schema_version=None,
    )
    assert ref["association_status"] == "pdf_missing"
    assert ref["source"] == "none"
    assert "commercial" not in ref
    assert "raw_text" not in ref


def test_hash_mismatch_is_not_usable_and_keeps_kinded_references():
    accepted = {
        "document": {"filename": "rc.pdf"},
        "extracted": {
            "broker_load_reference": "ARM-100",
            "rate": "1800.00",
            "references": [
                {"kind": "po", "value": "PO-9"},
                {"kind": "bol", "value": "BOL-1"},
            ],
            "raw_text": "SECRET PAGE TEXT",
        },
        "field_confidence": {"rate": "high"},
        "warnings": [],
        "context": {
            "parse_path": "digital",
            "raw_text": "SECRET",
            "llm_prompt": "do not keep",
            "parse_diagnostics": {"secret": True},
        },
    }
    ref = project_original_rc_reference(
        accepted,
        evidence_id=5,
        evidence_sha256="aaa",
        accepted_parse_pdf_sha256="bbb",
        workspace_draft_id=None,
        parse_schema_version="v1",
    )
    assert ref["association_status"] == "parse_present_pdf_mismatch"
    assert ref["pdf_sha256_match"] is False
    assert ref["commercial"]["broker_load_reference"]["evidence_class"] == "unverified_parser_extraction"
    assert ref["document_references"]["value"][0]["kind"] == "po"
    assert "raw_text" not in ref
    blob = str(ref)
    assert "SECRET" not in blob
    assert "llm_prompt" not in blob


def test_matching_hashes_with_extracted_are_usable():
    ref = project_original_rc_reference(
        {"extracted": {"commodity": "steel"}, "context": {"pdf_type": "digital"}},
        evidence_id=5,
        evidence_sha256="abc",
        accepted_parse_pdf_sha256="abc",
        workspace_draft_id=None,
        parse_schema_version="v1",
    )
    assert ref["association_status"] == "usable"
    assert ref["commercial"]["commodity"]["value"] == "steel"
    assert ref["parse_context"]["value"] == {"pdf_type": "digital"}


def test_nested_references_stops_and_confidence_drop_leak_keys():
    secret = "NESTED-SECRET-RC"
    ref = project_original_rc_reference(
        {
            "document": {"filename": "rc.pdf"},
            "extracted": {
                "commodity": "steel",
                "temperature_requirement": "appointment window",
                "references": [
                    {
                        "kind": "po",
                        "value": "PO-9",
                        "raw_text": secret,
                        "llm_prompt": secret,
                        "handoff": {"raw_text": secret},
                        "parse_diagnostics": {"secret": secret},
                    }
                ],
                "stops": [
                    {
                        "city": "Chicago",
                        "state_or_province": "IL",
                        "appointment_type": "FCFS",
                        "raw_text": secret,
                        "prompt": secret,
                        "handoff_payload": secret,
                        "diagnostic_blob": secret,
                    }
                ],
            },
            "field_confidence": {
                "rate": {"score": "high", "raw_text": secret, "prompt": secret},
                "stops": [
                    {
                        "city": {
                            "value": "Chicago",
                            "handoff": secret,
                            "diagnostics": secret,
                        }
                    }
                ],
            },
            "warnings": [{"code": "soft", "raw_text": secret, "diagnostic_note": secret}],
        },
        evidence_id=5,
        evidence_sha256="abc",
        accepted_parse_pdf_sha256="abc",
        workspace_draft_id=None,
        parse_schema_version="v1",
    )
    blob = str(ref)
    assert secret not in blob
    assert "raw_text" not in blob
    assert "llm_prompt" not in blob
    assert "handoff" not in blob
    assert "diagnostic" not in blob
    assert ref["document_references"]["value"] == [{"kind": "po", "value": "PO-9"}]
    stop = ref["document_stops"]["value"][0]
    assert stop["city"] == "Chicago"
    assert stop["appointment_type"] == "FCFS"
    assert ref["parser_field_confidence"]["value"]["rate"] == {"score": "high"}
    assert ref["parser_field_confidence"]["value"]["stops"][0]["city"] == {"value": "Chicago"}
    assert ref["parser_warnings"]["value"] == [{"code": "soft"}]
    assert ref["commercial"]["commodity"]["value"] == "steel"
    assert ref["commercial"]["temperature_requirement"]["value"] == "appointment window"


def test_orm_metadata_matches_s1_migration_constraints():
    from app.models.load_approved_commercial_snapshot import LoadApprovedCommercialSnapshot
    from app.models.load_commercial_evidence import LoadCommercialEvidence

    snapshot = LoadApprovedCommercialSnapshot.__table__
    constraint_names = {constraint.name for constraint in snapshot.constraints}
    assert "uq_load_approved_snapshots_tenant_load_milestone_rev" in constraint_names
    assert "fk_load_approved_snapshots_load_tenant" in constraint_names
    assert "fk_load_approved_snapshots_evidence_tenant" in constraint_names
    assert "ck_load_approved_snapshots_milestone_creation" in constraint_names
    assert "ck_load_approved_snapshots_creation_source" in constraint_names
    assert "ck_load_approved_snapshots_review_claim" in constraint_names
    assert "ck_load_approved_snapshots_claim_matches_source" in constraint_names
    assert "ck_load_approved_snapshots_evidence_on_promotion" in constraint_names
    assert "ix_load_approved_snapshots_tenant_load" in {index.name for index in snapshot.indexes}

    evidence_names = {constraint.name for constraint in LoadCommercialEvidence.__table__.constraints}
    assert "uq_load_commercial_evidence_tenant_id" in evidence_names


def test_provisioning_target_stops_before_s1_snapshot_table():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from pathlib import Path

    from app.core.config import Settings
    from scripts.tenant_revision_plan import POD_X5, S1_FMP, S1_X5

    assert Settings.model_fields["tenant_alembic_target_rev"].default == POD_X5
    root = Path(__file__).resolve().parents[1]
    script = ScriptDirectory.from_config(Config(str(root / "alembic_tenant.ini")))

    def ancestors(revision: str) -> set[str]:
        found: set[str] = set()
        pending = [revision]
        while pending:
            current_id = pending.pop()
            if current_id in found:
                continue
            found.add(current_id)
            current = script.get_revision(current_id)
            down = current.down_revision
            if down is None:
                continue
            if isinstance(down, (tuple, list)):
                pending.extend(str(item) for item in down)
            else:
                pending.append(str(down))
        return found

    provisioning = ancestors(POD_X5)
    assert S1_X5 not in provisioning
    assert S1_FMP not in provisioning
    assert POD_X5 in ancestors(S1_X5)
    assert S1_FMP not in ancestors(S1_X5)
    assert S1_X5 not in ancestors(S1_FMP)


def test_storage_policy_excludes_internal_notes_from_future_ai():
    from datetime import datetime, timezone

    payload = build_creation_payload(
        _load(),
        creation_source="direct_create",
        dispatcher_review_claim="none",
        created_by_platform_user_id=None,
        snapshot_taken_at=datetime(2026, 10, 27, tzinfo=timezone.utc),
        original_rc_reference={"association_status": "pdf_missing", "source": "none"},
        commercial_evidence_id=None,
        workspace_draft_id=None,
    )
    assert payload["schema_version"] == "load_approved_snapshot_v2"
    assert payload["approved_db_fields"]["internal_notes"] == "private note"
    assert payload["storage_policy"]["future_ai_comparable_excludes"] == [
        "approved_db_fields.internal_notes"
    ]
    assert payload["metadata"]["dispatcher_review_claim"] == "none"
    assert payload["metadata"]["creation_source"] == "direct_create"
