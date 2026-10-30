"""Shared DDL for the two alternative tenant payee/compensation revisions (pc01 fmp / x5).

`payees` and `compensation_profiles` are mapped in app/models/payee.py but no tenant
revision ever created them (c9f8e7d6b5a4 and b3cfb1d0d9f0 only alter them when present).
This creates both tables when absent, with:

* tenant-scoped identity: payees (tenant_id, id) unique; profiles reference it compositely
* effective dating: effective_to is the inclusive last day; one open version per payee;
  one version per (payee, effective_from); effective_to >= effective_from
* rate bounds: percent_rate in (0, 1]; cpm_loaded > 0; cpm_empty >= 0; dispatch_fee_rate in [0, 1]

Forward-only data: no backfill from legacy pay_profiles, no row copies, no deletes.
Apply precisely one sibling revision after confirming tenant Alembic lineage.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

_ENUMS = {
    "worker_type": (
        "EMPLOYEE_DRIVER",
        "CONTRACTOR_COMPANY_DRIVER",
        "OWNER_OPERATOR_LEASED_ON",
        "THIRD_PARTY_CARRIER",
    ),
    "payee_type": ("DRIVER", "CARRIER"),
    "gross_calc_type": ("CPM", "PERCENT_REVENUE", "FLAT_PER_LOAD", "HOURLY", "SALARY", "HYBRID"),
    "settlement_frequency": ("WEEKLY", "BIWEEKLY", "SEMI_MONTHLY", "MONTHLY"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*_ENUMS[name], name=name, create_type=False)


def upgrade_payee_compensation() -> None:
    bind = op.get_bind()
    for name, values in _ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)
    insp = sa.inspect(bind)

    if not insp.has_table("payees"):
        op.create_table(
            "payees",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("payee_type", _enum("payee_type"), nullable=False),
            sa.Column("worker_type", _enum("worker_type"), nullable=False),
            sa.Column("display_name", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("carrier_mc_number", sa.Text(), nullable=True),
            sa.Column("carrier_dot_number", sa.Text(), nullable=True),
            sa.Column("incorporation_name", sa.Text(), nullable=True),
            sa.Column("tax_id_last4", sa.CHAR(length=4), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("tenant_id", "id", name="uq_payees_tenant_id_id"),
        )
        op.create_index("ix_payees_tenant_id", "payees", ["tenant_id"])

    if not insp.has_table("compensation_profiles"):
        op.create_table(
            "compensation_profiles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("payee_id", sa.Integer(), nullable=False),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("worker_type_snapshot", _enum("worker_type"), nullable=False),
            sa.Column("gross_calc_type", _enum("gross_calc_type"), nullable=False),
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
                _enum("settlement_frequency"),
                nullable=False,
                server_default=sa.text("'BIWEEKLY'"),
            ),
            sa.Column("allow_negative_settlement", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column(
                "participates_in_fuel_discount_program",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["tenant_id", "payee_id"],
                ["payees.tenant_id", "payees.id"],
                name="fk_compensation_profiles_tenant_payee",
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint(
                "tenant_id", "payee_id", "effective_from", name="uq_compensation_profiles_payee_effective_from"
            ),
            sa.CheckConstraint(
                "effective_to IS NULL OR effective_to >= effective_from",
                name="ck_compensation_profiles_effective_range",
            ),
            sa.CheckConstraint(
                "percent_rate IS NULL OR (percent_rate > 0 AND percent_rate <= 1)",
                name="ck_compensation_profiles_percent_rate_fraction",
            ),
            sa.CheckConstraint(
                "cpm_loaded IS NULL OR cpm_loaded > 0", name="ck_compensation_profiles_cpm_loaded_positive"
            ),
            sa.CheckConstraint(
                "cpm_empty IS NULL OR cpm_empty >= 0", name="ck_compensation_profiles_cpm_empty_nonnegative"
            ),
            sa.CheckConstraint(
                "dispatch_fee_rate >= 0 AND dispatch_fee_rate <= 1",
                name="ck_compensation_profiles_dispatch_fee_rate_fraction",
            ),
        )
        op.create_index("ix_compensation_profiles_tenant_id", "compensation_profiles", ["tenant_id"])
        op.create_index("ix_compensation_profiles_payee_id", "compensation_profiles", ["payee_id"])
        op.create_index(
            "uq_compensation_profiles_one_open_version",
            "compensation_profiles",
            ["tenant_id", "payee_id"],
            unique=True,
            postgresql_where=sa.text("effective_to IS NULL"),
        )

    if insp.has_table("drivers"):
        driver_cols = {c["name"] for c in insp.get_columns("drivers")}
        driver_fks = {fk["name"] for fk in insp.get_foreign_keys("drivers")}
        if "payee_id" in driver_cols and "fk_drivers_payee_id" not in driver_fks:
            op.create_foreign_key(
                "fk_drivers_payee_id", "drivers", "payees", ["payee_id"], ["id"], ondelete="RESTRICT"
            )


def downgrade_payee_compensation() -> None:
    """Drops only empty tables; refuses when any payee or compensation row exists."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in ("compensation_profiles", "payees"):
        if insp.has_table(table) and bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError(f"Refusing to drop non-empty {table}; payroll history must be preserved.")
    if insp.has_table("drivers") and "fk_drivers_payee_id" in {fk["name"] for fk in insp.get_foreign_keys("drivers")}:
        op.drop_constraint("fk_drivers_payee_id", "drivers", type_="foreignkey")
    if insp.has_table("compensation_profiles"):
        op.drop_table("compensation_profiles")
    if insp.has_table("payees"):
        op.drop_table("payees")
