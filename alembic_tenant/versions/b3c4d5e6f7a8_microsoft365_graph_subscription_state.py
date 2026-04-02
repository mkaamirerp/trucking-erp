"""Microsoft 365 Graph mail: subscription + delta sync state on tenant_email_accounts.

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f7
Create Date: 2026-03-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenant_email_accounts", sa.Column("ms_graph_subscription_id", sa.String(128), nullable=True))
    op.add_column("tenant_email_accounts", sa.Column("ms_graph_subscription_status", sa.String(32), nullable=True))
    op.add_column(
        "tenant_email_accounts", sa.Column("ms_graph_subscription_expiration_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("tenant_email_accounts", sa.Column("ms_graph_delta_link", sa.Text(), nullable=True))
    op.add_column(
        "tenant_email_accounts", sa.Column("ms_graph_last_notification_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tenant_email_accounts", sa.Column("ms_graph_last_delta_sync_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("tenant_email_accounts", sa.Column("ms_graph_last_sync_status", sa.String(32), nullable=True))
    op.add_column("tenant_email_accounts", sa.Column("ms_graph_last_sync_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenant_email_accounts", "ms_graph_last_sync_error")
    op.drop_column("tenant_email_accounts", "ms_graph_last_sync_status")
    op.drop_column("tenant_email_accounts", "ms_graph_last_delta_sync_at")
    op.drop_column("tenant_email_accounts", "ms_graph_last_notification_at")
    op.drop_column("tenant_email_accounts", "ms_graph_delta_link")
    op.drop_column("tenant_email_accounts", "ms_graph_subscription_expiration_at")
    op.drop_column("tenant_email_accounts", "ms_graph_subscription_status")
    op.drop_column("tenant_email_accounts", "ms_graph_subscription_id")
