"""Platform: public workspace intake requests (email-gated signup entry).

Revision ID: 0030_platform_workspace_intake_requests
Revises: 0029_gmail_mailbox_tenant_index
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030_platform_workspace_intake_requests"
down_revision: Union[str, Sequence[str], None] = "0029_gmail_mailbox_tenant_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_workspace_intake_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone_number", sa.String(length=30), nullable=False),
        sa.Column("selected_package_code", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("intake_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("continuation_token_hash", sa.String(length=64), nullable=True),
        sa.Column("continuation_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("intake_token_hash", name="uq_platform_workspace_intake_token_hash"),
    )
    op.create_index(
        "ix_platform_workspace_intake_requests_email",
        "platform_workspace_intake_requests",
        ["email"],
        unique=False,
    )
    op.create_index(
        "ix_platform_workspace_intake_requests_status_expires",
        "platform_workspace_intake_requests",
        ["status", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_workspace_intake_requests_status_expires", table_name="platform_workspace_intake_requests")
    op.drop_index("ix_platform_workspace_intake_requests_email", table_name="platform_workspace_intake_requests")
    op.drop_table("platform_workspace_intake_requests")
