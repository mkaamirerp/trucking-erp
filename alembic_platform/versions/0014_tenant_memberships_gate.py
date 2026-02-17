"""Add tenant_memberships table (platform membership gate: active/suspended, break-glass owner).

Revision ID: 0014_tenant_memberships
Revises: 0013_onboarding_payloads
Create Date: 2026-02-16

Gates tenant access: user_id + tenant_id + status (active|suspended|pending|invited).
References: platform_users(id), platform_tenants(id).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_tenant_memberships"
down_revision: Union[str, Sequence[str], None] = "0013_onboarding_payloads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_break_glass_owner", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_tenant_memberships_user_tenant"),
    )
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"], unique=False)
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"], unique=False)

    # Backfill from existing platform_tenant_members so current users keep access
    op.execute(
        sa.text("""
            INSERT INTO tenant_memberships (user_id, tenant_id, status, joined_at, is_break_glass_owner)
            SELECT platform_user_id, tenant_id, 'active', created_at,
                   (role IN ('TENANT_OWNER', 'TENANT_ADMIN'))
            FROM platform_tenant_members
            ON CONFLICT (user_id, tenant_id) DO NOTHING
        """)
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_memberships_user_id", table_name="tenant_memberships")
    op.drop_index("ix_tenant_memberships_tenant_id", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
