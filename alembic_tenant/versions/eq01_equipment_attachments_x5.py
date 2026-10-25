"""EQ01 physical equipment state: x5/POD/ln01 tenant lineage only.

Revision ID: eq01_equipment_attachments_x5
Revises: ln01_load_number_periods_x5

STOP: this is NOT the FMP revision. Never apply both eq01 siblings.
Shared preflight/revision-target tooling requires separately reviewed update
before any migration execution; this commit is schema-only.
"""

from __future__ import annotations

from alembic_tenant.equipment_attachments_ddl import (
    downgrade_equipment_attachments,
    upgrade_equipment_attachments,
)

revision = "eq01_equipment_attachments_x5"
down_revision = "ln01_load_number_periods_x5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    upgrade_equipment_attachments()


def downgrade() -> None:
    downgrade_equipment_attachments()
