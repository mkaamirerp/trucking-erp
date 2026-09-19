"""Fuel Segment 9 — deterministic reconciliation engine."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.deps.auth import get_current_user
from app.deps.entitlements import require_admin_sensitive_entitlement
from app.deps.fuel_rbac import (
    FUEL_RECONCILIATION_RUN,
    FUEL_RECONCILIATION_VIEW,
    fuel_capability_allowed,
)
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.fuel import FuelSourceBatch
from app.routers import fuel as fuel_router
from app.services.fuel_canonical import (
    BATCH_STATUS_BLOCKED,
    BATCH_STATUS_READY_FOR_RECONCILIATION,
    BATCH_STATUS_RECONCILED,
    BATCH_STATUS_RECONCILIATION_FAILED,
    ROW_REVIEW_CONFIRMED,
)
from app.services import fuel_reconciliation as recon


def _txn(
    *,
    id: int = 1,
    total_amount: str = "10.0000",
    currency: str = "CAD",
    card: str | None = None,
    unit: str | None = None,
    product: str | None = None,
    source_row_order: int = 1,
    gst_amount: str | None = None,
    provider_discount_amount: str | None = None,
    provider_event_type: str = "PURCHASE",
    provider_raw: dict | None = None,
    requires_review: bool = False,
    parsed_row_role: str = "TRANSACTION",
    reviewed_row_role: str | None = None,
) -> dict:
    return {
        "id": id,
        "source_row_order": source_row_order,
        "total_amount": Decimal(total_amount),
        "currency": currency,
        "card_or_account_id": card,
        "unit_number_snapshot": unit,
        "product": product,
        "product_code_raw": product,
        "gst_amount": None if gst_amount is None else Decimal(gst_amount),
        "provider_discount_amount": (
            None if provider_discount_amount is None else Decimal(provider_discount_amount)
        ),
        "provider_event_type": provider_event_type,
        "provider_raw": provider_raw or {},
        "requires_review": requires_review,
        "parsed_row_role": parsed_row_role,
        "reviewed_row_role": reviewed_row_role,
    }


def _ctrl(
    *,
    id: int = 100,
    control_type: str,
    declared_amount: str | None,
    currency: str | None = "CAD",
    card: str | None = None,
    unit: str | None = None,
    product: str | None = None,
    source_row_order: int | None = 50,
    label: str | None = None,
    control_scope: str = "BATCH",
    invoice_number: str | None = None,
    provider_control_identity: str | None = None,
) -> dict:
    return {
        "id": id,
        "source_row_order": source_row_order,
        "control_type": control_type,
        "control_scope": control_scope,
        "declared_amount": None if declared_amount is None else Decimal(declared_amount),
        "currency": currency,
        "scope_card_or_account_id": card,
        "scope_unit_number_snapshot": unit,
        "scope_product_raw": product,
        "control_label_raw": label,
        "control_type_raw": label,
        "invoice_number": invoice_number,
        "provider_control_identity": provider_control_identity,
    }


def test_reconciliation_rbac_requires_admin() -> None:
    assert fuel_capability_allowed("TENANT_ADMIN", FUEL_RECONCILIATION_VIEW) is True
    assert fuel_capability_allowed("TENANT_ADMIN", FUEL_RECONCILIATION_RUN) is True
    assert fuel_capability_allowed("TENANT_MEMBER", FUEL_RECONCILIATION_VIEW) is False
    assert fuel_capability_allowed("TENANT_MEMBER", FUEL_RECONCILIATION_RUN) is False


def test_invoice_total_reconciles_with_decimal_sum() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[
            _txn(id=1, total_amount="1610.9600", source_row_order=1),
            _txn(id=2, total_amount="1810.0500", source_row_order=2),
        ],
        controls=[
            _ctrl(
                id=10,
                control_type="INVOICE_TOTAL",
                declared_amount="3421.0100",
                source_row_order=99,
            )
        ],
    )
    assert report.outcome == recon.OUTCOME_RECONCILED
    assert report.gates[0].status == recon.GATE_PASS
    assert report.gates[0].difference == Decimal("0.0000")
    dumped = report.to_dict()
    assert dumped["ai_authority"] is False
    assert dumped["finalization_implemented"] is False
    assert dumped["financial_responsibility_implemented"] is False
    assert report.finalization_implemented is False
    assert report.financial_responsibility_implemented is False


def test_mismatch_fails_with_amount_mismatch() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="10.0000")],
        controls=[_ctrl(control_type="INVOICE_TOTAL", declared_amount="11.0000")],
    )
    assert report.outcome == recon.OUTCOME_RECONCILIATION_FAILED
    assert report.gates[0].status == recon.GATE_FAIL
    assert report.gates[0].difference == Decimal("-1.0000")
    assert report.gates[0].reason == "AMOUNT_MISMATCH"
    assert report.unexplained_variances


def test_provider_variance_row_does_not_force_pass() -> None:
    """VARIANCE is provider evidence only — never masks a nonzero mismatch."""
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="NATIONWIDE",
        transactions=[_txn(total_amount="10.0000")],
        controls=[
            _ctrl(id=1, control_type="INVOICE_TOTAL", declared_amount="10.0100", source_row_order=90),
            _ctrl(
                id=2,
                control_type="VARIANCE",
                declared_amount="-0.0100",
                source_row_order=91,
            ),
        ],
    )
    assert report.outcome == recon.OUTCOME_RECONCILIATION_FAILED
    invoice_gate = next(g for g in report.gates if g.control_type == "INVOICE_TOTAL")
    variance_gate = next(g for g in report.gates if g.control_type == "VARIANCE")
    assert invoice_gate.status == recon.GATE_FAIL
    assert invoice_gate.reason == "AMOUNT_MISMATCH"
    assert variance_gate.status == recon.GATE_SKIPPED
    assert "DOES_NOT_FORCE_PASS" in (variance_gate.reason or "")


def test_cad_and_usd_reconcile_independently() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="NATIONWIDE",
        transactions=[
            _txn(id=1, total_amount="100.0000", currency="CAD", source_row_order=1),
            _txn(id=2, total_amount="50.0000", currency="USD", source_row_order=2),
        ],
        controls=[
            _ctrl(
                id=1,
                control_type="CURRENCY_TOTAL",
                declared_amount="100.0000",
                currency="CAD",
                source_row_order=80,
            ),
            _ctrl(
                id=2,
                control_type="CURRENCY_TOTAL",
                declared_amount="50.0000",
                currency="USD",
                source_row_order=81,
            ),
        ],
    )
    assert report.outcome == recon.OUTCOME_RECONCILED
    assert set(report.currencies) == {"CAD", "USD"}
    assert report.validated_totals_by_currency["CAD"] == "100.0000"
    assert report.validated_totals_by_currency["USD"] == "50.0000"


def test_batch_total_without_currency_blocks_multi_currency() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="NATIONWIDE",
        transactions=[
            _txn(id=1, total_amount="100.0000", currency="CAD", source_row_order=1),
            _txn(id=2, total_amount="50.0000", currency="USD", source_row_order=2),
        ],
        controls=[
            _ctrl(
                control_type="INVOICE_TOTAL",
                declared_amount="150.0000",
                currency=None,
            )
        ],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any(
        g.reason == "MULTI_CURRENCY_BATCH_TOTAL_REQUIRES_CURRENCY_SCOPE" for g in report.gates
    )


def test_card_total_scoped_independently() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="NATIONWIDE",
        transactions=[
            _txn(id=1, total_amount="40.0000", card="87115", source_row_order=1),
            _txn(id=2, total_amount="60.0000", card="87195", source_row_order=2),
        ],
        controls=[
            _ctrl(
                id=1,
                control_type="CARD_TOTAL",
                declared_amount="40.0000",
                card="87115",
                source_row_order=70,
            ),
            _ctrl(
                id=2,
                control_type="CARD_TOTAL",
                declared_amount="60.0000",
                card="87195",
                source_row_order=71,
            ),
            _ctrl(
                id=3,
                control_type="INVOICE_TOTAL",
                declared_amount="100.0000",
                source_row_order=72,
            ),
        ],
    )
    assert report.outcome == recon.OUTCOME_RECONCILED


def test_unit_and_product_subtotals() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[
            _txn(id=1, total_amount="25.0000", unit="1100", product="DSL", source_row_order=1),
            _txn(id=2, total_amount="15.0000", unit="1100", product="DEF", source_row_order=2),
            _txn(id=3, total_amount="10.0000", unit="2200", product="DSL", source_row_order=3),
        ],
        controls=[
            _ctrl(
                id=1,
                control_type="UNIT_SUBTOTAL",
                declared_amount="40.0000",
                unit="1100",
                control_scope="UNIT",
                source_row_order=60,
            ),
            _ctrl(
                id=2,
                control_type="PRODUCT_SUBTOTAL",
                declared_amount="35.0000",
                product="DSL",
                control_scope="PRODUCT",
                source_row_order=61,
            ),
            _ctrl(
                id=3,
                control_type="INVOICE_TOTAL",
                declared_amount="50.0000",
                control_scope="BATCH",
                source_row_order=62,
            ),
        ],
    )
    assert report.outcome == recon.OUTCOME_RECONCILED


def test_tax_control_uses_gst_field() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="NATIONWIDE",
        transactions=[
            _txn(id=1, total_amount="100.0000", gst_amount="5.0000", source_row_order=1),
            _txn(id=2, total_amount="200.0000", gst_amount="10.0000", source_row_order=2),
        ],
        controls=[
            _ctrl(
                id=1,
                control_type="INVOICE_TOTAL",
                declared_amount="300.0000",
                source_row_order=50,
            ),
            _ctrl(
                id=2,
                control_type="TAX_CONTROL",
                declared_amount="15.0000",
                label="GST $15.00",
                source_row_order=51,
            ),
        ],
    )
    assert report.outcome == recon.OUTCOME_RECONCILED
    tax_gate = next(g for g in report.gates if g.control_type == "TAX_CONTROL")
    assert tax_gate.status == recon.GATE_PASS
    assert tax_gate.computed_amount == Decimal("15.0000")


def test_credits_preserve_sign_in_sum() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[
            _txn(id=1, total_amount="100.0000", source_row_order=1),
            _txn(id=2, total_amount="-25.0000", source_row_order=2),
        ],
        controls=[_ctrl(control_type="INVOICE_TOTAL", declared_amount="75.0000")],
    )
    assert report.outcome == recon.OUTCOME_RECONCILED


def test_unknown_control_blocks() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="10.0000")],
        controls=[
            _ctrl(control_type="INVOICE_TOTAL", declared_amount="10.0000", source_row_order=1),
            _ctrl(
                id=2,
                control_type="UNKNOWN",
                declared_amount="1.0000",
                source_row_order=2,
            ),
        ],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED


def test_missing_transaction_amount_blocks() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[{"id": 1, "source_row_order": 1, "total_amount": None, "currency": "CAD"}],
        controls=[_ctrl(control_type="INVOICE_TOTAL", declared_amount="0.0000")],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any("TRANSACTION_TOTAL_AMOUNT_MISSING" in b for b in report.blockers)


def test_no_controls_blocks() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="10.0000")],
        controls=[],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert "NO_PROVIDER_CONTROLS" in report.blockers


def test_double_count_source_row_blocks() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="10.0000", source_row_order=5)],
        controls=[_ctrl(control_type="INVOICE_TOTAL", declared_amount="10.0000", source_row_order=5)],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any("both" in b.lower() or "Source row" in b for b in report.blockers)


def test_controls_never_enter_purchase_total() -> None:
    """Control declared amounts must not inflate validated transaction totals."""
    txns = [_txn(total_amount="10.0000")]
    controls = [_ctrl(control_type="CARD_TOTAL", declared_amount="999.0000", card="1")]
    # purchase helper sums txns only
    from app.services.fuel_controls import purchase_total_from_transactions

    assert purchase_total_from_transactions([t["total_amount"] for t in txns]) == Decimal("10.0000")
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=txns,
        controls=controls
        + [_ctrl(id=2, control_type="INVOICE_TOTAL", declared_amount="10.0000", source_row_order=88)],
    )
    # Card scope with no matching card → computed 0 vs 999 → fail, but invoice can pass
    assert report.validated_totals_by_currency["CAD"] == "10.0000"


def test_float_forbidden_in_money_helpers() -> None:
    with pytest.raises(Exception):
        recon.sum_transaction_totals([{"total_amount": 1.5, "currency": "CAD"}])


@pytest.mark.asyncio
async def test_reconcile_batch_persists_status_and_report() -> None:
    batch = SimpleNamespace(
        id=9,
        tenant_id=53,
        provider_code="BVD",
        status=BATCH_STATUS_READY_FOR_RECONCILIATION,
        problem_summary_json={},
        updated_by=None,
    )
    txn = SimpleNamespace(
        id=1,
        tenant_id=53,
        batch_id=9,
        source_row_order=1,
        total_amount=Decimal("10.0000"),
        currency="CAD",
        card_or_account_id=None,
        unit_number_snapshot=None,
        product=None,
        product_code_raw=None,
        gst_amount=None,
        hst_amount=None,
        pst_amount=None,
        qst_amount=None,
        tax_amount=None,
        provider_discount_amount=None,
        provider_event_type="PURCHASE",
        provider_raw={},
        requires_review=False,
        parsed_row_role="TRANSACTION",
        reviewed_row_role=None,
        review_status=ROW_REVIEW_CONFIRMED,
        gate_status=None,
    )
    ctrl = SimpleNamespace(
        id=10,
        tenant_id=53,
        batch_id=9,
        source_row_order=99,
        control_type="INVOICE_TOTAL",
        control_scope="BATCH",
        declared_amount=Decimal("10.0000"),
        currency="CAD",
        scope_card_or_account_id=None,
        scope_unit_number_snapshot=None,
        scope_product_raw=None,
        control_label_raw="Grand Total",
        control_type_raw="Grand Total",
        provider_control_identity=None,
        invoice_number=None,
        gst_amount=None,
        hst_amount=None,
        pst_amount=None,
        qst_amount=None,
        tax_amount=None,
        review_status=ROW_REVIEW_CONFIRMED,
    )

    class _ScalarResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    db = AsyncMock()

    async def _scalars(stmt):
        text = str(stmt)
        if "fuel_transactions" in text or "FuelTransaction" in text:
            return _ScalarResult([txn])
        return _ScalarResult([ctrl])

    # sqlalchemy select().where uses entity; AsyncMock scalars needs side_effect by call order
    call_n = {"n": 0}

    async def _scalars_ordered(stmt):
        call_n["n"] += 1
        if call_n["n"] == 1:
            return _ScalarResult([txn])
        return _ScalarResult([ctrl])

    db.scalars = AsyncMock(side_effect=_scalars_ordered)
    db.flush = AsyncMock()

    actor = SimpleNamespace(user_id=7, email="admin@example.com")

    # Patch audit so we don't need full DB
    async def _audit(*args, **kwargs):
        return None

    monkey = pytest.MonkeyPatch()
    monkey.setattr(recon, "write_audit_event", _audit)
    try:
        out = await recon.reconcile_batch(db, tenant_id=53, batch=batch, actor=actor)
    finally:
        monkey.undo()

    assert out["outcome"] == recon.OUTCOME_RECONCILED
    assert batch.status == BATCH_STATUS_RECONCILED
    assert batch.problem_summary_json["reconciliation"]["outcome"] == recon.OUTCOME_RECONCILED
    assert txn.gate_status == recon.GATE_PASS
    assert out["finalization_implemented"] is False
    assert out["financial_responsibility_implemented"] is False
    assert out["ai_authority"] is False


@pytest.mark.asyncio
async def test_reconcile_batch_rejects_unready_status() -> None:
    batch = SimpleNamespace(
        id=1,
        tenant_id=53,
        provider_code="BVD",
        status="IN_REVIEW",
        problem_summary_json={},
    )
    db = AsyncMock()
    with pytest.raises(recon.FuelReconciliationError) as exc:
        await recon.reconcile_batch(
            db, tenant_id=53, batch=batch, actor=SimpleNamespace(user_id=1)
        )
    assert exc.value.code == "BATCH_NOT_READY"


def test_api_run_reconciliation_endpoint(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(fuel_router.router, prefix="/api/v1")

    async def _user():
        return SimpleNamespace(
            user_id=7,
            tenant_id=53,
            role="TENANT_ADMIN",
            email="admin@example.com",
            member_id=7,
            user=SimpleNamespace(email="admin@example.com"),
        )

    async def _skip():
        return None

    async def _tdb():
        yield AsyncMock()

    async def _pdb():
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[require_tenant] = lambda: 53
    app.dependency_overrides[require_admin_sensitive_entitlement] = _skip
    app.dependency_overrides[get_tenant_db] = _tdb
    app.dependency_overrides[get_db] = _pdb

    batch = SimpleNamespace(
        id=3,
        tenant_id=53,
        provider_code="BVD",
        status=BATCH_STATUS_READY_FOR_RECONCILIATION,
        problem_summary_json={},
    )

    async def _get_batch(db, *, tenant_id, batch_id):
        return batch

    async def _run(db, *, tenant_id, batch, actor):
        return {
            "outcome": recon.OUTCOME_RECONCILED,
            "status": BATCH_STATUS_RECONCILED,
            "batch_id": batch.id,
            "tenant_id": tenant_id,
            "provider_code": "BVD",
            "transaction_count": 1,
            "control_count": 1,
            "gates": [],
            "unexplained_variances": [],
            "blockers": [],
            "currencies": ["CAD"],
            "validated_totals_by_currency": {"CAD": "10.0000"},
            "provider_totals_by_currency": {"CAD": "10.0000"},
            "finalization_implemented": False,
            "financial_responsibility_implemented": False,
            "ai_authority": False,
            "reconciled_at": "2026-09-19T00:00:00+00:00",
            "reconciled_by": "7",
        }

    monkeypatch.setattr(recon, "get_batch", _get_batch)
    monkeypatch.setattr(recon, "reconcile_batch", _run)
    # router imports reconciliation_service alias — patch on router module
    monkeypatch.setattr(fuel_router.reconciliation_service, "get_batch", _get_batch)
    monkeypatch.setattr(fuel_router.reconciliation_service, "reconcile_batch", _run)

    client = TestClient(app)
    resp = client.post("/api/v1/fuel/reconciliation/batches/3/run", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["outcome"] == "RECONCILED"
    assert body["finalization_implemented"] is False
    assert body["ai_authority"] is False


def test_invoice_scoped_control_sums_matching_invoice_only() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[
            _txn(
                id=1,
                total_amount="100.0000",
                source_row_order=1,
                provider_raw={"invoice_number": "972201"},
            ),
            _txn(
                id=2,
                total_amount="50.0000",
                source_row_order=2,
                provider_raw={"invoice_number": "999999"},
            ),
        ],
        controls=[
            _ctrl(
                id=1,
                control_type="INVOICE_TOTAL",
                declared_amount="100.0000",
                control_scope="INVOICE",
                invoice_number="972201",
                source_row_order=80,
            )
        ],
    )
    assert report.outcome == recon.OUTCOME_RECONCILED
    assert report.gates[0].scope_key == "INVOICE:972201"
    assert report.gates[0].computed_amount == Decimal("100.0000")


def test_statement_scoped_control_batch_wide() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="NATIONWIDE",
        transactions=[
            _txn(id=1, total_amount="40.0000", source_row_order=1),
            _txn(id=2, total_amount="60.0000", source_row_order=2),
        ],
        controls=[
            _ctrl(
                control_type="STATEMENT_TOTAL",
                declared_amount="100.0000",
                control_scope="STATEMENT",
                invoice_number="20250522B-06142026",
            )
        ],
    )
    assert report.outcome == recon.OUTCOME_RECONCILED


def test_invoice_total_ambiguous_scope_blocks() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="10.0000")],
        controls=[
            _ctrl(
                control_type="INVOICE_TOTAL",
                declared_amount="10.0000",
                control_scope="UNKNOWN",
            )
        ],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any(
        "AMBIGUOUS" in (g.reason or "") or "NOT_DETERMINISTIC" in (g.reason or "")
        for g in report.gates
    )


def test_invoice_scope_missing_invoice_number_blocks() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="10.0000")],
        controls=[
            _ctrl(
                control_type="INVOICE_TOTAL",
                declared_amount="10.0000",
                control_scope="INVOICE",
                invoice_number=None,
            )
        ],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any(g.reason == "INVOICE_SCOPE_MISSING_INVOICE_NUMBER" for g in report.gates)


def test_multiple_invoice_scopes_without_txn_partition_blocks() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[
            _txn(id=1, total_amount="100.0000", source_row_order=1),
            _txn(id=2, total_amount="50.0000", source_row_order=2),
        ],
        controls=[
            _ctrl(
                id=1,
                control_type="INVOICE_TOTAL",
                declared_amount="100.0000",
                control_scope="INVOICE",
                invoice_number="A",
                source_row_order=80,
            ),
            _ctrl(
                id=2,
                control_type="INVOICE_TOTAL",
                declared_amount="50.0000",
                control_scope="INVOICE",
                invoice_number="B",
                source_row_order=81,
            ),
        ],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any(g.reason == "MULTI_INVOICE_SCOPE_WITHOUT_TXN_PARTITION" for g in report.gates)


def test_multiple_invoice_scopes_with_txn_partition_pass() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[
            _txn(
                id=1,
                total_amount="100.0000",
                source_row_order=1,
                provider_raw={"invoice_number": "A"},
            ),
            _txn(
                id=2,
                total_amount="50.0000",
                source_row_order=2,
                provider_raw={"invoice_number": "B"},
            ),
        ],
        controls=[
            _ctrl(
                id=1,
                control_type="INVOICE_TOTAL",
                declared_amount="100.0000",
                control_scope="INVOICE",
                invoice_number="A",
                source_row_order=80,
            ),
            _ctrl(
                id=2,
                control_type="INVOICE_TOTAL",
                declared_amount="50.0000",
                control_scope="INVOICE",
                invoice_number="B",
                source_row_order=81,
            ),
        ],
    )
    assert report.outcome == recon.OUTCOME_RECONCILED


def test_group_subtotal_valid_deterministic_group() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="NATIONWIDE",
        transactions=[
            _txn(
                id=1,
                total_amount="30.0000",
                source_row_order=1,
                provider_raw={"group_key": "G1"},
            ),
            _txn(
                id=2,
                total_amount="20.0000",
                source_row_order=2,
                provider_raw={"group_key": "G1"},
            ),
            _txn(
                id=3,
                total_amount="99.0000",
                source_row_order=3,
                provider_raw={"group_key": "G2"},
            ),
        ],
        controls=[
            _ctrl(
                id=1,
                control_type="GROUP_SUBTOTAL",
                declared_amount="50.0000",
                control_scope="GROUP",
                provider_control_identity="G1",
                source_row_order=70,
            ),
            _ctrl(
                id=2,
                control_type="INVOICE_TOTAL",
                declared_amount="149.0000",
                control_scope="BATCH",
                source_row_order=71,
            ),
        ],
    )
    assert report.outcome == recon.OUTCOME_RECONCILED
    group_gate = next(g for g in report.gates if g.control_type == "GROUP_SUBTOTAL")
    assert group_gate.computed_amount == Decimal("50.0000")


def test_group_subtotal_missing_key_blocks() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="10.0000", provider_raw={"group_key": "G1"})],
        controls=[
            _ctrl(
                control_type="GROUP_SUBTOTAL",
                declared_amount="10.0000",
                control_scope="GROUP",
                provider_control_identity=None,
            )
        ],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any(g.reason == "GROUP_KEY_MISSING" for g in report.gates)


def test_group_subtotal_no_txn_group_identity_blocks() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="10.0000")],
        controls=[
            _ctrl(
                control_type="GROUP_SUBTOTAL",
                declared_amount="10.0000",
                control_scope="GROUP",
                provider_control_identity="G1",
            )
        ],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any(g.reason == "GROUP_MEMBERSHIP_NOT_DETERMINISTIC" for g in report.gates)


def test_group_subtotal_does_not_fall_back_to_product() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="10.0000", product="DSL")],
        controls=[
            _ctrl(
                control_type="GROUP_SUBTOTAL",
                declared_amount="10.0000",
                control_scope="PRODUCT",
                product="DSL",
                provider_control_identity="G1",
            )
        ],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any(g.reason == "GROUP_SUBTOTAL_REQUIRES_CONTROL_SCOPE_GROUP" for g in report.gates)


def test_unknown_event_with_money_blocks_pass() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="10.0000", provider_event_type="UNKNOWN")],
        controls=[_ctrl(control_type="INVOICE_TOTAL", declared_amount="10.0000")],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any("UNRESOLVED_FINANCIAL_TRANSACTION_EVENT" in b for b in report.blockers)


def test_other_event_with_money_blocks_pass() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="5.0000", provider_event_type="OTHER")],
        controls=[_ctrl(control_type="INVOICE_TOTAL", declared_amount="5.0000")],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any("UNRESOLVED_FINANCIAL_TRANSACTION_EVENT" in b for b in report.blockers)


def test_unresolved_row_role_with_money_blocks() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[
            _txn(
                total_amount="10.0000",
                parsed_row_role="UNKNOWN",
                reviewed_row_role="UNKNOWN",
            )
        ],
        controls=[_ctrl(control_type="INVOICE_TOTAL", declared_amount="10.0000")],
    )
    assert report.outcome == recon.OUTCOME_BLOCKED
    assert any("UNRESOLVED_FINANCIAL_TRANSACTION_ROW_ROLE" in b for b in report.blockers)


def test_provider_declared_total_batch_scope() -> None:
    report = recon.reconcile_transactions_and_controls(
        tenant_id=53,
        batch_id=1,
        provider_code="BVD",
        transactions=[_txn(total_amount="12.5000")],
        controls=[
            _ctrl(
                control_type="PROVIDER_DECLARED_TOTAL",
                declared_amount="12.5000",
                control_scope="BATCH",
            )
        ],
    )
    assert report.outcome == recon.OUTCOME_RECONCILED
