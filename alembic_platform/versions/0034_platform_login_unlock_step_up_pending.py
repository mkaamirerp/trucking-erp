"""Platform: one-shot login step-up after admin unlock (tenant+email fingerprint).

Revision ID: 0034_platform_login_unlock_step_up_pending
Revises: 0033_platform_login_otp_challenges
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034_platform_login_unlock_step_up_pending"
down_revision: Union[str, Sequence[str], None] = "0033_platform_login_otp_challenges"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_login_unlock_step_up_pending",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("email_fingerprint", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["platform_tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "email_fingerprint", name="uq_plusup_tenant_fp"),
    )
    op.create_index(
        "ix_platform_login_unlock_step_up_pending_tenant_id",
        "platform_login_unlock_step_up_pending",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_login_unlock_step_up_pending_tenant_id", table_name="platform_login_unlock_step_up_pending")
    op.drop_table("platform_login_unlock_step_up_pending")
