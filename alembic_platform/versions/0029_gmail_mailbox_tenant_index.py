"""Platform index: Gmail mailbox address -> tenant for Pub/Sub push routing.

Revision ID: 0029_gmail_mailbox_tenant_index
Revises: 0028_platform_login_failure_events
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_gmail_mailbox_tenant_index"
down_revision: Union[str, Sequence[str], None] = "0028_platform_login_failure_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_gmail_mailbox_index",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("gmail_address_norm", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["platform_tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gmail_address_norm", name="uq_platform_gmail_mailbox_index_norm"),
    )
    op.create_index(
        "ix_platform_gmail_mailbox_index_tenant_id",
        "platform_gmail_mailbox_index",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_gmail_mailbox_index_tenant_id", table_name="platform_gmail_mailbox_index")
    op.drop_table("platform_gmail_mailbox_index")
