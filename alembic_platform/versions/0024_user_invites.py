"""Add user_invites table for tenant-admin invite flow.

Revision ID: 0024_user_invites
Revises: 0023_company_profile_phone_email
Create Date: 2026-03-15

Stores invite tokens: when tenant admin invites a user, we create a token.
On accept-invite, we validate token, set password, activate TenantMembership.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024_user_invites"
down_revision: Union[str, Sequence[str], None] = "0023_company_profile_phone_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_invites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("inviter_user_id", sa.String(36), sa.ForeignKey("platform_users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_user_invites_user_tenant", "user_invites", ["user_id", "tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_invites_user_tenant", table_name="user_invites")
    op.drop_table("user_invites")
