"""Task 14 checkpoint 1: tenant_load_number_periods (x5 POD branch head).

Revision ID: ln01_load_number_periods_x5
Revises: i14_load_pod_evidence_x5
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic_tenant.ln01_load_number_periods_ddl import (
    downgrade_tenant_load_number_periods,
    upgrade_tenant_load_number_periods,
)

revision: str = "ln01_load_number_periods_x5"
down_revision: Union[str, Sequence[str], None] = "i14_load_pod_evidence_x5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    upgrade_tenant_load_number_periods()


def downgrade() -> None:
    downgrade_tenant_load_number_periods()
