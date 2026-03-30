"""Platform: per-tenant login password failure streaks (shared abuse state; human verification).

Revision ID: 0031_platform_login_password_fail_streaks
Revises: 0030_platform_workspace_intake_requests
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_platform_login_password_fail_streaks"
down_revision: Union[str, Sequence[str], None] = "0030_platform_workspace_intake_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_login_password_fail_streaks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("email_fingerprint", sa.String(length=32), nullable=False),
        sa.Column("streak_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["platform_tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "email_fingerprint", name="uq_plpfs_tenant_fp"),
    )
    op.create_index(
        "ix_platform_login_password_fail_streaks_tenant_fp",
        "platform_login_password_fail_streaks",
        ["tenant_id", "email_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_login_password_fail_streaks_tenant_fp", table_name="platform_login_password_fail_streaks")
    op.drop_table("platform_login_password_fail_streaks")
