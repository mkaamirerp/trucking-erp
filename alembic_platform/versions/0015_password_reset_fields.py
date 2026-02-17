"""Add password reset token fields to platform_users.

Revision ID: 0015_password_reset
Revises: 0014_tenant_memberships
Create Date: 2026-02-16

Stores hashed reset token and expiry for forgot-password flow.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_password_reset"
down_revision: Union[str, Sequence[str], None] = "0014_tenant_memberships"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_users",
        sa.Column("password_reset_token_hash", sa.String(255), nullable=True),
    )
    op.add_column(
        "platform_users",
        sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("platform_users", "password_reset_expires_at")
    op.drop_column("platform_users", "password_reset_token_hash")
