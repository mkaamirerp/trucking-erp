"""Add platform_admins table for control-plane admin auth.

Revision ID: 0022_platform_admins
Revises: 0021_onboarding_payload_normalized_email_slug
Create Date: 2026-03-07

Platform admin auth is separate from tenant auth. Uses dedicated table and cookies.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022_platform_admins"
down_revision: Union[str, Sequence[str], None] = "0021_onboarding_payload_normalized_email_slug"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_admins",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform_user_id", sa.String(36), sa.ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_super_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("platform_admins.id", ondelete="SET NULL"), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("platform_admins")
