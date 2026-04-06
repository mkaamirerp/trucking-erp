"""Tenant: dispatch_trips (canonical trip_number), tenant_dispatch_numbering, load read-model columns.

Revision ID: e7f8a9b0c1d2
Revises: f8e9d0c1b2a3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "f8e9d0c1b2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_dispatch_numbering",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("trip_number_prefix", sa.String(length=16), server_default="", nullable=False),
        sa.Column("prefix_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_numeric", sa.BigInteger(), server_default="10001", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id"),
    )

    op.create_table(
        "dispatch_trips",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("trip_number", sa.String(length=32), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("load_id", sa.Integer(), nullable=True),
        sa.Column("trailer_move_id", sa.Integer(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(CASE WHEN load_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN trailer_move_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_dispatch_trips_exactly_one_target",
        ),
        sa.CheckConstraint(
            "(job_type = 'freight_load' AND load_id IS NOT NULL AND trailer_move_id IS NULL) OR "
            "(job_type = 'trailer_move' AND trailer_move_id IS NOT NULL AND load_id IS NULL)",
            name="ck_dispatch_trips_job_type_matches_fk",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_dispatch_trips_load_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dispatch_trips_tenant_id", "dispatch_trips", ["tenant_id"], unique=False)
    op.create_index("ix_dispatch_trips_tenant_status", "dispatch_trips", ["tenant_id", "status"], unique=False)
    op.create_index("ix_dispatch_trips_tenant_trip_number", "dispatch_trips", ["tenant_id", "trip_number"], unique=True)
    op.create_index(
        "uq_dispatch_trips_tenant_load_active",
        "dispatch_trips",
        ["tenant_id", "load_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND load_id IS NOT NULL"),
    )
    op.create_index(
        "uq_dispatch_trips_tenant_trailer_move_active",
        "dispatch_trips",
        ["tenant_id", "trailer_move_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND trailer_move_id IS NOT NULL"),
    )

    op.add_column("loads", sa.Column("active_dispatch_trip_id", sa.Integer(), nullable=True))
    op.add_column("loads", sa.Column("trip_number", sa.String(length=32), nullable=True))
    op.create_index("ix_loads_active_dispatch_trip_id", "loads", ["active_dispatch_trip_id"], unique=False)
    op.create_index("ix_loads_trip_number", "loads", ["trip_number"], unique=False)
    op.create_foreign_key(
        "fk_loads_active_dispatch_trip",
        "loads",
        "dispatch_trips",
        ["active_dispatch_trip_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_loads_active_dispatch_trip", "loads", type_="foreignkey")
    op.drop_index("ix_loads_trip_number", table_name="loads")
    op.drop_index("ix_loads_active_dispatch_trip_id", table_name="loads")
    op.drop_column("loads", "trip_number")
    op.drop_column("loads", "active_dispatch_trip_id")

    op.drop_index("uq_dispatch_trips_tenant_trailer_move_active", table_name="dispatch_trips")
    op.drop_index("uq_dispatch_trips_tenant_load_active", table_name="dispatch_trips")
    op.drop_index("ix_dispatch_trips_tenant_trip_number", table_name="dispatch_trips")
    op.drop_index("ix_dispatch_trips_tenant_status", table_name="dispatch_trips")
    op.drop_index("ix_dispatch_trips_tenant_id", table_name="dispatch_trips")
    op.drop_table("dispatch_trips")
    op.drop_table("tenant_dispatch_numbering")
