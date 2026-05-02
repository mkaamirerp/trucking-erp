"""Catch-up: mirror any dispatch_trips row missing a trips.legacy link (Phase1→2A drift); idempotent.

Revision ID: y1a2b3c4d5e4
Revises: x1a2b3c4d5e6
Create Date: 2026-04-27

- Does not alter dispatch_trips, loads.trip_number, or loads.active_dispatch_trip_id.
- Does not allocate new trip numbers (copies from existing dispatch rows only).
- See app.services.trip_mirror_catchup for reusable repair (same SQL).
 Downgrade: no-op (data repair is not auto-reversed).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.services.trip_mirror_catchup import (
    SQL_INSERT_TRIP_LOADS_FOR_NEW_TRIPS,
    SQL_INSERT_TRIPS_FOR_MISSING_MIRRORS,
    SQL_UPDATE_LOADS_ACTIVE_TRIP_ID,
)

revision = "y1a2b3c4d5e4"
down_revision = "x1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(SQL_INSERT_TRIPS_FOR_MISSING_MIRRORS))
    op.execute(sa.text(SQL_INSERT_TRIP_LOADS_FOR_NEW_TRIPS))
    op.execute(sa.text(SQL_UPDATE_LOADS_ACTIVE_TRIP_ID))


def downgrade() -> None:
    pass
