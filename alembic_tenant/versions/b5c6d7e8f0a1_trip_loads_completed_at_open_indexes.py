"""TripLoad completed_at + open-membership uniqueness (planned/active cardinality).

Revision ID: b5c6d7e8f0a1
Revises: a4b5c6d7e8f0
Create Date: 2026-08-12

OPEN = status IN (planned, active) AND completed_at IS NULL AND removed_at IS NULL.
Fails loudly if duplicate open ACTIVE or open PLANNED rows exist per (tenant_id, load_id).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b5c6d7e8f0a1"
down_revision = "a4b5c6d7e8f0"
branch_labels = None
depends_on = None

_OPEN_PRED = (
    "status_within_trip IN ('planned', 'active') "
    "AND completed_at IS NULL AND removed_at IS NULL"
)


def _preflight_no_duplicate_open_cardinality(conn) -> None:
    """STOP if more than one open ACTIVE or open PLANNED exists per (tenant_id, load_id)."""
    active_dups = conn.execute(
        sa.text(
            f"""
            SELECT tenant_id, load_id, count(*)::int AS n
            FROM trip_loads
            WHERE status_within_trip = 'active'
              AND completed_at IS NULL
              AND removed_at IS NULL
            GROUP BY tenant_id, load_id
            HAVING count(*) > 1
            ORDER BY tenant_id, load_id
            """
        )
    ).fetchall()
    planned_dups = conn.execute(
        sa.text(
            f"""
            SELECT tenant_id, load_id, count(*)::int AS n
            FROM trip_loads
            WHERE status_within_trip = 'planned'
              AND completed_at IS NULL
              AND removed_at IS NULL
            GROUP BY tenant_id, load_id
            HAVING count(*) > 1
            ORDER BY tenant_id, load_id
            """
        )
    ).fetchall()
    if not active_dups and not planned_dups:
        return

    lines = [
        "STOP: trip_loads open-cardinality preflight failed.",
        "Do NOT auto-merge or rewrite history. Resolve duplicates manually, then re-run.",
    ]
    if active_dups:
        lines.append("Duplicate open ACTIVE (tenant_id, load_id, count):")
        for tenant_id, load_id, n in active_dups:
            lines.append(f"  tenant_id={tenant_id} load_id={load_id} count={n}")
    if planned_dups:
        lines.append("Duplicate open PLANNED (tenant_id, load_id, count):")
        for tenant_id, load_id, n in planned_dups:
            lines.append(f"  tenant_id={tenant_id} load_id={load_id} count={n}")
    raise RuntimeError("\n".join(lines))


def upgrade() -> None:
    op.add_column(
        "trip_loads",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    conn = op.get_bind()
    _preflight_no_duplicate_open_cardinality(conn)

    op.drop_index("uq_trip_loads_active_membership", table_name="trip_loads")

    op.create_index(
        "uq_trip_loads_open_membership",
        "trip_loads",
        ["tenant_id", "trip_id", "load_id"],
        unique=True,
        postgresql_where=sa.text(_OPEN_PRED),
    )
    op.create_index(
        "uq_trip_loads_one_open_active_per_load",
        "trip_loads",
        ["tenant_id", "load_id"],
        unique=True,
        postgresql_where=sa.text(
            "status_within_trip = 'active' AND completed_at IS NULL AND removed_at IS NULL"
        ),
    )
    op.create_index(
        "uq_trip_loads_one_open_planned_per_load",
        "trip_loads",
        ["tenant_id", "load_id"],
        unique=True,
        postgresql_where=sa.text(
            "status_within_trip = 'planned' AND completed_at IS NULL AND removed_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_trip_loads_one_open_planned_per_load", table_name="trip_loads")
    op.drop_index("uq_trip_loads_one_open_active_per_load", table_name="trip_loads")
    op.drop_index("uq_trip_loads_open_membership", table_name="trip_loads")
    op.create_index(
        "uq_trip_loads_active_membership",
        "trip_loads",
        ["tenant_id", "trip_id", "load_id"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.drop_column("trip_loads", "completed_at")
