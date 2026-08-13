"""Custody foundation: terminals, load_custody_events, Load snapshot columns.

Revision ID: d7e8f0a1b2c3
Revises: c6d7e8f0a1b2
Create Date: 2026-08-12

Slice 1 foundation only — no operational custody mutation APIs.
Load snapshot defaults to custody_owner=unknown; bootstrap script is separate.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d7e8f0a1b2c3"
down_revision = "c6d7e8f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "terminals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("street", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state_or_province", sa.String(length=50), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("country", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_terminals_tenant_id", "terminals", ["tenant_id"])
    op.create_index(
        "ix_terminals_tenant_id_is_active",
        "terminals",
        ["tenant_id", "is_active"],
    )
    op.create_index(
        "uq_terminals_tenant_id_name",
        "terminals",
        ["tenant_id", "name"],
        unique=True,
    )

    op.create_table(
        "load_custody_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("load_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("custody_owner_after", sa.String(length=32), nullable=False),
        sa.Column("placement_after", sa.String(length=32), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=True),
        sa.Column("terminal_id", sa.Integer(), nullable=True),
        sa.Column("trailer_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_load_custody_events_load_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name="fk_load_custody_events_trip_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["terminal_id"],
            ["terminals.id"],
            name="fk_load_custody_events_terminal_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trailer_id"],
            ["trailers.id"],
            name="fk_load_custody_events_trailer_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_load_custody_events_tenant_id", "load_custody_events", ["tenant_id"])
    op.create_index(
        "ix_load_custody_events_tenant_load_occurred",
        "load_custody_events",
        ["tenant_id", "load_id", "occurred_at"],
    )
    op.create_index(
        "ix_load_custody_events_tenant_trip_occurred",
        "load_custody_events",
        ["tenant_id", "trip_id", "occurred_at"],
    )
    op.create_index(
        "uq_load_custody_events_idempotency",
        "load_custody_events",
        ["tenant_id", "load_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.add_column(
        "loads",
        sa.Column(
            "custody_owner",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column("loads", sa.Column("custody_trip_id", sa.Integer(), nullable=True))
    op.add_column("loads", sa.Column("custody_terminal_id", sa.Integer(), nullable=True))
    op.add_column(
        "loads",
        sa.Column(
            "custody_placement",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column("loads", sa.Column("custody_trailer_id", sa.Integer(), nullable=True))
    op.add_column(
        "loads",
        sa.Column("custody_since_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "loads",
        sa.Column("last_custody_event_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_loads_custody_trip_id",
        "loads",
        "trips",
        ["custody_trip_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_loads_custody_terminal_id",
        "loads",
        "terminals",
        ["custody_terminal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_loads_custody_trailer_id",
        "loads",
        "trailers",
        ["custody_trailer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_loads_last_custody_event_id",
        "loads",
        "load_custody_events",
        ["last_custody_event_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_loads_tenant_custody_owner", "loads", ["tenant_id", "custody_owner"])


def downgrade() -> None:
    op.drop_index("ix_loads_tenant_custody_owner", table_name="loads")
    op.drop_constraint("fk_loads_last_custody_event_id", "loads", type_="foreignkey")
    op.drop_constraint("fk_loads_custody_trailer_id", "loads", type_="foreignkey")
    op.drop_constraint("fk_loads_custody_terminal_id", "loads", type_="foreignkey")
    op.drop_constraint("fk_loads_custody_trip_id", "loads", type_="foreignkey")
    op.drop_column("loads", "last_custody_event_id")
    op.drop_column("loads", "custody_since_at")
    op.drop_column("loads", "custody_trailer_id")
    op.drop_column("loads", "custody_placement")
    op.drop_column("loads", "custody_terminal_id")
    op.drop_column("loads", "custody_trip_id")
    op.drop_column("loads", "custody_owner")

    op.drop_index("uq_load_custody_events_idempotency", table_name="load_custody_events")
    op.drop_index("ix_load_custody_events_tenant_trip_occurred", table_name="load_custody_events")
    op.drop_index("ix_load_custody_events_tenant_load_occurred", table_name="load_custody_events")
    op.drop_index("ix_load_custody_events_tenant_id", table_name="load_custody_events")
    op.drop_table("load_custody_events")

    op.drop_index("uq_terminals_tenant_id_name", table_name="terminals")
    op.drop_index("ix_terminals_tenant_id_is_active", table_name="terminals")
    op.drop_index("ix_terminals_tenant_id", table_name="terminals")
    op.drop_table("terminals")
