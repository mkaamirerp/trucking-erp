"""Add tenant_integration_secrets for encrypted credential storage.

Revision ID: 0026_tenant_integration_secrets
Revises: 0025_platform_users_username
Create Date: 2026-03-23

Control-plane table: encrypted secrets for tenant integrations (email mailbox, etc).
Tenant DB holds metadata + credential_ref_id only; secrets live here.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026_tenant_integration_secrets"
down_revision: Union[str, Sequence[str], None] = "0025_platform_users_username"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_integration_secrets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("integration_type", sa.String(50), nullable=False, server_default="email_mailbox"),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("credential_ref", sa.String(64), nullable=False),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["platform_tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenant_integration_secrets_tenant_type", "tenant_integration_secrets", ["tenant_id", "integration_type"])
    op.create_index("ix_tenant_integration_secrets_credential_ref", "tenant_integration_secrets", ["credential_ref"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_tenant_integration_secrets_credential_ref", table_name="tenant_integration_secrets")
    op.drop_index("ix_tenant_integration_secrets_tenant_type", table_name="tenant_integration_secrets")
    op.drop_table("tenant_integration_secrets")
