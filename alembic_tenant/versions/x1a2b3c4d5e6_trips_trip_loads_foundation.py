"""Phase 1: trips + trip_loads + loads.active_trip_id; backfill from dispatch_trips; no write-path change.

LIVE-SYNC (READ — Phase 1):
Phase 1 trips / trip_loads / loads.active_trip_id are schema + historical backfill mirror only. The
current live dispatch writer remains dispatch_trips and loads.active_dispatch_trip_id / loads.trip_number.
New dispatches after this migration do NOT insert into trips or trip_loads and do NOT set
loads.active_trip_id. Do not use trips / trip_loads as live operational read authority until Phase 2
dual-write / service flip. Do not change the live writer in this revision.

TRANSACTIONS:
- There are no CREATE INDEX CONCURRENTLY (or other CONCURRENTLY) statements. All DDL + backfill
  statements in upgrade() run inside Alembic's single transaction (see alembic_tenant/env.py:
  do_run_migrations + begin_transaction). On failure before commit, PostgreSQL should roll back
  the entire upgrade for this revision, including all CREATE TABLE/INDEX and INSERT/UPDATE
  in this file.
- If you ever see orphan objects in dev after a failed run, treat as an edge case (manual SQL,
  external tool, or connection out of band) and clean up in dev only; do not add DROP TABLE to this
  migration for prod — a clean pre-upgrade database + a successful one-shot upgrade is the target.

Revision ID: x1a2b3c4d5e6
Revises: w1a2b3c4d5e6
Create Date: 2026-04-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "x1a2b3c4d5e6"
down_revision = "w1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("trip_number", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("trailer_move_id", sa.Integer(), nullable=True),
        sa.Column("legacy_dispatch_trip_id", sa.Integer(), nullable=True),
        sa.Column("driver_id", sa.Integer(), nullable=True),
        sa.Column("truck_id", sa.Integer(), nullable=True),
        sa.Column("trailer_id", sa.Integer(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["legacy_dispatch_trip_id"],
            ["dispatch_trips.id"],
            name="fk_trips_legacy_dispatch_trip",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"], ondelete="SET NULL", name="fk_trips_driver_id"),
        sa.ForeignKeyConstraint(["truck_id"], ["trucks.id"], ondelete="SET NULL", name="fk_trips_truck_id"),
        sa.ForeignKeyConstraint(["trailer_id"], ["trailers.id"], ondelete="SET NULL", name="fk_trips_trailer_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trips_tenant_id", "trips", ["tenant_id"], unique=False)
    op.create_index("ix_trips_tenant_id_status", "trips", ["tenant_id", "status"], unique=False)
    op.create_index("ix_trips_tenant_id_job_type", "trips", ["tenant_id", "job_type"], unique=False)
    op.create_index("ix_trips_tenant_id_driver_id", "trips", ["tenant_id", "driver_id"], unique=False)
    op.create_index("ix_trips_tenant_id_truck_id", "trips", ["tenant_id", "truck_id"], unique=False)
    op.create_index("ix_trips_tenant_id_trailer_id", "trips", ["tenant_id", "trailer_id"], unique=False)
    op.create_index(
        "ix_trips_tenant_trip_number",
        "trips",
        ["tenant_id", "trip_number"],
        unique=True,
    )
    op.create_index(
        "ix_trips_legacy_dispatch_trip_id",
        "trips",
        ["legacy_dispatch_trip_id"],
        unique=True,
        postgresql_where=sa.text("legacy_dispatch_trip_id IS NOT NULL"),
    )

    op.create_table(
        "trip_loads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("load_id", sa.Integer(), nullable=False),
        sa.Column("status_within_trip", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("sequence_hint", sa.Integer(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_trip_loads_load_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name="fk_trip_loads_trip_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trip_loads_tenant_trip_id", "trip_loads", ["tenant_id", "trip_id"], unique=False)
    op.create_index("ix_trip_loads_tenant_load_id", "trip_loads", ["tenant_id", "load_id"], unique=False)
    op.create_index("ix_trip_loads_tenant_status_within", "trip_loads", ["tenant_id", "status_within_trip"], unique=False)
    op.create_index(
        "uq_trip_loads_active_membership",
        "trip_loads",
        ["tenant_id", "trip_id", "load_id"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )

    op.add_column("loads", sa.Column("active_trip_id", sa.Integer(), nullable=True))
    op.create_index("ix_loads_tenant_id_active_trip_id", "loads", ["tenant_id", "active_trip_id"], unique=False)
    op.create_index("ix_loads_active_trip_id", "loads", ["active_trip_id"], unique=False)
    op.create_foreign_key(
        "fk_loads_active_trip",
        "loads",
        "trips",
        ["active_trip_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- Backfill: one trips row per dispatch_trips row
    op.execute(
        sa.text(
            """
            INSERT INTO trips (
                tenant_id, trip_number, status, job_type, trailer_move_id,
                legacy_dispatch_trip_id, driver_id, truck_id, trailer_id,
                assigned_at, created_at, updated_at
            )
            SELECT
                dt.tenant_id,
                dt.trip_number,
                dt.status,
                dt.job_type,
                dt.trailer_move_id,
                dt.id,
                l.driver_id,
                l.truck_id,
                l.trailer_id,
                dt.assigned_at,
                dt.created_at,
                dt.updated_at
            FROM dispatch_trips AS dt
            LEFT JOIN loads AS l
                ON l.tenant_id = dt.tenant_id
                AND l.id = dt.load_id
            """
        )
    )

    # --- trip_loads for freight (load_id not null)
    op.execute(
        sa.text(
            """
            INSERT INTO trip_loads (
                tenant_id, trip_id, load_id, status_within_trip, sequence_hint,
                added_at, removed_at, created_at, updated_at
            )
            SELECT
                dt.tenant_id,
                t.id,
                dt.load_id,
                CASE WHEN dt.status = 'active' THEN 'active' ELSE 'removed' END,
                0,
                COALESCE(dt.assigned_at, dt.created_at, now()),
                CASE
                    WHEN dt.status = 'active' THEN NULL
                    ELSE COALESCE(dt.updated_at, now())
                END,
                now(),
                now()
            FROM dispatch_trips AS dt
            INNER JOIN trips AS t
                ON t.legacy_dispatch_trip_id = dt.id
            WHERE dt.load_id IS NOT NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE loads AS l
            SET active_trip_id = t.id
            FROM trips AS t
            WHERE t.legacy_dispatch_trip_id = l.active_dispatch_trip_id
              AND l.active_dispatch_trip_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_loads_active_trip", "loads", type_="foreignkey")
    op.drop_index("ix_loads_tenant_id_active_trip_id", table_name="loads")
    op.drop_index("ix_loads_active_trip_id", table_name="loads")
    op.drop_column("loads", "active_trip_id")

    op.drop_index("uq_trip_loads_active_membership", table_name="trip_loads")
    op.drop_index("ix_trip_loads_tenant_status_within", table_name="trip_loads")
    op.drop_index("ix_trip_loads_tenant_load_id", table_name="trip_loads")
    op.drop_index("ix_trip_loads_tenant_trip_id", table_name="trip_loads")
    op.drop_table("trip_loads")

    op.drop_index("ix_trips_legacy_dispatch_trip_id", table_name="trips")
    op.drop_index("ix_trips_tenant_trip_number", table_name="trips")
    op.drop_index("ix_trips_tenant_id_trailer_id", table_name="trips")
    op.drop_index("ix_trips_tenant_id_truck_id", table_name="trips")
    op.drop_index("ix_trips_tenant_id_driver_id", table_name="trips")
    op.drop_index("ix_trips_tenant_id_job_type", table_name="trips")
    op.drop_index("ix_trips_tenant_id_status", table_name="trips")
    op.drop_index("ix_trips_tenant_id", table_name="trips")
    op.drop_table("trips")
