"""Add tenant_email_mailboxes for primary mailbox config.

Revision ID: m1n2o3p4q5r6
Revises: k6f7a8b9c0d1
Create Date: 2026-03-23

Tenant-side metadata only. Secrets stored in platform tenant_integration_secrets.
credential_ref_id links to platform encrypted secret.
Status: NOT_CONFIGURED, CONFIGURED, TESTING, CONNECTED, ERROR, DISABLED.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "m1n2o3p4q5r6"
down_revision = "k6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_email_mailboxes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("credential_ref_id", sa.String(64), nullable=True),
        sa.Column("mailbox_type", sa.String(30), nullable=False, server_default="imap"),
        sa.Column("email_address", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("inbound_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("outbound_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("connection_mode", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("provider_name", sa.String(50), nullable=True),
        sa.Column("imap_host", sa.String(255), nullable=True),
        sa.Column("imap_port", sa.Integer(), nullable=True),
        sa.Column("imap_username", sa.String(255), nullable=True),
        sa.Column("smtp_host", sa.String(255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("smtp_username", sa.String(255), nullable=True),
        sa.Column("use_ssl", sa.Boolean(), nullable=True),
        sa.Column("use_tls", sa.Boolean(), nullable=True),
        sa.Column("oauth_provider", sa.String(50), nullable=True),
        sa.Column("oauth_account_email", sa.String(255), nullable=True),
        sa.Column("sync_cursor", sa.String(255), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(50), nullable=True),
        sa.Column("last_error_code", sa.String(50), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="NOT_CONFIGURED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenant_email_mailboxes_tenant_id", "tenant_email_mailboxes", ["tenant_id"])
    op.create_index("ix_tenant_email_mailboxes_tenant_primary", "tenant_email_mailboxes", ["tenant_id", "is_primary"])


def downgrade() -> None:
    op.drop_index("ix_tenant_email_mailboxes_tenant_primary", table_name="tenant_email_mailboxes")
    op.drop_index("ix_tenant_email_mailboxes_tenant_id", table_name="tenant_email_mailboxes")
    op.drop_table("tenant_email_mailboxes")
