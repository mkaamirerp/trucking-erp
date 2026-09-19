"""Fuel Segment 3 historical resolution tables.

Revision ID: f3d4e5f6a7b8
Revises: f2c3d4e5f6a7

Effective-dated unit-number history, truck ownership/payee history, and Fuel
card/account assignment history. Resolution uses transaction datetime; never
current-assignment fallback.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f3d4e5f6a7b8"
down_revision = "f2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Prerequisite for composite tenant FKs from history tables.
    op.create_unique_constraint("uq_trucks_tenant_id_id", "trucks", ["tenant_id", "id"])

    op.create_table(
        "truck_unit_number_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("truck_id", sa.Integer(), nullable=False),
        sa.Column("unit_number", sa.String(length=50), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("changed_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_truck_unit_number_history_tenant_id_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "truck_id"],
            ["trucks.tenant_id", "trucks.id"],
            name="fk_truck_unit_number_history_truck_tenant",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_truck_unit_number_history_tenant_id", "truck_unit_number_history", ["tenant_id"]
    )
    op.create_index(
        "ix_truck_unit_number_history_tenant_truck",
        "truck_unit_number_history",
        ["tenant_id", "truck_id"],
    )
    op.create_index(
        "ix_truck_unit_number_history_tenant_unit_from",
        "truck_unit_number_history",
        ["tenant_id", "unit_number", "effective_from"],
    )

    op.create_table(
        "truck_ownership_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("truck_id", sa.Integer(), nullable=False),
        sa.Column("ownership_type", sa.String(length=30), nullable=False),
        sa.Column("owner_operator_payee_id", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("changed_by", sa.String(length=36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_truck_ownership_history_tenant_id_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "truck_id"],
            ["trucks.tenant_id", "trucks.id"],
            name="fk_truck_ownership_history_truck_tenant",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_truck_ownership_history_tenant_id", "truck_ownership_history", ["tenant_id"]
    )
    op.create_index(
        "ix_truck_ownership_history_tenant_truck",
        "truck_ownership_history",
        ["tenant_id", "truck_id"],
    )
    op.create_index(
        "ix_truck_ownership_history_tenant_truck_from",
        "truck_ownership_history",
        ["tenant_id", "truck_id", "effective_from"],
    )

    op.create_table(
        "fuel_card_account_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("provider_code", sa.String(length=40), nullable=False),
        sa.Column("account_reference", sa.String(length=128), nullable=True),
        sa.Column("card_or_account_id", sa.String(length=64), nullable=False),
        sa.Column("truck_id", sa.Integer(), nullable=True),
        sa.Column("driver_id", sa.Integer(), nullable=True),
        sa.Column("owner_operator_payee_id", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("changed_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_fuel_card_account_assignments_tenant_id_id"
        ),
    )
    op.create_index(
        "ix_fuel_card_account_assignments_tenant_id",
        "fuel_card_account_assignments",
        ["tenant_id"],
    )
    op.create_index(
        "ix_fuel_card_account_assignments_tenant_card",
        "fuel_card_account_assignments",
        ["tenant_id", "provider_code", "card_or_account_id", "effective_from"],
    )
    op.create_index(
        "ix_fuel_card_account_assignments_tenant_account",
        "fuel_card_account_assignments",
        ["tenant_id", "provider_code", "account_reference"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fuel_card_account_assignments_tenant_account",
        table_name="fuel_card_account_assignments",
    )
    op.drop_index(
        "ix_fuel_card_account_assignments_tenant_card",
        table_name="fuel_card_account_assignments",
    )
    op.drop_index(
        "ix_fuel_card_account_assignments_tenant_id",
        table_name="fuel_card_account_assignments",
    )
    op.drop_table("fuel_card_account_assignments")
    op.drop_index(
        "ix_truck_ownership_history_tenant_truck_from", table_name="truck_ownership_history"
    )
    op.drop_index("ix_truck_ownership_history_tenant_truck", table_name="truck_ownership_history")
    op.drop_index("ix_truck_ownership_history_tenant_id", table_name="truck_ownership_history")
    op.drop_table("truck_ownership_history")
    op.drop_index(
        "ix_truck_unit_number_history_tenant_unit_from", table_name="truck_unit_number_history"
    )
    op.drop_index(
        "ix_truck_unit_number_history_tenant_truck", table_name="truck_unit_number_history"
    )
    op.drop_index("ix_truck_unit_number_history_tenant_id", table_name="truck_unit_number_history")
    op.drop_table("truck_unit_number_history")
    op.drop_constraint("uq_trucks_tenant_id_id", "trucks", type_="unique")
