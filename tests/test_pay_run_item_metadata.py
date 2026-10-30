"""Tracing metadata on generated pay run items (reference_code + optional load trip read-model).

Tests the helper only. In generate_pay_run, load resolution uses a transitional
numeric reference_code → load id rule; see docs/load_trip/MASTER.md.
"""

from types import SimpleNamespace

from app.routers.pay_runs import _pay_run_item_metadata


def test_metadata_reference_only_when_no_load():
    entry = SimpleNamespace(reference_code="ABC-1")
    assert _pay_run_item_metadata(entry, None) == {"reference_code": "ABC-1"}


def test_metadata_includes_trip_when_load_provided():
    entry = SimpleNamespace(reference_code="42")
    load = SimpleNamespace(id=42, trip_number="T-100", active_dispatch_trip_id=99)
    assert _pay_run_item_metadata(entry, load) == {
        "reference_code": "42",
        "load_id": 42,
        "trip_number": "T-100",
        "dispatch_trip_id": 99,
    }


def test_metadata_omits_empty_trip_fields():
    entry = SimpleNamespace(reference_code="x")
    load = SimpleNamespace(id=1, trip_number=None, active_dispatch_trip_id=None)
    assert _pay_run_item_metadata(entry, load) == {"reference_code": "x", "load_id": 1}


# ---- generate_pay_run sign/payee rules (fake session; installed pay_run_items schema differs from ORM) ----

from decimal import Decimal

import pytest
from fastapi import HTTPException

import app.main  # noqa: F401  (configure every ORM mapper before instantiating Payee)
from app.models.enums import PayRunStatus, SourceType, WorkerType
from app.routers.pay_runs import _compute_totals, generate_pay_run


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, *, scalars, executes):
        self._scalars = list(scalars)
        self._executes = list(executes)
        self.added = []
        self.committed = False

    async def scalar(self, _stmt):
        return self._scalars.pop(0)

    async def execute(self, _stmt):
        return _Result(self._executes.pop(0))

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None and type(obj).__name__ == "Payee":
            obj.id = 501

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True


def _entry(entry_type, amount, driver_id=7):
    return SimpleNamespace(
        driver_id=driver_id, entry_type=entry_type, amount=Decimal(amount), quantity=None,
        rate_amount=None, reference_code="",
    )


def _run(status=PayRunStatus.GENERATED):
    return SimpleNamespace(id=3, pay_period_id=9, status=status, base_currency_snapshot="USD")


@pytest.mark.asyncio
async def test_generate_maps_deduction_negative_and_net_matches_period_summary():
    driver = SimpleNamespace(id=7, payee_id=55, person_id=None, first_name="A", last_name="B")
    db = _FakeSession(
        scalars=[_run(), SimpleNamespace(status="CLOSED")],
        executes=[[], [_entry("GROSS", "1000.00"), _entry("DEDUCTION", "150.00"), _entry("ADJUSTMENT", "-20.00")], [driver]],
    )
    out = await generate_pay_run(run_id=3, tenant_id=1, db=db)
    assert out.item_count == 3 and db.committed
    items = [o for o in db.added if type(o).__name__ == "PayRunItem"]
    assert [(i.source_type, i.amount_signed) for i in items] == [
        (SourceType.EARNING.value, Decimal("1000.00")),
        (SourceType.DEDUCTION.value, Decimal("-150.00")),
        (SourceType.EARNING.value, Decimal("-20.00")),
    ]
    totals = _compute_totals(items)
    # Period summary: earnings(GROSS+ADJUSTMENT)=980 - deductions 150 = 830.
    assert totals["gross"] == Decimal("980.00")
    assert totals["net"] == Decimal("830.00")


@pytest.mark.asyncio
async def test_generate_refuses_finalized_run():
    db = _FakeSession(scalars=[_run(PayRunStatus.FINALIZED)], executes=[])
    with pytest.raises(HTTPException) as exc:
        await generate_pay_run(run_id=3, tenant_id=1, db=db)
    assert exc.value.status_code == 409 and not db.added and not db.committed


@pytest.mark.asyncio
async def test_generate_no_payee_unknown_classification_fails_without_employee_default():
    driver = SimpleNamespace(id=7, payee_id=None, person_id=None, first_name="A", last_name="B")
    db = _FakeSession(
        scalars=[_run(), SimpleNamespace(status="CLOSED")],
        executes=[[], [_entry("GROSS", "10.00")], [driver]],
    )
    with pytest.raises(HTTPException) as exc:
        await generate_pay_run(run_id=3, tenant_id=1, db=db)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "PAYRUN_PAYEE_CLASSIFICATION_REQUIRED"
    assert not db.added and not db.committed


@pytest.mark.asyncio
async def test_generate_no_payee_owner_operator_gets_owner_operator_payee():
    driver = SimpleNamespace(id=7, payee_id=None, person_id=12, first_name="A", last_name="B")
    ext = SimpleNamespace(employment_relationship_type="owner_operator")
    db = _FakeSession(
        scalars=[_run(), SimpleNamespace(status="CLOSED"), ext],
        executes=[[], [_entry("GROSS", "10.00")], [driver]],
    )
    await generate_pay_run(run_id=3, tenant_id=1, db=db)
    payees = [o for o in db.added if type(o).__name__ == "Payee"]
    assert len(payees) == 1 and payees[0].worker_type == WorkerType.OWNER_OPERATOR_LEASED_ON
    assert driver.payee_id == 501
