"""Add tenant_email_accounts for Gmail OAuth persistence (V1 slice).

Revision ID: o7p8q9r0s1t2
Revises: n2o3p4q5r6s7
Create Date: 2026-03-23

Tenant-scoped Gmail connection: tokens encrypted in tenant DB.
One primary per tenant in V1. provider=gmail only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "o7p8q9r0s1t2"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_email_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("email_address", sa.String(255), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="CONNECTED"),
        sa.Column("access_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("token_expiry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.String(512), nullable=True),
        sa.Column("provider_account_id", sa.String(255), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("connected_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenant_email_accounts_tenant_id", "tenant_email_accounts", ["tenant_id"])
    op.create_index(
        "ix_tenant_email_accounts_tenant_provider_primary",
        "tenant_email_accounts",
        ["tenant_id", "provider", "is_primary"],
    )
    op.create_unique_constraint(
        "uq_tenant_email_accounts_tenant_provider_primary",
        "tenant_email_accounts",
        ["tenant_id", "provider"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_tenant_email_accounts_tenant_provider_primary", "tenant_email_accounts", type_="unique")
    op.drop_index("ix_tenant_email_accounts_tenant_provider_primary", table_name="tenant_email_accounts")
    op.drop_index("ix_tenant_email_accounts_tenant_id", table_name="tenant_email_accounts")
    op.drop_table("tenant_email_accounts")
