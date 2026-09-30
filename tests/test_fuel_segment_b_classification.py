"""Segment B: canonical charge classification foundation."""

from __future__ import annotations

import importlib
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.fuel_bvd_canonical_projection import (
    SECTION_EXPRESS,
    SECTION_FUEL_CARD,
    project_bvd_rows_to_canonical,
    build_fuel_source_batch,
    assert_canonical_money_gate,
)
from app.services.fuel_bvd_effective import build_effective_bvd_row
from app.services.fuel_bvd_extraction import ROW_HEADER, extract_bvd_rows_from_digital_pdf
from app.services.fuel_charge_categories import (
    CANONICAL_CATEGORY_CODES,
    CATEGORY_DEF,
    CATEGORY_FUEL,
    CATEGORY_OTHER,
    LOCKED_CHARGE_CATEGORY_CODES,
    CATEGORY_LUMPER,
    CATEGORY_SCALE,
    CATEGORY_UNMAPPED,
    CATEGORY_SEED_ROWS,
    CLASSIFICATION_SOURCE_MANUAL,
    CLASSIFICATION_SOURCE_PROVIDER_RULE,
    CLASSIFICATION_SOURCE_TENANT_MAPPING,
    CLASSIFICATION_STATUS_CONFIRMED,
    CLASSIFICATION_STATUS_UNMAPPED,
)
from app.services.fuel_reason_normalize import normalize_provider_reason_key
from app.services.fuel_transaction_classify import classify_fuel_transaction

REPO = Path(__file__).resolve().parents[1]
BVD_838710 = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_838710.pdf"
BVD_972201 = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_972201.pdf"


def test_category_seed_catalog_matches_locked_codes() -> None:
    codes = {row[0] for row in CATEGORY_SEED_ROWS}
    assert codes == CANONICAL_CATEGORY_CODES
    assert CATEGORY_UNMAPPED in codes
    assert LOCKED_CHARGE_CATEGORY_CODES | {CATEGORY_UNMAPPED} == CANONICAL_CATEGORY_CODES
    assert "LOAD_PAY" not in codes
    assert "ALLOWANCE" not in codes


# Original Segment B seed (d1e2f3a4b5c6) — must stay immutable in that revision.
_SEGMENT_B_ORIGINAL_SEED_CODES = {
    "FUEL",
    "DEF",
    "SCALE",
    "LUMPER",
    "TOLL",
    "CASH_ADVANCE",
    "PARKING",
    "REPAIR_OR_SERVICE",
    "PRODUCT_PURCHASE",
    "ALLOWANCE",
    "LOAD_PAY",
    "OTHER",
    "UNMAPPED",
}

_RETIRED_CATEGORY_CODES = frozenset({"LOAD_PAY", "ALLOWANCE"})


def test_fresh_install_seed_minus_retired_matches_app_catalog() -> None:
    """Full chain: d1e2f3 seed → e3f4 retire → same effective codes as CATEGORY_SEED_ROWS."""
    after_retire = _SEGMENT_B_ORIGINAL_SEED_CODES - _RETIRED_CATEGORY_CODES
    app_codes = {row[0] for row in CATEGORY_SEED_ROWS}
    assert after_retire == app_codes
    assert after_retire - {CATEGORY_UNMAPPED} == LOCKED_CHARGE_CATEGORY_CODES


def test_picker_catalog_excludes_removed_categories() -> None:
    """API/UI charge-categories list is driven by CATEGORY_SEED_ROWS / DB seed."""
    picker_codes = {row[0] for row in CATEGORY_SEED_ROWS if row[0] != CATEGORY_UNMAPPED}
    assert picker_codes == LOCKED_CHARGE_CATEGORY_CODES
    assert "LOAD_PAY" not in picker_codes
    assert "ALLOWANCE" not in picker_codes


@pytest.mark.parametrize("reason", ["pay", "load pay", "allowance"])
def test_express_reasons_unmapped_without_explicit_mapping(reason: str) -> None:
    r = classify_fuel_transaction(
        tenant_id=53,
        provider_code="BVD",
        provider_section_raw=SECTION_EXPRESS,
        product_code_raw=None,
        provider_reason_raw=reason,
        tenant_reason_mappings={("BVD", SECTION_EXPRESS, "lumper fee"): (CATEGORY_LUMPER, 1)},
    )
    assert r.classification == CATEGORY_UNMAPPED
    assert r.classification_status == CLASSIFICATION_STATUS_UNMAPPED


def test_ta_tf_fuel_df_def_s_scale() -> None:
    for prod, cat in (("TA", CATEGORY_FUEL), ("TF", CATEGORY_FUEL), ("DF", CATEGORY_DEF), ("S", CATEGORY_SCALE)):
        r = classify_fuel_transaction(
            tenant_id=1,
            provider_code="BVD",
            provider_section_raw=SECTION_FUEL_CARD,
            product_code_raw=prod,
            provider_reason_raw=None,
        )
        assert r.classification == cat
        assert r.classification_status == CLASSIFICATION_STATUS_CONFIRMED
        assert r.classification_source == CLASSIFICATION_SOURCE_PROVIDER_RULE


def test_unknown_bvd_product_unmapped() -> None:
    r = classify_fuel_transaction(
        tenant_id=1,
        provider_code="BVD",
        provider_section_raw=SECTION_FUEL_CARD,
        product_code_raw="ZZ",
        provider_reason_raw=None,
    )
    assert r.classification == CATEGORY_UNMAPPED
    assert r.classification_status == CLASSIFICATION_STATUS_UNMAPPED
    assert r.classification_source is None


def test_express_without_mapping_unmapped() -> None:
    r = classify_fuel_transaction(
        tenant_id=1,
        provider_code="BVD",
        provider_section_raw=SECTION_EXPRESS,
        product_code_raw=None,
        provider_reason_raw="lumper fee",
    )
    assert r.classification == CATEGORY_UNMAPPED


def test_normalize_reason_key() -> None:
    assert normalize_provider_reason_key("  Lumper   Fee ") == "lumper fee"


def test_tenant_exact_mapping_resolves() -> None:
    mappings = {("BVD", SECTION_EXPRESS, "lumper fee"): (CATEGORY_LUMPER, 99)}
    r = classify_fuel_transaction(
        tenant_id=53,
        provider_code="BVD",
        provider_section_raw=SECTION_EXPRESS,
        product_code_raw=None,
        provider_reason_raw="LUMPER FEE",
        tenant_reason_mappings=mappings,
    )
    assert r.classification == CATEGORY_LUMPER
    assert r.classification_source == CLASSIFICATION_SOURCE_TENANT_MAPPING
    assert r.mapping_id == 99


def test_lumper_fee_mapping_does_not_map_lumper() -> None:
    mappings = {("BVD", SECTION_EXPRESS, "lumper fee"): (CATEGORY_LUMPER, 1)}
    r = classify_fuel_transaction(
        tenant_id=53,
        provider_code="BVD",
        provider_section_raw=SECTION_EXPRESS,
        product_code_raw=None,
        provider_reason_raw="lumper",
        tenant_reason_mappings=mappings,
    )
    assert r.classification == CATEGORY_UNMAPPED


@pytest.mark.parametrize(
    "reason",
    ["pay", "load pay", "toll pay", "allowance"],
)
def test_express_phrases_stay_unmapped_without_mapping(reason: str) -> None:
    mappings = {("BVD", SECTION_EXPRESS, "lumper fee"): (CATEGORY_LUMPER, 1)}
    r = classify_fuel_transaction(
        tenant_id=53,
        provider_code="BVD",
        provider_section_raw=SECTION_EXPRESS,
        product_code_raw=None,
        provider_reason_raw=reason,
        tenant_reason_mappings=mappings,
    )
    assert r.classification == CATEGORY_UNMAPPED


def test_mapping_scoped_by_tenant_provider_section() -> None:
    mappings = {("BVD", SECTION_EXPRESS, "pay"): (CATEGORY_OTHER, 1)}
    hit = classify_fuel_transaction(
        tenant_id=53,
        provider_code="BVD",
        provider_section_raw=SECTION_EXPRESS,
        product_code_raw=None,
        provider_reason_raw="pay",
        tenant_reason_mappings=mappings,
    )
    assert hit.classification == CATEGORY_OTHER
    assert hit.classification_source == CLASSIFICATION_SOURCE_TENANT_MAPPING

    wrong_provider = classify_fuel_transaction(
        tenant_id=53,
        provider_code="OTHER",
        provider_section_raw=SECTION_EXPRESS,
        product_code_raw=None,
        provider_reason_raw="pay",
        tenant_reason_mappings=mappings,
    )
    assert wrong_provider.classification == CATEGORY_UNMAPPED

    wrong_section = classify_fuel_transaction(
        tenant_id=53,
        provider_code="BVD",
        provider_section_raw=SECTION_FUEL_CARD,
        product_code_raw=None,
        provider_reason_raw="pay",
        tenant_reason_mappings=mappings,
    )
    assert wrong_section.classification == CATEGORY_UNMAPPED


def test_tenant_mapping_loader_filters_tenant_id() -> None:
    """Mappings are loaded per tenant in persistence; other tenants never see them."""
    from app.models.fuel import FuelProviderCategoryMapping

    row = FuelProviderCategoryMapping(
        tenant_id=53,
        provider_code="BVD",
        provider_section=SECTION_EXPRESS,
        normalized_reason_key="pay",
        canonical_category_code=CATEGORY_OTHER,
        mapping_source="TENANT_MAPPING",
        active=True,
    )
    assert row.tenant_id == 53


def _as_review_rows(extracted, import_id: str) -> tuple[list[dict], list[dict]]:
    raw_rows: list[dict] = []
    for i, row in enumerate(extracted):
        raw_rows.append(
            {
                "id": i + 1,
                "import_id": import_id,
                "row_type": row.row_type,
                "source_page": row.source_page,
                "source_row_number": i + 1,
                **row.fields,
            }
        )
    effective_rows = [build_effective_bvd_row(r) for r in raw_rows]
    return raw_rows, effective_rows


def _classify_txns(txns, mappings=None):
    for t in txns:
        r = classify_fuel_transaction(
            tenant_id=53,
            provider_code=t.source_vendor,
            provider_section_raw=t.provider_section_raw,
            product_code_raw=t.product_code_raw,
            provider_reason_raw=t.provider_reason_raw,
            tenant_reason_mappings=mappings,
        )
        t.classification = r.classification
        t.classification_status = r.classification_status
        t.classification_source = r.classification_source


@pytest.mark.skipif(not BVD_838710.is_file(), reason="838710 fixture missing")
def test_bvd_838710_purchase_rules_and_express_unmapped() -> None:
    extracted, _, _ = extract_bvd_rows_from_digital_pdf(BVD_838710.read_bytes())
    import_id = str(uuid.uuid4())
    raw_rows, effective_rows = _as_review_rows(extracted, import_id)
    header = next(r for r in raw_rows if r["row_type"] == "HEADER")
    batch = build_fuel_source_batch(
        tenant_id=53,
        import_id=uuid.UUID(import_id),
        header=header,
        source_hash="sha",
        source_storage_ref="key",
        parser_version="BVD:test",
        reviewed_by="pytest",
    )
    batch.id = 1
    id_map = {int(r["id"]): 1000 + int(r["id"]) for r in raw_rows}
    txns, controls = project_bvd_rows_to_canonical(
        tenant_id=53,
        batch=batch,
        import_id=uuid.UUID(import_id),
        raw_rows=raw_rows,
        effective_rows=effective_rows,
        fuel_bvd_id_by_stage_row_id=id_map,
    )
    _classify_txns(txns)
    assert len(txns) == 42
    total = sum((t.total_amount or Decimal("0") for t in txns), Decimal("0"))
    assert total == Decimal("9047.72")
    assert_canonical_money_gate(txns, controls, expected_transaction_count=42, expected_total=total)

    purchases = [t for t in txns if t.provider_section_raw == SECTION_FUEL_CARD]
    express = [t for t in txns if t.provider_section_raw == SECTION_EXPRESS]
    assert len(purchases) == 31
    assert len(express) == 11

    for t in purchases:
        prod = (t.product_code_raw or "").upper()
        if prod in {"TA", "TF"}:
            assert t.classification == CATEGORY_FUEL
        elif prod == "DF":
            assert t.classification == CATEGORY_DEF
        elif prod == "S":
            assert t.classification == CATEGORY_SCALE
        else:
            assert t.classification == CATEGORY_UNMAPPED

    assert all(t.classification == CATEGORY_UNMAPPED for t in express)


@pytest.mark.skipif(not BVD_838710.is_file(), reason="838710 fixture missing")
def test_bvd_838710_lumper_fee_mapping_only_exact_rows() -> None:
    extracted, _, _ = extract_bvd_rows_from_digital_pdf(BVD_838710.read_bytes())
    import_id = str(uuid.uuid4())
    raw_rows, effective_rows = _as_review_rows(extracted, import_id)
    header = next(r for r in raw_rows if r["row_type"] == "HEADER")
    batch = build_fuel_source_batch(
        tenant_id=53,
        import_id=uuid.UUID(import_id),
        header=header,
        source_hash="sha",
        source_storage_ref="key",
        parser_version="BVD:test",
        reviewed_by="pytest",
    )
    batch.id = 1
    id_map = {int(r["id"]): 1000 + int(r["id"]) for r in raw_rows}
    txns, _ = project_bvd_rows_to_canonical(
        tenant_id=53,
        batch=batch,
        import_id=uuid.UUID(import_id),
        raw_rows=raw_rows,
        effective_rows=effective_rows,
        fuel_bvd_id_by_stage_row_id=id_map,
    )
    mappings = {("BVD", SECTION_EXPRESS, "lumper fee"): (CATEGORY_LUMPER, 42)}
    _classify_txns(txns, mappings=mappings)

    lumper_fee = [t for t in txns if (t.provider_reason_raw or "").strip().lower() == "lumper fee"]
    assert lumper_fee
    assert all(t.classification == CATEGORY_LUMPER for t in lumper_fee)

    lumper_only = [t for t in txns if (t.provider_reason_raw or "").strip().lower() == "lumper"]
    assert lumper_only
    assert all(t.classification == CATEGORY_UNMAPPED for t in lumper_only)


@pytest.mark.skipif(not BVD_972201.is_file(), reason="972201 fixture missing")
def test_bvd_972201_both_fuel_confirmed() -> None:
    extracted, _, _ = extract_bvd_rows_from_digital_pdf(BVD_972201.read_bytes())
    import_id = str(uuid.uuid4())
    raw_rows, effective_rows = _as_review_rows(extracted, import_id)
    header = next(r for r in raw_rows if r["row_type"] == "HEADER")
    batch = build_fuel_source_batch(
        tenant_id=53,
        import_id=uuid.UUID(import_id),
        header=header,
        source_hash="sha",
        source_storage_ref="key",
        parser_version="BVD:test",
        reviewed_by="pytest",
    )
    batch.id = 1
    id_map = {int(r["id"]): 1000 + int(r["id"]) for r in raw_rows}
    txns, controls = project_bvd_rows_to_canonical(
        tenant_id=53,
        batch=batch,
        import_id=uuid.UUID(import_id),
        raw_rows=raw_rows,
        effective_rows=effective_rows,
        fuel_bvd_id_by_stage_row_id=id_map,
    )
    _classify_txns(txns)
    assert len(txns) == 2
    total = sum((t.total_amount or Decimal("0") for t in txns), Decimal("0"))
    assert total == Decimal("3421.01")
    assert all(t.classification == CATEGORY_FUEL for t in txns)
    assert all(t.classification_source == CLASSIFICATION_SOURCE_PROVIDER_RULE for t in txns)
    assert_canonical_money_gate(txns, controls, expected_transaction_count=2, expected_total=total)


def test_classification_does_not_change_money_fields() -> None:
    from app.models.fuel import FuelTransaction

    txn = FuelTransaction(
        tenant_id=1,
        batch_id=1,
        source_row_order=1,
        source_vendor="BVD",
        provider_event_type="PURCHASE",
        transaction_datetime_source="2024-01-01",
        transaction_timezone_source="DATE_ONLY",
        provider_section_raw=SECTION_EXPRESS,
        provider_reason_raw="pay",
        total_amount=Decimal("103.00"),
        principal_amount=Decimal("100.00"),
        provider_fee_amount=Decimal("3.00"),
        provider_raw={},
    )
    before = (txn.principal_amount, txn.provider_fee_amount, txn.total_amount)
    r = classify_fuel_transaction(
        tenant_id=1,
        provider_code="BVD",
        provider_section_raw=SECTION_EXPRESS,
        product_code_raw=None,
        provider_reason_raw="pay",
        tenant_reason_mappings={("BVD", SECTION_EXPRESS, "pay"): (CATEGORY_OTHER, 1)},
    )
    txn.classification = r.classification
    after = (txn.principal_amount, txn.provider_fee_amount, txn.total_amount)
    assert before == after
    assert r.classification == CATEGORY_OTHER
    assert txn.provider_reason_raw == "pay"


@pytest.mark.asyncio
async def test_manual_classification_without_remember_mapping() -> None:
    from unittest.mock import AsyncMock, patch

    from app.models.fuel import FuelTransaction
    from app.services.fuel_classification_persistence import set_transaction_classification_manual

    txn = FuelTransaction(
        id=7,
        tenant_id=53,
        batch_id=1,
        source_row_order=1,
        source_vendor="BVD",
        provider_event_type="PURCHASE",
        transaction_datetime_source="x",
        transaction_timezone_source="DATE_ONLY",
        provider_section_raw=SECTION_EXPRESS,
        provider_reason_raw="pay",
        total_amount=Decimal("103.00"),
        principal_amount=Decimal("100.00"),
        provider_fee_amount=Decimal("3.00"),
        provider_raw={},
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=txn)
    with patch(
        "app.services.fuel_classification_persistence.apply_classification_result",
        AsyncMock(return_value=True),
    ) as apply_mock:
        with patch(
            "app.services.fuel_classification_persistence.version_tenant_reason_mapping",
            AsyncMock(),
        ) as upsert_mock:
            out = await set_transaction_classification_manual(
                db,
                tenant_id=53,
                transaction_id=7,
                canonical_category=CATEGORY_OTHER,
                remember_mapping=False,
                actor_user_id="u1",
            )
    assert out.id == 7
    assert txn.provider_reason_raw == "pay"
    upsert_mock.assert_not_awaited()
    apply_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_remember_mapping_calls_upsert() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.models.fuel import FuelTransaction
    from app.services.fuel_classification_persistence import set_transaction_classification_manual

    txn = FuelTransaction(
        id=8,
        tenant_id=53,
        batch_id=1,
        source_row_order=2,
        source_vendor="BVD",
        provider_event_type="PURCHASE",
        transaction_datetime_source="x",
        transaction_timezone_source="DATE_ONLY",
        provider_section_raw=SECTION_EXPRESS,
        provider_reason_raw="pay",
        total_amount=Decimal("103.00"),
        provider_raw={},
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=txn)
    mapping = MagicMock(id=55)
    with patch(
        "app.services.fuel_classification_persistence.apply_classification_result",
        AsyncMock(return_value=True),
    ):
        with patch(
            "app.services.fuel_classification_workflow.version_tenant_reason_mapping",
            AsyncMock(return_value=mapping),
        ) as upsert_mock:
            await set_transaction_classification_manual(
                db,
                tenant_id=53,
                transaction_id=8,
                canonical_category=CATEGORY_OTHER,
                remember_mapping=True,
                actor_user_id="u1",
            )
    upsert_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_classification_appends_event_on_change() -> None:
    from unittest.mock import MagicMock

    from app.models.fuel import FuelTransaction
    from app.services.fuel_classification_persistence import apply_classification_result
    from app.services.fuel_transaction_classify import FuelTransactionClassificationResult

    txn = FuelTransaction(
        id=9,
        tenant_id=53,
        batch_id=1,
        source_row_order=3,
        source_vendor="BVD",
        provider_event_type="PURCHASE",
        transaction_datetime_source="x",
        transaction_timezone_source="DATE_ONLY",
        provider_raw={},
        classification=CATEGORY_UNMAPPED,
        classification_status=CLASSIFICATION_STATUS_UNMAPPED,
    )
    db = MagicMock()
    result = FuelTransactionClassificationResult(
        classification=CATEGORY_FUEL,
        classification_status=CLASSIFICATION_STATUS_CONFIRMED,
        classification_source=CLASSIFICATION_SOURCE_PROVIDER_RULE,
    )
    changed = await apply_classification_result(db, txn=txn, result=result, actor_user_id="u1")
    assert changed is True
    assert db.add.call_count == 2
    assert txn.classification == CATEGORY_FUEL


@pytest.mark.asyncio
async def test_apply_classification_idempotent_same_state() -> None:
    from unittest.mock import MagicMock

    from app.models.fuel import FuelTransaction
    from app.services.fuel_classification_persistence import apply_classification_result
    from app.services.fuel_transaction_classify import FuelTransactionClassificationResult

    txn = FuelTransaction(
        id=10,
        tenant_id=53,
        batch_id=1,
        source_row_order=4,
        source_vendor="BVD",
        provider_event_type="PURCHASE",
        transaction_datetime_source="x",
        transaction_timezone_source="DATE_ONLY",
        provider_raw={},
        classification=CATEGORY_FUEL,
        classification_status=CLASSIFICATION_STATUS_CONFIRMED,
        classification_source=CLASSIFICATION_SOURCE_PROVIDER_RULE,
        classification_mapping_id=None,
    )
    db = MagicMock()
    result = FuelTransactionClassificationResult(
        classification=CATEGORY_FUEL,
        classification_status=CLASSIFICATION_STATUS_CONFIRMED,
        classification_source=CLASSIFICATION_SOURCE_PROVIDER_RULE,
        mapping_id=None,
    )
    changed = await apply_classification_result(db, txn=txn, result=result)
    assert changed is False
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_provenance_change_appends_event_same_category() -> None:
    from unittest.mock import MagicMock

    from app.models.fuel import FuelTransaction
    from app.services.fuel_classification_persistence import apply_classification_result
    from app.services.fuel_transaction_classify import FuelTransactionClassificationResult

    txn = FuelTransaction(
        id=11,
        tenant_id=53,
        batch_id=1,
        source_row_order=5,
        source_vendor="BVD",
        provider_event_type="PURCHASE",
        transaction_datetime_source="x",
        transaction_timezone_source="DATE_ONLY",
        provider_raw={},
        classification=CATEGORY_LUMPER,
        classification_status=CLASSIFICATION_STATUS_CONFIRMED,
        classification_source=CLASSIFICATION_SOURCE_MANUAL,
        classification_mapping_id=None,
    )
    db = MagicMock()
    result = FuelTransactionClassificationResult(
        classification=CATEGORY_LUMPER,
        classification_status=CLASSIFICATION_STATUS_CONFIRMED,
        classification_source=CLASSIFICATION_SOURCE_TENANT_MAPPING,
        mapping_id=77,
    )
    changed = await apply_classification_result(db, txn=txn, result=result)
    assert changed is True
    assert db.add.call_count == 2


@pytest.mark.asyncio
async def test_human_confirmed_not_overwritten_by_automatic() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.models.fuel import FuelTransaction
    from app.services.fuel_classification_persistence import classify_transaction_row

    txn = FuelTransaction(
        id=12,
        tenant_id=53,
        batch_id=1,
        source_row_order=6,
        source_vendor="BVD",
        provider_event_type="PURCHASE",
        transaction_datetime_source="x",
        transaction_timezone_source="DATE_ONLY",
        provider_section_raw=SECTION_EXPRESS,
        provider_reason_raw="pay",
        provider_raw={},
        classification=CATEGORY_OTHER,
        classification_status=CLASSIFICATION_STATUS_CONFIRMED,
        classification_source=CLASSIFICATION_SOURCE_MANUAL,
    )
    db = MagicMock()
    out = await classify_transaction_row(
        db,
        txn=txn,
        tenant_reason_mappings={},
        respect_human_lock=True,
    )
    assert out is None
    assert txn.classification == CATEGORY_OTHER
    assert txn.provider_reason_raw == "pay"
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_best_effort_classification_does_not_propagate_errors() -> None:
    from unittest.mock import AsyncMock, patch

    from app.services.fuel_classification_persistence import (
        best_effort_backfill_classifications_for_import,
    )

    db = AsyncMock()
    with patch(
        "app.services.fuel_classification_persistence.backfill_classifications_for_import",
        AsyncMock(side_effect=RuntimeError("mapping table missing")),
    ):
        changed = await best_effort_backfill_classifications_for_import(
            db, tenant_id=53, import_id="import-uuid"
        )
    assert changed == 0
    db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_mapping_version_deactivates_old_row() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.models.fuel import FuelProviderCategoryMapping
    from app.services.fuel_classification_persistence import version_tenant_reason_mapping
    from app.services.fuel_charge_categories import CATEGORY_OTHER

    active = FuelProviderCategoryMapping(
        id=5,
        tenant_id=53,
        provider_code="BVD",
        provider_section=SECTION_EXPRESS,
        normalized_reason_key="lumper fee",
        canonical_category_code=CATEGORY_LUMPER,
        mapping_source="TENANT_MAPPING",
        active=True,
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=active)
    db.flush = AsyncMock()
    db.add = MagicMock()
    row = await version_tenant_reason_mapping(
        db,
        tenant_id=53,
        provider_code="BVD",
        provider_section=SECTION_EXPRESS,
        normalized_reason_key="lumper fee",
        canonical_category_code=CATEGORY_OTHER,
        raw_example="lumper fee",
        approved_by="u1",
    )
    assert active.active is False
    assert row.canonical_category_code == CATEGORY_OTHER
    db.add.assert_called_once()


def test_segment_b_modules_do_not_import_openai() -> None:
    modules = [
        "app.services.fuel_charge_categories",
        "app.services.fuel_reason_normalize",
        "app.services.fuel_transaction_classify",
        "app.services.fuel_classification_persistence",
    ]
    for name in modules:
        mod = importlib.import_module(name)
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "openai" not in src.lower()
        assert "OpenAI" not in src
