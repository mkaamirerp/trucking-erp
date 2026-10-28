"""Accepting a revised rate confirmation writes only the accepted rate."""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.authz.routes import binding_for
from app.models.load_rate_confirmation_revision import LoadRateConfirmationRevision
from app.schemas.load_document_parse import (
    LoadDocumentParseResponse,
    LoadParseDocumentMeta,
    LoadParseExtractedFields,
    LoadParseStopItem,
)
from app.services.load_document_parse_orchestrator import (
    _DIFFERENT_LOAD,
    _NO_REVISED_REF,
    _NO_SAVED_REF,
    _UNREADABLE_PDF,
)
from app.services.load_rate_confirmation_revision import (
    RateConfirmationRevisionAcceptError,
    _ALREADY_APPLIED,
    _LOAD_CHANGED,
    _RATE_ONLY,
    _RATE_UNVERIFIED,
    accept_revised_rate_confirmation,
    list_rate_confirmation_revisions,
    read_rate_confirmation_pdf_for_view,
)

PDF = b"%PDF-1.4\nrevised-rate\n"
PDF_SHA = hashlib.sha256(PDF).hexdigest()
ROOT = Path(__file__).resolve().parents[1]


def _stop():
    return SimpleNamespace(
        id=1,
        sequence=1,
        stop_type="pickup",
        facility_name="Acme Warehouse",
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


def _load(**overrides):
    values = dict(
        id=11,
        tenant_id=4,
        status="ready",
        load_number="L-11",
        broker_load_reference="ABC-123",
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


def _evidence(**overrides):
    payload = {
        "extracted": {
            "broker_load_reference": "ABC-123",
            "broker_name_snapshot": "Armstrong",
            "rate": "1800.00",
            "stops": [{"facility_name": "Acme Warehouse", "city": "Boston"}],
        }
    }
    values = dict(
        accepted_parse_json=payload,
        file_sha256="a" * 64,
        filename="original.pdf",
        storage_key="demo/load_workspace_drafts/original.pdf",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _parsed(**extracted_overrides):
    extracted = dict(
        broker_load_reference="ABC123",
        broker_name_snapshot="Armstrong",
        rate=Decimal("1500.00"),
        stops=[LoadParseStopItem(stop_type="pickup", sequence=1, city="Boston", facility_name="Acme Warehouse")],
    )
    extracted.update(extracted_overrides)
    context = extracted_overrides.pop("_context", {})
    return LoadDocumentParseResponse(
        document=LoadParseDocumentMeta(filename="revised.pdf"),
        extracted=LoadParseExtractedFields(**extracted),
        raw_text="revised rate confirmation raw text",
        context=context,
    )


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _Stored:
    def __init__(self, sha: str):
        self.storage_key = "demo/load_workspace_drafts/load_rc_revision/11/revised.pdf"
        self.sha256 = sha
        self.original_filename = "revised.pdf"


class _Storage:
    def __init__(self):
        self.saved = 0
        self.deleted = 0

    async def save_bytes(self, *_args, **_kwargs):
        self.saved += 1
        return _Stored(PDF_SHA)

    def delete(self, *_args, **_kwargs):
        self.deleted += 1


class _Db:
    def __init__(self, load, evidence, revisions=None):
        self.load = load
        self.evidence = evidence
        self.revisions = list(revisions or [])
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.tenant_id = 4
        self.load_id = 11

    def _params(self, stmt):
        return list(stmt.compile().params.values())

    async def scalar(self, stmt):
        params = self._params(stmt)
        if self.tenant_id not in params or self.load_id not in params:
            return None
        sql = str(stmt)
        if "load_commercial_evidence" in sql:
            return self.evidence
        if "load_rate_confirmation_revisions" in sql:
            numbers = [
                value
                for value in params
                if isinstance(value, int) and value not in {self.tenant_id, self.load_id}
            ]
            if numbers:
                return next((row for row in self.revisions if row.revision_number == numbers[0]), None)
            return next((row for row in self.revisions if row.is_current), None)
        return self.load

    async def scalars(self, stmt):
        params = self._params(stmt)
        if self.tenant_id not in params or self.load_id not in params:
            return _Rows([])
        return _Rows(self.revisions)

    def add(self, row):
        self.added.append(row)
        self.revisions.append(row)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _fields(new="1500.00", expected="1800.00", field="rate"):
    return [{"field": field, "expected_current_value": expected, "new_value": new}]


async def _accept(db, monkeypatch, parsed=None, fields=None, pdf=PDF, tenant_id=4):
    storage = _Storage()
    seen = {"parse": 0, "compare": 0}

    async def _parse(*_args, **_kwargs):
        seen["parse"] += 1
        return parsed if parsed is not None else _parsed()

    async def _compare(*_args, **_kwargs):
        seen["compare"] += 1
        raise AssertionError("accept must not call compare")

    monkeypatch.setattr(
        "app.services.load_rate_confirmation_revision.parse_load_workspace_document_orchestrated",
        _parse,
    )
    monkeypatch.setattr(
        "app.services.load_document_parse_orchestrator.compare_revised_rate_confirmation",
        _compare,
    )
    monkeypatch.setattr(
        "app.services.load_rate_confirmation_revision.get_storage",
        lambda: storage,
    )
    try:
        result = await accept_revised_rate_confirmation(
            db,
            tenant_id=tenant_id,
            tenant_slug="demo",
            load_id=11,
            pdf_bytes=pdf,
            filename="revised.pdf",
            accepted_fields=fields if fields is not None else _fields(),
            accepted_by_platform_user_id="user-1",
        )
    except RateConfirmationRevisionAcceptError:
        return None, storage, seen
    return result, storage, seen


def test_revision_trigger_clears_only_the_current_flag() -> None:
    text = (ROOT / "alembic_tenant" / "load_rate_confirmation_revision_ddl.py").read_text()
    assert "BEFORE UPDATE OR DELETE" in text
    assert "TG_OP = 'DELETE'" in text
    assert "OLD.is_current IS TRUE" in text
    assert "NEW.is_current IS FALSE" in text
    assert "append_only:load_rate_confirmation_revisions" in text
    assert "uq_load_rc_revisions_one_current" in text
    assert "is_current" in text


def test_accept_is_the_same_write_capability_as_compare() -> None:
    accept = binding_for("POST", "/api/v1/loads/{load_id}/rate-confirmation-revision/accept")
    compare = binding_for("POST", "/api/v1/loads/{load_id}/rate-confirmation-revision/compare")
    assert accept is not None and compare is not None
    assert (accept.resource, accept.action, accept.kind) == (compare.resource, compare.action, compare.kind)
    listed = binding_for("GET", "/api/v1/loads/{load_id}/rate-confirmation-revisions")
    assert listed is not None
    assert listed.kind == "read"


@pytest.mark.asyncio
async def test_accept_writes_rate_and_keeps_the_pdf(monkeypatch) -> None:
    load = _load()
    evidence = _evidence()
    original_json = copy.deepcopy(evidence.accepted_parse_json)
    stop_name = load.stops[0].facility_name
    previous = SimpleNamespace(
        revision_number=1,
        is_current=True,
        file_sha256="b" * 64,
        accepted_changes_json=[{"field": "rate", "old": "1700.00", "new": "1800.00"}],
        filename="older.pdf",
        accepted_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        accepted_by_platform_user_id="user-0",
    )
    db = _Db(load, evidence, [previous])
    result, storage, seen = await _accept(db, monkeypatch)
    assert result is not None
    assert result.revision_number == 2
    assert result.applied_fields == ["rate", "customer_rate"]
    assert result.new_rate == "1500.00"
    assert result.customer_rate_moved is True
    assert load.rate == Decimal("1500.00")
    assert load.customer_rate == Decimal("1500.00")
    assert load.broker_load_reference == "ABC-123"
    assert load.stops[0].facility_name == stop_name
    assert evidence.accepted_parse_json == original_json
    assert previous.is_current is False
    assert db.commits == 1
    assert storage.saved == 1
    assert storage.deleted == 0
    assert seen["parse"] == 1
    assert seen["compare"] == 0
    row = db.added[0]
    assert isinstance(row, LoadRateConfirmationRevision)
    assert row.is_current is True
    assert row.revision_number == 2
    assert row.file_sha256 == PDF_SHA
    assert row.accepted_changes_json == [
        {"field": "rate", "old": "1800.00", "new": "1500.00"},
        {"field": "customer_rate", "old": "1800.00", "new": "1500.00"},
    ]
    assert "raw_text" not in row.new_parse_json
    assert sum(1 for item in db.revisions if item.is_current) == 1


@pytest.mark.asyncio
async def test_customer_rate_stays_when_it_is_not_the_old_rate(monkeypatch) -> None:
    load = _load(customer_rate=Decimal("900.00"))
    db = _Db(load, _evidence())
    result, storage, _seen = await _accept(db, monkeypatch)
    assert result is not None
    assert result.customer_rate_moved is False
    assert result.applied_fields == ["rate"]
    assert load.rate == Decimal("1500.00")
    assert load.customer_rate == Decimal("900.00")
    assert db.added[0].accepted_changes_json == [{"field": "rate", "old": "1800.00", "new": "1500.00"}]
    assert storage.saved == 1


@pytest.mark.asyncio
async def test_dashed_broker_reference_matches_the_compact_reading(monkeypatch) -> None:
    load = _load(broker_load_reference="ABC-123")
    db = _Db(load, _evidence())
    result, _storage, _seen = await _accept(
        db,
        monkeypatch,
        parsed=_parsed(broker_load_reference="ABC123"),
    )
    assert result is not None
    assert result.new_rate == "1500.00"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "saved,revised,warning",
    [
        ("", "ABC123", _NO_SAVED_REF),
        ("ABC-123", "", _NO_REVISED_REF),
        ("ABC-123", "OTHER-9", _DIFFERENT_LOAD),
    ],
)
async def test_unconfirmed_same_load_writes_nothing(monkeypatch, saved, revised, warning) -> None:
    load = _load(broker_load_reference=saved)
    evidence = _evidence()
    evidence.accepted_parse_json["extracted"]["broker_load_reference"] = saved or "ABC-123"
    db = _Db(load, evidence)
    storage = _Storage()
    seen = {"parse": 0}

    async def _parse(*_args, **_kwargs):
        seen["parse"] += 1
        return _parsed(broker_load_reference=revised or None)

    monkeypatch.setattr(
        "app.services.load_rate_confirmation_revision.parse_load_workspace_document_orchestrated",
        _parse,
    )
    monkeypatch.setattr("app.services.load_rate_confirmation_revision.get_storage", lambda: storage)
    with pytest.raises(RateConfirmationRevisionAcceptError) as caught:
        await accept_revised_rate_confirmation(
            db,
            tenant_id=4,
            tenant_slug="demo",
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            accepted_fields=_fields(),
            accepted_by_platform_user_id="user-1",
        )
    assert caught.value.status_code == 409
    assert caught.value.detail == warning
    assert storage.saved == 0
    assert db.commits == 0
    assert load.rate == Decimal("1800.00")
    assert seen["parse"] == 1


@pytest.mark.asyncio
async def test_unverified_or_non_rate_field_writes_nothing(monkeypatch) -> None:
    load = _load()
    db = _Db(load, _evidence())
    _result, storage, _seen = await _accept(db, monkeypatch, fields=_fields(field="mode", new="FTL"))
    with pytest.raises(RateConfirmationRevisionAcceptError) as caught:
        await accept_revised_rate_confirmation(
            db,
            tenant_id=4,
            tenant_slug="demo",
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            accepted_fields=_fields(field="mode", new="FTL"),
            accepted_by_platform_user_id="user-1",
        )
    assert caught.value.status_code == 422
    assert caught.value.detail == _RATE_ONLY
    assert storage.saved == 0
    assert load.rate == Decimal("1800.00")

    parsed = _parsed(rate=Decimal("1800.00"))

    async def _parse(*_args, **_kwargs):
        return parsed

    monkeypatch.setattr(
        "app.services.load_rate_confirmation_revision.parse_load_workspace_document_orchestrated",
        _parse,
    )
    monkeypatch.setattr("app.services.load_rate_confirmation_revision.get_storage", lambda: storage)
    with pytest.raises(RateConfirmationRevisionAcceptError) as unverified:
        await accept_revised_rate_confirmation(
            db,
            tenant_id=4,
            tenant_slug="demo",
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            accepted_fields=_fields(new="1500.00"),
            accepted_by_platform_user_id="user-1",
        )
    assert unverified.value.status_code == 422
    assert unverified.value.detail == _RATE_UNVERIFIED
    assert load.rate == Decimal("1800.00")
    assert db.commits == 0


@pytest.mark.asyncio
async def test_stale_expected_rate_and_duplicate_file_write_nothing(monkeypatch) -> None:
    load = _load()
    db = _Db(load, _evidence())
    storage = _Storage()

    async def _parse(*_args, **_kwargs):
        return _parsed()

    monkeypatch.setattr(
        "app.services.load_rate_confirmation_revision.parse_load_workspace_document_orchestrated",
        _parse,
    )
    monkeypatch.setattr("app.services.load_rate_confirmation_revision.get_storage", lambda: storage)
    with pytest.raises(RateConfirmationRevisionAcceptError) as changed:
        await accept_revised_rate_confirmation(
            db,
            tenant_id=4,
            tenant_slug="demo",
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            accepted_fields=_fields(expected="1700.00"),
            accepted_by_platform_user_id="user-1",
        )
    assert changed.value.status_code == 409
    assert changed.value.detail == _LOAD_CHANGED
    assert storage.saved == 0
    assert load.rate == Decimal("1800.00")

    db.evidence.file_sha256 = PDF_SHA
    with pytest.raises(RateConfirmationRevisionAcceptError) as original:
        await accept_revised_rate_confirmation(
            db,
            tenant_id=4,
            tenant_slug="demo",
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            accepted_fields=_fields(),
            accepted_by_platform_user_id="user-1",
        )
    assert original.value.status_code == 409
    assert original.value.detail == _ALREADY_APPLIED
    assert storage.saved == 0

    db.evidence.file_sha256 = "a" * 64
    db.revisions.append(SimpleNamespace(revision_number=1, is_current=True, file_sha256=PDF_SHA))
    with pytest.raises(RateConfirmationRevisionAcceptError) as repeat:
        await accept_revised_rate_confirmation(
            db,
            tenant_id=4,
            tenant_slug="demo",
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            accepted_fields=_fields(),
            accepted_by_platform_user_id="user-1",
        )
    assert repeat.value.status_code == 409
    assert repeat.value.detail == _ALREADY_APPLIED
    assert db.commits == 0


@pytest.mark.asyncio
async def test_cancelled_and_other_tenant_do_not_parse(monkeypatch) -> None:
    load = _load(status="cancelled")
    db = _Db(load, _evidence())
    storage = _Storage()
    seen = {"parse": 0}

    async def _parse(*_args, **_kwargs):
        seen["parse"] += 1
        return _parsed()

    monkeypatch.setattr(
        "app.services.load_rate_confirmation_revision.parse_load_workspace_document_orchestrated",
        _parse,
    )
    monkeypatch.setattr("app.services.load_rate_confirmation_revision.get_storage", lambda: storage)
    with pytest.raises(RateConfirmationRevisionAcceptError) as cancelled:
        await accept_revised_rate_confirmation(
            db,
            tenant_id=4,
            tenant_slug="demo",
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            accepted_fields=_fields(),
            accepted_by_platform_user_id="user-1",
        )
    assert cancelled.value.status_code == 409
    assert seen["parse"] == 0
    assert storage.saved == 0

    with pytest.raises(RateConfirmationRevisionAcceptError) as missing:
        await accept_revised_rate_confirmation(
            db,
            tenant_id=99,
            tenant_slug="demo",
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            accepted_fields=_fields(),
            accepted_by_platform_user_id="user-1",
        )
    assert missing.value.status_code == 404
    assert seen["parse"] == 0


@pytest.mark.asyncio
async def test_unreadable_pdf_is_422(monkeypatch) -> None:
    parsed = _parsed()
    parsed = parsed.model_copy(update={"context": {"semantic_outcome": "blocked_ocr_required"}})
    db = _Db(_load(), _evidence())
    storage = _Storage()

    async def _parse(*_args, **_kwargs):
        return parsed

    monkeypatch.setattr(
        "app.services.load_rate_confirmation_revision.parse_load_workspace_document_orchestrated",
        _parse,
    )
    monkeypatch.setattr("app.services.load_rate_confirmation_revision.get_storage", lambda: storage)
    with pytest.raises(RateConfirmationRevisionAcceptError) as caught:
        await accept_revised_rate_confirmation(
            db,
            tenant_id=4,
            tenant_slug="demo",
            load_id=11,
            pdf_bytes=PDF,
            filename="revised.pdf",
            accepted_fields=_fields(),
            accepted_by_platform_user_id="user-1",
        )
    assert caught.value.status_code == 422
    assert caught.value.detail == _UNREADABLE_PDF
    assert storage.saved == 0
    assert db.commits == 0


@pytest.mark.asyncio
async def test_list_returns_old_and_new_rate(monkeypatch) -> None:
    row = SimpleNamespace(
        revision_number=1,
        filename="revised.pdf",
        accepted_at=datetime(2026, 10, 27, tzinfo=timezone.utc),
        accepted_by_platform_user_id="user-1",
        is_current=True,
        accepted_changes_json=[{"field": "rate", "old": "1800.00", "new": "1500.00"}],
    )
    db = _Db(_load(), _evidence(), [row])
    listed = await list_rate_confirmation_revisions(db, tenant_id=4, load_id=11)
    assert len(listed.items) == 1
    assert listed.items[0].revision_number == 1
    assert listed.items[0].old_rate == "1800.00"
    assert listed.items[0].new_rate == "1500.00"
    assert listed.items[0].is_current is True
    assert listed.items[0].accepted_by == "user-1"


@pytest.mark.asyncio
async def test_pdf_view_uses_current_revision_or_original(monkeypatch) -> None:
    current = SimpleNamespace(
        revision_number=2,
        filename="current.pdf",
        is_current=True,
        file_sha256=PDF_SHA,
        storage_key="demo/load_workspace_drafts/load_rc_revision/11/current.pdf",
    )
    older = SimpleNamespace(
        revision_number=1,
        filename="older.pdf",
        is_current=False,
        file_sha256="b" * 64,
        storage_key="demo/load_workspace_drafts/load_rc_revision/11/older.pdf",
    )
    db = _Db(_load(), _evidence(), [older, current])

    def _read(storage_key, **_kwargs):
        return storage_key.encode()

    async def _original(*_args, **_kwargs):
        return SimpleNamespace(filename="original.pdf"), b"original-pdf"

    monkeypatch.setattr("app.services.load_rate_confirmation_revision.read_object_bytes", _read)
    monkeypatch.setattr(
        "app.services.load_rate_confirmation_revision.read_load_rate_confirmation_pdf_bytes",
        _original,
    )
    name, body = await read_rate_confirmation_pdf_for_view(
        db, tenant_id=4, load_id=11, tenant_slug="demo", revision=None
    )
    assert name == "current.pdf"
    assert body == current.storage_key.encode()
    name, body = await read_rate_confirmation_pdf_for_view(
        db, tenant_id=4, load_id=11, tenant_slug="demo", revision=0
    )
    assert name == "original.pdf"
    assert body == b"original-pdf"
    name, body = await read_rate_confirmation_pdf_for_view(
        db, tenant_id=4, load_id=11, tenant_slug="demo", revision=1
    )
    assert name == "older.pdf"
    assert body == older.storage_key.encode()
