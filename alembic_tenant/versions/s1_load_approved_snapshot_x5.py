"""S1 creation snapshot: x5 / EQ01 lineage only.

Revision ID: s1_load_approved_snapshot_x5
Revises: eq01_equipment_attachments_x5

STOP: this is NOT the FMP revision. Never apply both S1 siblings.
"""

from __future__ import annotations

from alembic_tenant.load_approved_snapshot_ddl import (
    downgrade_load_approved_commercial_snapshots,
    upgrade_load_approved_commercial_snapshots,
)

revision = "s1_load_approved_snapshot_x5"
down_revision = "eq01_equipment_attachments_x5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    upgrade_load_approved_commercial_snapshots()


def downgrade() -> None:
    downgrade_load_approved_commercial_snapshots()
