"""Task 14 checkpoint 1: tenant_load_number_periods (FMP branch head).

Revision ID: ln01_load_number_periods_fmp
Revises: fmp02_fmp_tenant_scope
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic_tenant.ln01_load_number_periods_ddl import (
    downgrade_tenant_load_number_periods,
    upgrade_tenant_load_number_periods,
)

revision: str = "ln01_load_number_periods_fmp"
down_revision: Union[str, Sequence[str], None] = "fmp02_fmp_tenant_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    upgrade_tenant_load_number_periods()


def downgrade() -> None:
    downgrade_tenant_load_number_periods()
