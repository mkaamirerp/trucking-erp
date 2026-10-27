"""Read-only revised rate-confirmation compare. No database writes."""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.authz.routes import binding_for
from app.schemas.load_document_parse import (
    LoadDocumentParseResponse,
    LoadParseDocumentMeta,
    LoadParseExtractedFields,
    LoadParseStopItem,
)
from app.services.load_approved_commercial_snapshot import CreationSnapshotLookup
from app.services.load_document_parse_orchestrator import (
    RateConfirmationRevisionCompareError,
    compare_revised_rate_confirmation,
    original_evidence_select,
)

PDF = b"%PDF-1.4\nrevised\n"


def _stop(**overrides):
    values = dict(
        id=1,
        sequence=1,
        stop_type="pickup",
        facility_name=None,
        street=None,
        city="Boston",
        state_or_province="MA",
        postal_code=None,
        country=None,
        reference_number=None,
        appointment_type=None,
        appointment_date=None,
        appointment_time_text=None,
        notes=None,
        commodity_notes=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _load(**overrides):
    values = dict(
        id=11,
        tenant_id=4,
        status="ready",
        load_number="L-11",
        broker_load_reference="3872125-1",
        operational_references=[],
        broker_id=None,
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
        internal_notes=None,
        rate=Decimal("1800.00"),
        customer_rate=Decimal("1800.00"),
        stops=[_stop()],
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _snapshot() -> dict:
    return {
        "schema_version": "load_approved_snapshot_v2",
        "approved_db_fields": {"rate": "1800.00", "broker_load_reference": "3872125-1"},
        "original_rc_reference": {"association_status": "usable"},
        "metadata": {"tenant_id": 4, "load_id": 11},
        "storage_policy": {"append_only": True},
    }


def _evidence(extracted: dict) -> SimpleNamespace:
    return SimpleNamespace(accepted_parse_json={"extracted": extracted, "unused_note": "kept"})


def _parsed(**extracted_overrides) -> LoadDocumentParseResponse:
    extracted = dict(
        broker_load_reference="3872125-1",
        broker_name_snapshot="Armstrong",
        broker_mc_number_snapshot="MC-unused",
        rate=Decimal("1800.00"),
        stops=[LoadParseStopItem(stop_type="pickup", sequence=1, city="Boston")],
    )
    extracted.update(extracted_overrides)
    return LoadDocumentParseResponse(
        document=LoadParseDocumentMeta(filename="revised.pdf"),
        extracted=LoadParseExtractedFields(**extracted),
        raw_text="revised rate confirmation",
    )


class _Db:
    def __init__(self, evidence) -> None:
        self.evidence = evidence
        self.writes: list[str] = []

    def add(self, *_args, **_kwargs):
        self.writes.append("add")
        raise AssertionError("compare must not add rows")

    async def commit(self):
        self.writes.append("commit")
        raise AssertionError("compare must not commit")

    async def rollback(self):
        self.writes.append("rollback")

    async def scalar(self, _statement):
        return self.evidence


def _freeze(load, snapshot, evidence) -> str:
    return json.dumps(
        {
            "load": load.__dict__,
            "snapshot": snapshot,
            "evidence": evidence.accepted_parse_json,
        },
        default=lambda value: value.__dict__ if hasattr(value, "__dict__") else str(value),
        sort_keys=True,
    )


@pytest.fixture
def baselines(monkeypatch):
    load = _load()
    snapshot = _snapshot()
    evidence = _evidence(
        {
            "broker_load_reference": "3872125-1",
            "rate": "1800.00",
            "stops": [{"city": "Chicago", "sequence": 1, "stop_type": "pickup"}],
        }
    )
    state = {"load": load, "snapshot": snapshot, "evidence": evidence}

    async def get_load(_db, tenant_id, load_id):
        row = state["load"]
        if int(tenant_id) != int(row.tenant_id) or int(load_id) != int(row.id):
            return None
        return row

    async def get_creation_snapshot(_db, _tenant_id, _load_id):
        payload = state["snapshot"]
        if payload is None:
            return CreationSnapshotLookup(outcome="no_creation_snapshot")
        return CreationSnapshotLookup(outcome="creation_snapshot", payload=payload, snapshot_id=1)

    monkeypatch.setattr("app.services.loads.get_load", get_load)
    monkeypatch.setattr(
        "app.services.load_approved_commercial_snapshot.get_creation_snapshot",
        get_creation_snapshot,
    )
    return state


async def _run(state, parsed, proposals, *, tenant_id=4, load_id=11):
    db = _Db(state["evidence"])
    seen: dict = {}
    before = _freeze(state["load"], state["snapshot"], state["evidence"])

    async def parse_document(*_args, **kwargs):
        seen["parse"] = kwargs
        return parsed

    async def compare_chat(**kwargs):
        seen["chat"] = kwargs
        return {"changes": proposals}

    result = await compare_revised_rate_confirmation(
        db,
        tenant_id=tenant_id,
        load_id=load_id,
        pdf_bytes=PDF,
        filename="revised.pdf",
        parse_document=parse_document,
        compare_chat=compare_chat,
    )
    after = _freeze(state["load"], state["snapshot"], state["evidence"])
    assert after == before
    assert db.writes == []
    return result, seen


@pytest.mark.asyncio
async def test_rate_change_is_kept_and_rows_stay_unchanged(baselines):
    parsed = _parsed(rate=Decimal("2100.00"))
    result, seen = await _run(
        baselines,
        parsed,
        [{"field": "rate", "new_value": "2100.00", "ai_note": "Linehaul changed."}],
    )
    assert seen["parse"]["load_id"] == 11
    assert "saved_snapshot" in seen["chat"]["user_text"]
    assert "broker_mc_number_snapshot" in seen["chat"]["user_text"]
    assert seen["chat"]["schema"]["required"] == ["changes"]
    assert "load" not in seen["chat"]["schema"]["properties"]
    assert result.same_load is True
    assert result.warning is None
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.field == "rate"
    assert change.current_value == "1800.00"
    assert change.original_extracted == "1800.00"
    assert change.new_value == "2100.00"
    assert change.kind == "changed"
    assert change.ai_note == "Linehaul changed."
    assert change.requires_explicit_accept is True


@pytest.mark.asyncio
async def test_repeat_misread_equal_to_original_extraction_is_not_a_change(baselines):
    parsed = _parsed(
        stops=[LoadParseStopItem(stop_type="pickup", sequence=1, city="Chicago")],
    )
    result, _seen = await _run(
        baselines,
        parsed,
        [{"field": "stops[0].city", "new_value": "Chicago", "ai_note": "City differs from the saved stop."}],
    )
    assert result.same_load is True
    assert result.changes == []


@pytest.mark.asyncio
async def test_unchanged_pdf_returns_an_empty_list(baselines):
    result, _seen = await _run(
        baselines,
        _parsed(),
        [
            {"field": "rate", "new_value": "1800.00", "ai_note": "Same rate."},
            {"field": "stops[0].city", "new_value": "Boston", "ai_note": "Same city."},
        ],
    )
    assert result.changes == []


@pytest.mark.asyncio
async def test_different_broker_reference_proposes_nothing(baselines):
    result, seen = await _run(
        baselines,
        _parsed(broker_load_reference="34307972"),
        [{"field": "rate", "new_value": "2100.00", "ai_note": "Should not be asked."}],
    )
    assert "chat" not in seen
    assert result.same_load is False
    assert result.changes == []
    assert "different broker load number" in (result.warning or "")


@pytest.mark.asyncio
async def test_missing_creation_snapshot_is_409(baselines):
    baselines["snapshot"] = None
    db = _Db(baselines["evidence"])
    before = _freeze(baselines["load"], {}, baselines["evidence"])
    with pytest.raises(RateConfirmationRevisionCompareError) as caught:
        await compare_revised_rate_confirmation(
            db,
            tenant_id=4,
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            parse_document=_must_not_parse,
            compare_chat=_must_not_chat,
        )
    assert caught.value.status_code == 409
    assert "no usable creation snapshot" in caught.value.detail
    assert db.writes == []
    assert _freeze(baselines["load"], {}, baselines["evidence"]) == before


@pytest.mark.asyncio
async def test_cancelled_load_is_rejected(baselines):
    baselines["load"].status = "cancelled"
    before = baselines["load"].status
    with pytest.raises(RateConfirmationRevisionCompareError) as caught:
        await compare_revised_rate_confirmation(
            _Db(baselines["evidence"]),
            tenant_id=4,
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            parse_document=_must_not_parse,
            compare_chat=_must_not_chat,
        )
    assert caught.value.status_code == 409
    assert "Cancelled" in caught.value.detail
    assert baselines["load"].status == before


@pytest.mark.asyncio
async def test_cross_tenant_load_is_not_found(baselines):
    before = copy.deepcopy(baselines["load"].__dict__)
    with pytest.raises(RateConfirmationRevisionCompareError) as caught:
        await compare_revised_rate_confirmation(
            _Db(baselines["evidence"]),
            tenant_id=99,
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            parse_document=_must_not_parse,
            compare_chat=_must_not_chat,
        )
    assert caught.value.status_code == 404
    assert baselines["load"].__dict__ == before


@pytest.mark.asyncio
async def test_ai_value_missing_from_the_new_extraction_is_dropped(baselines):
    result, _seen = await _run(
        baselines,
        _parsed(rate=Decimal("2100.00")),
        [{"field": "rate", "new_value": "9999.00", "ai_note": "Invented rate."}],
    )
    assert result.changes == []


@pytest.mark.asyncio
async def test_evidence_query_is_tenant_scoped():
    statement = original_evidence_select(9, 3)
    params = statement.compile().params
    assert 9 in params.values()
    assert 3 in params.values()


def test_compare_route_is_mapped_as_document_parse():
    binding = binding_for("POST", "/api/v1/loads/{load_id}/rate-confirmation-revision/compare")
    assert binding.resource == "loads.documents"
    assert binding.action == "parse"
    assert "does not update the load" in binding.note


async def _must_not_parse(*_args, **_kwargs):
    raise AssertionError("parser must not run")


async def _must_not_chat(**_kwargs):
    raise AssertionError("compare model must not run")
