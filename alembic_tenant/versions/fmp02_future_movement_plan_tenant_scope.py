"""FMP tenant-scoped composite FK: plan lines must match header tenant.

Revision ID: fmp02_fmp_tenant_scope
Revises: fmp01_future_movement_plan
Create Date: 2026-10-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "fmp02_fmp_tenant_scope"
down_revision: Union[str, Sequence[str], None] = "fmp01_future_movement_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_fmp_tenant_id",
        "future_movement_plans",
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        "fk_fmpl_plan_tenant",
        "future_movement_plan_loads",
        "future_movement_plans",
        ["tenant_id", "plan_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_fmpl_plan_tenant", "future_movement_plan_loads", type_="foreignkey")
    op.drop_constraint("uq_fmp_tenant_id", "future_movement_plans", type_="unique")
