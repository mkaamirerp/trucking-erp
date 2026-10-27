"""S1 creation snapshot: FMP / EQ01 lineage only.

Revision ID: s1_load_approved_snapshot_fmp
Revises: eq01_equipment_attachments_fmp

STOP: this is NOT the x5 revision. Never apply both S1 siblings.
"""

from __future__ import annotations

from alembic_tenant.load_approved_snapshot_ddl import (
    downgrade_load_approved_commercial_snapshots,
    upgrade_load_approved_commercial_snapshots,
)

revision = "s1_load_approved_snapshot_fmp"
down_revision = "eq01_equipment_attachments_fmp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    upgrade_load_approved_commercial_snapshots()


def downgrade() -> None:
    downgrade_load_approved_commercial_snapshots()
