"""Tenant auth cutover: mode on platform_tenants + platform_user <-> tenant_user map.

Revision ID: 0027_tenant_auth_mode
Revises: 0026_tenant_integration_secrets
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027_tenant_auth_mode"
down_revision: Union[str, Sequence[str], None] = "0026_tenant_integration_secrets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_tenants",
        sa.Column("tenant_auth_mode", sa.String(20), nullable=False, server_default="platform"),
    )
    op.create_table(
        "platform_tenant_user_map",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform_user_id", sa.String(36), sa.ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("platform_user_id", "tenant_id", name="uq_ptum_platform_tenant"),
        sa.UniqueConstraint("tenant_id", "tenant_user_id", name="uq_ptum_tenant_tuser"),
    )


def downgrade() -> None:
    op.drop_table("platform_tenant_user_map")
    op.drop_column("platform_tenants", "tenant_auth_mode")
