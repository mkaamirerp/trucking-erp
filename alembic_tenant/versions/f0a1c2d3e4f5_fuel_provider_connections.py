"""Fuel provider connections (Segment 0A).

Revision ID: f0a1c2d3e4f5
Revises: u4v5w6x7y8z9

Tenant metadata only. Secrets stay in platform tenant_integration_secrets
via credential_ref. Provider code is not unique per tenant (multiple accounts).

tenant_id is required even though this table lives in a per-tenant database:
TruckERP tenant data-plane tables use composite isolation (tenant_id, id).
See FuelProviderConnection model docstring.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f0a1c2d3e4f5"
down_revision = "u4v5w6x7y8z9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuel_provider_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("provider_code", sa.String(length=40), nullable=False),
        sa.Column("connection_method", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("account_reference", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("credential_ref", sa.String(length=64), nullable=True),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("auto_sync_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sync_frequency", sa.String(length=40), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(length=64), nullable=True),
        sa.Column("last_sync_result", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(length=64), nullable=True),
        sa.Column("last_test_result", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fuel_provider_connections_tenant_id_id"),
        sa.CheckConstraint(
            "jsonb_typeof(config_json) = 'object'",
            name="ck_fuel_provider_connections_config_json_object",
        ),
    )
    op.create_index(
        "ix_fuel_provider_connections_tenant_id",
        "fuel_provider_connections",
        ["tenant_id"],
    )
    op.create_index(
        "ix_fuel_provider_connections_tenant_provider",
        "fuel_provider_connections",
        ["tenant_id", "provider_code"],
    )
    op.create_index(
        "ix_fuel_provider_connections_tenant_credential_ref",
        "fuel_provider_connections",
        ["tenant_id", "credential_ref"],
        unique=True,
        postgresql_where=sa.text("credential_ref IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fuel_provider_connections_tenant_credential_ref",
        table_name="fuel_provider_connections",
    )
    op.drop_index(
        "ix_fuel_provider_connections_tenant_provider",
        table_name="fuel_provider_connections",
    )
    op.drop_index("ix_fuel_provider_connections_tenant_id", table_name="fuel_provider_connections")
    op.drop_table("fuel_provider_connections")
