"""PC01 payees + compensation_profiles: FMP/ln01/eq01 tenant lineage only.

Revision ID: pc01_payee_compensation_fmp
Revises: eq01_equipment_attachments_fmp

STOP: this is NOT the x5 revision. Never apply both pc01 siblings.
PENDING: kept outside alembic_tenant/versions so the live graph, preflight approved heads
and tenant_revision_plan.py stay on the eq01 pair. Activation (move into versions/ plus
tooling update) and any execution against tenant_demo/production need owner approval.
"""

from __future__ import annotations

from alembic_tenant.payee_compensation_ddl import (
    downgrade_payee_compensation,
    upgrade_payee_compensation,
)

revision = "pc01_payee_compensation_fmp"
down_revision = "eq01_equipment_attachments_fmp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    upgrade_payee_compensation()


def downgrade() -> None:
    downgrade_payee_compensation()
