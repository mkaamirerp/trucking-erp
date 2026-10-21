"""Future Movement Plan (§9A) + load dispatch instructions.

Revision ID: fmp01_future_movement_plan
Revises: i14_load_pod_evidence
Create Date: 2026-10-21

Additive only. Production tenants on i14_load_pod_evidence_x5 require a separate
revision from that head before applying (owner migration path).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "fmp01_future_movement_plan"
down_revision: Union[str, Sequence[str], None] = "i14_load_pod_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "future_movement_plans",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("origin_kind", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("pickup_terminal_id", sa.Integer(), nullable=True),
        sa.Column("planned_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_completion_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("driver_id", sa.Integer(), nullable=True),
        sa.Column("truck_id", sa.Integer(), nullable=True),
        sa.Column("trailer_id", sa.Integer(), nullable=True),
        sa.Column("converted_trip_id", sa.Integer(), nullable=True),
        sa.Column("conversion_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("concurrency_version", sa.Integer(), server_default="1", nullable=False),
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
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["pickup_terminal_id"], ["terminals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["truck_id"], ["trucks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trailer_id"], ["trailers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["converted_trip_id"], ["trips.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fmp_tenant_status", "future_movement_plans", ["tenant_id", "status"])
    op.create_index(
        "uq_fmp_tenant_conversion_idem",
        "future_movement_plans",
        ["tenant_id", "conversion_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("conversion_idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "ix_future_movement_plans_tenant_id", "future_movement_plans", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_future_movement_plans_converted_trip_id",
        "future_movement_plans",
        ["converted_trip_id"],
        unique=False,
    )

    op.create_table(
        "future_movement_plan_loads",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=False),
        sa.Column("load_id", sa.Integer(), nullable=False),
        sa.Column("sequence_hint", sa.Integer(), nullable=True),
        sa.Column("inbound_trip_id", sa.Integer(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["future_movement_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_fmpl_load_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["inbound_trip_id"], ["trips.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fmpl_tenant_plan", "future_movement_plan_loads", ["tenant_id", "plan_id"])
    op.create_index("ix_fmpl_tenant_load", "future_movement_plan_loads", ["tenant_id", "load_id"])
    op.create_index(
        "uq_fmpl_one_open_reservation_per_load",
        "future_movement_plan_loads",
        ["tenant_id", "load_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL AND converted_at IS NULL"),
    )

    op.create_table(
        "load_dispatch_instructions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("load_id", sa.Integer(), nullable=False),
        sa.Column("inbound_trip_id", sa.Integer(), nullable=True),
        sa.Column("terminal_id", sa.Integer(), nullable=True),
        sa.Column("instruction_type", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_ldi_load_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["inbound_trip_id"], ["trips.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["terminal_id"], ["terminals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ldi_tenant_load", "load_dispatch_instructions", ["tenant_id", "load_id"])
    op.create_index(
        "ix_ldi_tenant_inbound_trip", "load_dispatch_instructions", ["tenant_id", "inbound_trip_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ldi_tenant_inbound_trip", table_name="load_dispatch_instructions")
    op.drop_index("ix_ldi_tenant_load", table_name="load_dispatch_instructions")
    op.drop_table("load_dispatch_instructions")
    op.drop_index("uq_fmpl_one_open_reservation_per_load", table_name="future_movement_plan_loads")
    op.drop_index("ix_fmpl_tenant_load", table_name="future_movement_plan_loads")
    op.drop_index("ix_fmpl_tenant_plan", table_name="future_movement_plan_loads")
    op.drop_table("future_movement_plan_loads")
    op.drop_index("ix_future_movement_plans_converted_trip_id", table_name="future_movement_plans")
    op.drop_index("ix_future_movement_plans_tenant_id", table_name="future_movement_plans")
    op.drop_index("uq_fmp_tenant_conversion_idem", table_name="future_movement_plans")
    op.drop_index("ix_fmp_tenant_status", table_name="future_movement_plans")
    op.drop_table("future_movement_plans")
