"""B8 payroll + settlements schema

Revision ID: b8f9cfe34f1b
Revises: f2d5b4be0ac2
Create Date: 2026-01-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime

# revision identifiers, used by Alembic.
revision: str = "b8f9cfe34f1b"
down_revision: Union[str, Sequence[str], None] = "f2d5b4be0ac2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_enums(bind) -> None:
    worker_type = postgresql.ENUM(
        "EMPLOYEE_DRIVER",
        "CONTRACTOR_COMPANY_DRIVER",
        "OWNER_OPERATOR_LEASED_ON",
        "THIRD_PARTY_CARRIER",
        name="worker_type",
    )
    payee_type = postgresql.ENUM("DRIVER", "CARRIER", name="payee_type")
    pay_document_type = postgresql.ENUM(
        "PAYSTUB",
        "SETTLEMENT_STATEMENT",
        "CONTRACTOR_PAY_STATEMENT",
        "CARRIER_PAYOUT_STATEMENT",
        name="pay_document_type",
    )
    pay_run_status = postgresql.ENUM("DRAFT", "GENERATED", "FINALIZED", "VOIDED", name="pay_run_status")
    payout_status = postgresql.ENUM("UNPAID", "PARTIAL", "PAID", name="payout_status")
    source_type = postgresql.ENUM("EARNING", "DEDUCTION", "FEE", "ESCROW", "ADJUSTMENT", "TAX", name="source_type")
    responsibility = postgresql.ENUM("COMPANY", "WORKER", name="responsibility")
    calc_method = postgresql.ENUM(
        "ACTUAL", "FLAT", "PERCENT_OF_GROSS", "PERCENT_OF_NET_AFTER_DISPATCH", name="calc_method"
    )
    frequency = postgresql.ENUM(
        "ONE_TIME", "WEEKLY", "BIWEEKLY", "MONTHLY", "QUARTERLY", "YEARLY", name="frequency"
    )
    gross_calc_type = postgresql.ENUM(
        "CPM", "PERCENT_REVENUE", "FLAT_PER_LOAD", "HOURLY", "SALARY", "HYBRID", name="gross_calc_type"
    )
    settlement_frequency = postgresql.ENUM("WEEKLY", "BIWEEKLY", "SEMI_MONTHLY", "MONTHLY", name="settlement_frequency")
    mile_source = postgresql.ENUM(
        "ADDRESS_TO_ADDRESS", "ZIP_TO_ZIP", "CITY_TO_CITY", "MANUAL", name="mile_source"
    )
    pay_mile_mode = postgresql.ENUM(
        "ALL_MILES", "LOADED_ONLY", "LOADED_AND_EMPTY_DIFFERENT_RATES", name="pay_mile_mode"
    )
    escrow_rule_type = postgresql.ENUM("HOLD_WEEKS", "HOLD_FIXED_PER_PERIOD", "HOLD_UNTIL_TARGET", name="escrow_rule_type")
    escrow_entry_type = postgresql.ENUM("HOLD", "RELEASE", "ADJUSTMENT", name="escrow_entry_type")
    override_type = postgresql.ENUM("CHANGE_AMOUNT", "ADD_ITEM", "REMOVE_ITEM", name="override_type")
    payout_payment_status = postgresql.ENUM("PENDING", "SENT", "CONFIRMED", "FAILED", "VOIDED", name="payout_payment_status")

    for enum_type in [
        worker_type,
        payee_type,
        pay_document_type,
        pay_run_status,
        payout_status,
        source_type,
        responsibility,
        calc_method,
        frequency,
        gross_calc_type,
        settlement_frequency,
        mile_source,
        pay_mile_mode,
        escrow_rule_type,
        escrow_entry_type,
        override_type,
        payout_payment_status,
    ]:
        enum_type.create(bind, checkfirst=True)


def _drop_enums(bind) -> None:
    for name in [
        "payout_payment_status",
        "override_type",
        "escrow_entry_type",
        "escrow_rule_type",
        "pay_mile_mode",
        "mile_source",
        "settlement_frequency",
        "gross_calc_type",
        "frequency",
        "calc_method",
        "responsibility",
        "source_type",
        "payout_status",
        "pay_run_status",
        "pay_document_type",
        "payee_type",
        "worker_type",
    ]:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)


def upgrade() -> None:
    """Upgrade schema to B8 payroll + settlements."""
    bind = op.get_bind()
    _create_enums(bind)

    inspector = sa.inspect(bind)

    # Preserve legacy employees table if present to avoid data loss; rename it before creating the new schema table.
    if inspector.has_table("employees"):
        legacy_name = f"employees_legacy_{datetime.utcnow().strftime('%Y%m%d')}"
        op.rename_table("employees", legacy_name)

    worker_type_enum = postgresql.ENUM(
        "EMPLOYEE_DRIVER",
        "CONTRACTOR_COMPANY_DRIVER",
        "OWNER_OPERATOR_LEASED_ON",
        "THIRD_PARTY_CARRIER",
        name="worker_type",
        create_type=False,
    )
    payee_type_enum = postgresql.ENUM("DRIVER", "CARRIER", name="payee_type", create_type=False)
    pay_document_type_enum = postgresql.ENUM(
        "PAYSTUB",
        "SETTLEMENT_STATEMENT",
        "CONTRACTOR_PAY_STATEMENT",
        "CARRIER_PAYOUT_STATEMENT",
        name="pay_document_type",
        create_type=False,
    )
    pay_run_status_enum = postgresql.ENUM("DRAFT", "GENERATED", "FINALIZED", "VOIDED", name="pay_run_status", create_type=False)
    payout_status_enum = postgresql.ENUM("UNPAID", "PARTIAL", "PAID", name="payout_status", create_type=False)
    source_type_enum = postgresql.ENUM("EARNING", "DEDUCTION", "FEE", "ESCROW", "ADJUSTMENT", "TAX", name="source_type", create_type=False)
    responsibility_enum = postgresql.ENUM("COMPANY", "WORKER", name="responsibility", create_type=False)
    calc_method_enum = postgresql.ENUM(
        "ACTUAL", "FLAT", "PERCENT_OF_GROSS", "PERCENT_OF_NET_AFTER_DISPATCH", name="calc_method", create_type=False
    )
    frequency_enum = postgresql.ENUM(
        "ONE_TIME", "WEEKLY", "BIWEEKLY", "MONTHLY", "QUARTERLY", "YEARLY", name="frequency", create_type=False
    )
    gross_calc_type_enum = postgresql.ENUM(
        "CPM", "PERCENT_REVENUE", "FLAT_PER_LOAD", "HOURLY", "SALARY", "HYBRID", name="gross_calc_type", create_type=False
    )
    settlement_frequency_enum = postgresql.ENUM(
        "WEEKLY", "BIWEEKLY", "SEMI_MONTHLY", "MONTHLY", name="settlement_frequency", create_type=False
    )
    mile_source_enum = postgresql.ENUM(
        "ADDRESS_TO_ADDRESS", "ZIP_TO_ZIP", "CITY_TO_CITY", "MANUAL", name="mile_source", create_type=False
    )
    pay_mile_mode_enum = postgresql.ENUM(
        "ALL_MILES",
        "LOADED_ONLY",
        "LOADED_AND_EMPTY_DIFFERENT_RATES",
        name="pay_mile_mode",
        create_type=False,
    )
    escrow_rule_type_enum = postgresql.ENUM(
        "HOLD_WEEKS", "HOLD_FIXED_PER_PERIOD", "HOLD_UNTIL_TARGET", name="escrow_rule_type", create_type=False
    )
    escrow_entry_type_enum = postgresql.ENUM("HOLD", "RELEASE", "ADJUSTMENT", name="escrow_entry_type", create_type=False)
    override_type_enum = postgresql.ENUM("CHANGE_AMOUNT", "ADD_ITEM", "REMOVE_ITEM", name="override_type", create_type=False)
    payout_payment_status_enum = postgresql.ENUM(
        "PENDING", "SENT", "CONFIRMED", "FAILED", "VOIDED", name="payout_payment_status", create_type=False
    )

    # platform_tenants extensions
    op.add_column(
        "platform_tenants",
        sa.Column("base_currency", sa.CHAR(length=3), nullable=False, server_default=sa.text("'USD'")),
    )
    op.add_column(
        "platform_tenants",
        sa.Column("timezone", sa.Text(), nullable=False, server_default=sa.text("'America/Toronto'")),
    )
    op.add_column("platform_tenants", sa.Column("country_code", sa.CHAR(length=2), nullable=True))
    op.add_column("platform_tenants", sa.Column("billing_status", sa.Text(), nullable=True))
    op.add_column("platform_tenants", sa.Column("billing_provider", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_platform_tenants_base_currency_len", "platform_tenants", "char_length(base_currency) = 3"
    )

    # payees (drivers + carriers)
    op.create_table(
        "payees",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payee_type", payee_type_enum, nullable=False),
        sa.Column("worker_type", worker_type_enum, nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("carrier_mc_number", sa.Text(), nullable=True),
        sa.Column("carrier_dot_number", sa.Text(), nullable=True),
        sa.Column("incorporation_name", sa.Text(), nullable=True),
        sa.Column("tax_id_last4", sa.CHAR(length=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_payees_tenant", "payees", ["tenant_id"])
    op.create_index("idx_payees_worker_type", "payees", ["tenant_id", "worker_type"])
    op.create_index("idx_payees_mc", "payees", ["tenant_id", "carrier_mc_number"])
    op.create_check_constraint(
        "chk_payees_tax_id_last4_len",
        "payees",
        "(tax_id_last4 IS NULL) OR (char_length(tax_id_last4) = 4)",
    )

    # drivers link to payees
    op.add_column("drivers", sa.Column("payee_id", sa.Integer(), nullable=True, unique=True))
    op.create_foreign_key("fk_drivers_payee", "drivers", "payees", ["payee_id"], ["id"], ondelete="RESTRICT")

    # employees table
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payee_id", sa.Integer(), sa.ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("employee_number", sa.Text(), nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("employment_type", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "employee_number", name="uq_employee_number"),
    )

    # compensation profiles
    op.create_table(
        "compensation_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payee_id", sa.Integer(), sa.ForeignKey("payees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("worker_type_snapshot", worker_type_enum, nullable=False),
        sa.Column("gross_calc_type", gross_calc_type_enum, nullable=False),
        sa.Column("percent_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("cpm_loaded", sa.Numeric(8, 4), nullable=True),
        sa.Column("cpm_empty", sa.Numeric(8, 4), nullable=True),
        sa.Column("hourly_rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("salary_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("flat_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("dispatch_fee_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dispatch_fee_rate", sa.Numeric(6, 4), nullable=False, server_default=sa.text("0.0000")),
        sa.Column("dispatch_fee_basis", sa.Text(), nullable=False, server_default=sa.text("'GROSS'")),
        sa.Column(
            "settlement_frequency",
            settlement_frequency_enum,
            nullable=False,
            server_default=sa.text("'BIWEEKLY'"),
        ),
        sa.Column("allow_negative_settlement", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_comp_profiles_payee", "compensation_profiles", ["tenant_id", "payee_id", "effective_from"]
    )
    op.create_check_constraint(
        "chk_compensation_profiles_percent_rate_range",
        "compensation_profiles",
        "(percent_rate IS NULL) OR (percent_rate >= 0 AND percent_rate <= 1)",
    )
    op.create_check_constraint(
        "chk_compensation_profiles_dispatch_fee_rate_range",
        "compensation_profiles",
        "dispatch_fee_rate >= 0 AND dispatch_fee_rate <= 1",
    )
    op.create_check_constraint(
        "chk_compensation_profiles_effective_dates",
        "compensation_profiles",
        "(effective_to IS NULL) OR (effective_to >= effective_from)",
    )

    # tenant mileage policies
    op.create_table(
        "tenant_mileage_policies",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("default_mile_source", mile_source_enum, nullable=False, server_default=sa.text("'ADDRESS_TO_ADDRESS'")),
        sa.Column("pay_mile_mode", pay_mile_mode_enum, nullable=False, server_default=sa.text("'ALL_MILES'")),
        sa.Column("empty_mile_multiplier", sa.Numeric(6, 4), nullable=True),
        sa.Column("allow_manual_override", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("override_requires_reason", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # loads/shipments mileage fields (only if table exists)
    inspector = sa.inspect(bind)
    if "loads" in inspector.get_table_names():
        with op.batch_alter_table("loads") as batch:
            batch.add_column(sa.Column("loaded_miles", sa.Numeric(10, 2), nullable=True))
            batch.add_column(sa.Column("empty_miles", sa.Numeric(10, 2), nullable=True))
            batch.add_column(sa.Column("total_miles", sa.Numeric(10, 2), nullable=True))
            batch.add_column(
                sa.Column(
                    "mile_source",
                    mile_source_enum,
                    nullable=False,
                    server_default=sa.text("'ADDRESS_TO_ADDRESS'"),
                )
            )
            batch.add_column(sa.Column("miles_last_calculated_at", sa.DateTime(timezone=True), nullable=True))
            batch.add_column(sa.Column("miles_override_reason", sa.Text(), nullable=True))
            batch.add_column(sa.Column("miles_overridden_by_user_id", sa.Integer(), nullable=True))

    # charge categories
    op.create_table(
        "charge_categories",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("default_responsibility", responsibility_enum, nullable=False, server_default=sa.text("'WORKER'")),
        sa.Column("requires_document", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_charge_code"),
    )

    # comp profile charge rules
    op.create_table(
        "comp_profile_charge_rules",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "compensation_profile_id",
            sa.Integer(),
            sa.ForeignKey("compensation_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "charge_category_id",
            sa.Integer(),
            sa.ForeignKey("charge_categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("responsibility", responsibility_enum, nullable=False),
        sa.Column("calc_method", calc_method_enum, nullable=False),
        sa.Column("rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("flat_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("frequency", frequency_enum, nullable=False, server_default=sa.text("'ONE_TIME'")),
        sa.Column("cap_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("default_apply", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_comp_profile_charge_rules_profile",
        "comp_profile_charge_rules",
        ["tenant_id", "compensation_profile_id"],
    )

    # escrow accounts and rules
    op.create_table(
        "escrow_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payee_id", sa.Integer(), sa.ForeignKey("payees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("target_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("current_balance", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "escrow_rules",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "escrow_account_id",
            sa.Integer(),
            sa.ForeignKey("escrow_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_type", escrow_rule_type_enum, nullable=False),
        sa.Column("weeks_to_hold", sa.Integer(), nullable=True),
        sa.Column("amount_per_period", sa.Numeric(12, 2), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # pay periods constraints
    op.execute("UPDATE pay_periods SET status='OPEN' WHERE status NOT IN ('OPEN','CLOSED')")
    op.alter_column(
        "pay_periods",
        "status",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default=sa.text("'OPEN'"),
    )
    op.create_check_constraint(
        "chk_pay_periods_status_valid", "pay_periods", "status in ('OPEN','CLOSED')"
    )
    op.create_check_constraint("chk_pay_periods_dates", "pay_periods", "start_date <= end_date")

    # rebuild pay_runs/pay_run_items for B8 shape
    op.drop_table("pay_run_items")
    op.drop_table("pay_runs")

    op.create_table(
        "pay_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pay_period_id", sa.Integer(), sa.ForeignKey("pay_periods.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("pay_document_type", pay_document_type_enum, nullable=False),
        sa.Column("worker_type_snapshot", worker_type_enum, nullable=False),
        sa.Column("base_currency_snapshot", sa.CHAR(length=3), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("status", pay_run_status_enum, nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("payout_status", payout_status_enum, nullable=False, server_default=sa.text("'UNPAID'")),
        sa.Column("calculation_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_pay_runs_period", "pay_runs", ["tenant_id", "pay_period_id"])
    op.create_index("idx_pay_runs_status", "pay_runs", ["tenant_id", "status"])

    op.create_table(
        "pay_run_items",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pay_run_id", sa.Integer(), sa.ForeignKey("pay_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payee_id", sa.Integer(), sa.ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_type", source_type_enum, nullable=False),
        sa.Column("charge_category_id", sa.Integer(), sa.ForeignKey("charge_categories.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=True),
        sa.Column("unit_rate", sa.Numeric(12, 4), nullable=True),
        sa.Column("amount_signed", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_pay_items_run", "pay_run_items", ["tenant_id", "pay_run_id"])
    op.create_index("idx_pay_items_payee", "pay_run_items", ["tenant_id", "payee_id"])

    op.create_table(
        "escrow_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "escrow_account_id",
            sa.Integer(),
            sa.ForeignKey("escrow_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pay_run_id", sa.Integer(), sa.ForeignKey("pay_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entry_type", escrow_entry_type_enum, nullable=False),
        sa.Column("amount_signed", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # payee balances
    op.create_table(
        "payee_balances",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payee_id", sa.Integer(), sa.ForeignKey("payees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("as_of_pay_run_id", sa.Integer(), sa.ForeignKey("pay_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("balance_signed", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_balances_payee", "payee_balances", ["tenant_id", "payee_id", "as_of_pay_run_id"]
    )

    # pay_run_overrides
    op.create_table(
        "pay_run_overrides",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pay_run_id", sa.Integer(), sa.ForeignKey("pay_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("override_type", override_type_enum, nullable=False),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # pay_documents
    op.create_table(
        "pay_documents",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pay_run_id", sa.Integer(), sa.ForeignKey("pay_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payee_id", sa.Integer(), sa.ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_type", pay_document_type_enum, nullable=False),
        sa.Column("file_storage_key", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("generated_by", sa.Integer(), nullable=True),
    )
    op.create_index("idx_docs_run", "pay_documents", ["tenant_id", "pay_run_id"])

    # payout rails + preferences
    op.create_table(
        "payout_rails",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("supports_connector", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "tenant_payout_rail_settings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payout_rail_id", sa.Integer(), sa.ForeignKey("payout_rails.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "payout_rail_id", name="uq_tenant_rail"),
    )

    op.create_table(
        "payee_payout_preferences",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payee_id", sa.Integer(), sa.ForeignKey("payees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payout_rail_id", sa.Integer(), sa.ForeignKey("payout_rails.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "pay_run_payments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pay_run_id", sa.Integer(), sa.ForeignKey("pay_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payee_id", sa.Integer(), sa.ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_paid", sa.Numeric(12, 2), nullable=False),
        sa.Column("payout_rail_id", sa.Integer(), sa.ForeignKey("payout_rails.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", payout_payment_status_enum, nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "tenant_bank_connectors",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'DISCONNECTED'")),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("secrets_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenant_provider"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    op.drop_table("tenant_bank_connectors")
    op.drop_table("pay_run_payments")
    op.drop_table("payee_payout_preferences")
    op.drop_table("tenant_payout_rail_settings")
    op.drop_table("payout_rails")
    op.drop_index("idx_docs_run", table_name="pay_documents")
    op.drop_table("pay_documents")
    op.drop_table("pay_run_overrides")
    op.drop_index("idx_balances_payee", table_name="payee_balances")
    op.drop_table("payee_balances")
    op.drop_index("idx_pay_items_payee", table_name="pay_run_items")
    op.drop_index("idx_pay_items_run", table_name="pay_run_items")
    op.drop_table("pay_run_items")
    op.drop_table("escrow_ledger_entries")
    op.drop_index("idx_pay_runs_status", table_name="pay_runs")
    op.drop_index("idx_pay_runs_period", table_name="pay_runs")
    op.drop_table("pay_runs")
    op.drop_table("escrow_rules")
    op.drop_table("escrow_accounts")
    op.drop_index("idx_comp_profile_charge_rules_profile", table_name="comp_profile_charge_rules")
    op.drop_table("comp_profile_charge_rules")
    op.drop_table("charge_categories")
    op.drop_table("tenant_mileage_policies")
    op.drop_index("idx_comp_profiles_payee", table_name="compensation_profiles")
    op.drop_constraint("chk_compensation_profiles_effective_dates", "compensation_profiles", type_="check")
    op.drop_constraint("chk_compensation_profiles_dispatch_fee_rate_range", "compensation_profiles", type_="check")
    op.drop_constraint("chk_compensation_profiles_percent_rate_range", "compensation_profiles", type_="check")
    op.drop_table("compensation_profiles")
    op.drop_table("employees")
    op.drop_constraint("fk_drivers_payee", "drivers", type_="foreignkey")
    op.drop_column("drivers", "payee_id")
    op.drop_constraint("chk_payees_tax_id_last4_len", "payees", type_="check")
    op.drop_index("idx_payees_mc", table_name="payees")
    op.drop_index("idx_payees_worker_type", table_name="payees")
    op.drop_index("idx_payees_tenant", table_name="payees")
    op.drop_table("payees")
    op.drop_constraint("chk_platform_tenants_base_currency_len", "platform_tenants", type_="check")
    op.drop_column("platform_tenants", "billing_provider")
    op.drop_column("platform_tenants", "billing_status")
    op.drop_column("platform_tenants", "country_code")
    op.drop_column("platform_tenants", "timezone")
    op.drop_column("platform_tenants", "base_currency")

    # pay_periods constraints cleanup
    op.drop_constraint("chk_pay_periods_dates", "pay_periods", type_="check")
    op.drop_constraint("chk_pay_periods_status_valid", "pay_periods", type_="check")
    op.alter_column(
        "pay_periods",
        "status",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default=sa.text("'DRAFT'"),
    )

    _drop_enums(bind)
