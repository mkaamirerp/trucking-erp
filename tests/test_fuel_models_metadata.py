"""Fuel model metadata / import structural regression (Segment 0A–4)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint

from app.models.base import Base
from app.models.fuel import (
    FuelCardAccountAssignment,
    FuelExtractionCorrection,
    FuelOwnerOperatorPricingRule,
    FuelProviderConnection,
    FuelSourceBatch,
    FuelSourceControl,
    FuelTransaction,
)

_EXPECTED: dict[type, dict[str, object]] = {
    FuelProviderConnection: {
        "tablename": "fuel_provider_connections",
        "required_cols": {
            "tenant_id",
            "provider_code",
            "connection_method",
            "config_json",
            "credential_ref",
        },
        "uq_names": {"uq_fuel_provider_connections_tenant_id_id"},
    },
    FuelSourceBatch: {
        "tablename": "fuel_source_batches",
        "required_cols": {
            "tenant_id",
            "provider_code",
            "source_type",
            "parser_rule_version",
            "source_hash",
            "review_version",
            "layout_status",
            "provider_profile_code",
        },
        "uq_names": {"uq_fuel_source_batches_tenant_id_id"},
    },
    FuelTransaction: {
        "tablename": "fuel_transactions",
        "required_cols": {
            "tenant_id",
            "batch_id",
            "provider_event_type",
            "transaction_datetime_source",
            "transaction_timezone_source",
            "currency_raw",
            "currency",
            "owner_operator_charge_amount",
            "oo_pricing_mode",
            "oo_pricing_rule_id",
            "oo_pricing_status",
            "oo_pricing_inputs_json",
            "provider_raw",
            "review_status",
            "parsed_row_role",
        },
        "uq_names": {
            "uq_fuel_transactions_tenant_id_id",
            "uq_fuel_transactions_tenant_batch_source_row_order",
        },
    },
    FuelSourceControl: {
        "tablename": "fuel_source_controls",
        "required_cols": {
            "tenant_id",
            "batch_id",
            "control_type",
            "control_scope",
            "provider_raw",
            "requires_review",
            "source_row_order",
            "review_status",
            "parsed_row_role",
        },
        "uq_names": {"uq_fuel_source_controls_tenant_id_id"},
    },
    FuelExtractionCorrection: {
        "tablename": "fuel_extraction_corrections",
        "required_cols": {
            "tenant_id",
            "batch_id",
            "entity_type",
            "entity_id",
            "field_name",
            "parsed_value",
            "reviewed_value",
            "reason",
            "reviewed_by",
            "reviewed_at",
        },
        "uq_names": {"uq_fuel_extraction_corrections_tenant_id_id"},
    },
    FuelOwnerOperatorPricingRule: {
        "tablename": "fuel_oo_pricing_rules",
        "required_cols": {
            "tenant_id",
            "owner_operator_payee_id",
            "pricing_mode",
            "fixed_discount_per_unit",
            "percent_of_provider_discount",
            "effective_from",
            "effective_to",
            "rule_version",
        },
        "uq_names": {"uq_fuel_oo_pricing_rules_tenant_id_id"},
    },
    FuelCardAccountAssignment: {
        "tablename": "fuel_card_account_assignments",
        "required_cols": {
            "tenant_id",
            "provider_code",
            "card_or_account_id",
            "effective_from",
            "effective_to",
        },
        "uq_names": {"uq_fuel_card_account_assignments_tenant_id_id"},
    },
}


def test_fuel_models_import_and_tablename_ownership() -> None:
    metadata_tables = set(Base.metadata.tables.keys())
    for model, expect in _EXPECTED.items():
        assert model.__tablename__ == expect["tablename"]
        assert expect["tablename"] in metadata_tables
        cols = set(model.__table__.c.keys())
        missing = set(expect["required_cols"]) - cols
        assert not missing, f"{model.__name__} missing columns: {missing}"
        # Columns must belong to this table object, not a sibling class.
        assert model.__table__.name == expect["tablename"]


def test_fuel_model_constraints_and_indexes_not_orphaned() -> None:
    for model, expect in _EXPECTED.items():
        uq_names = {
            c.name
            for c in model.__table__.constraints
            if isinstance(c, UniqueConstraint) and c.name
        }
        assert set(expect["uq_names"]).issubset(uq_names), model.__name__
        # Sanity: CheckConstraints / FKs / Indexes resolve on the same table.
        for c in model.__table__.constraints:
            if isinstance(c, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint)):
                assert c.table is model.__table__
        for ix in model.__table__.indexes:
            assert isinstance(ix, Index)
            assert ix.table is model.__table__


def test_fuel_source_control_not_merged_into_pricing_rule() -> None:
    """Regression for temporary corruption while inserting Segment 4 model."""
    assert FuelSourceControl.__name__ == "FuelSourceControl"
    assert FuelOwnerOperatorPricingRule.__name__ == "FuelOwnerOperatorPricingRule"
    assert FuelSourceControl.__tablename__ == "fuel_source_controls"
    assert FuelOwnerOperatorPricingRule.__tablename__ == "fuel_oo_pricing_rules"
    assert "control_type" in FuelSourceControl.__table__.c
    assert "control_type" not in FuelOwnerOperatorPricingRule.__table__.c
    assert "pricing_mode" in FuelOwnerOperatorPricingRule.__table__.c
    assert "pricing_mode" not in FuelSourceControl.__table__.c
    # Segment 2 control columns must still live on FuelSourceControl.
    for col in ("declared_amount", "gst_amount", "requires_review", "review_reason"):
        assert col in FuelSourceControl.__table__.c
    # Segment 4 OO provenance must live on FuelTransaction, not controls.
    for col in ("oo_pricing_status", "oo_benefit_per_unit", "owner_operator_charge_amount"):
        assert col in FuelTransaction.__table__.c
        assert col not in FuelSourceControl.__table__.c
