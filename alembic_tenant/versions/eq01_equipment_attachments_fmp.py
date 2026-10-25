"""EQ01 physical equipment state: FMP/ln01 tenant lineage only.

Revision ID: eq01_equipment_attachments_fmp
Revises: ln01_load_number_periods_fmp

STOP: this is NOT the x5 revision. Never apply both eq01 siblings.
Shared preflight/revision-target tooling requires separately reviewed update
before any migration execution; this commit is schema-only.
"""

from __future__ import annotations

from alembic_tenant.equipment_attachments_ddl import (
    downgrade_equipment_attachments,
    upgrade_equipment_attachments,
)

revision = "eq01_equipment_attachments_fmp"
down_revision = "ln01_load_number_periods_fmp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    upgrade_equipment_attachments()


def downgrade() -> None:
    downgrade_equipment_attachments()
