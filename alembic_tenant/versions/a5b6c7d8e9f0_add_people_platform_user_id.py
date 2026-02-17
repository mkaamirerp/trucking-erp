"""Add people.platform_user_id (link platform identity to tenant People). Partial unique index per tenant.

Revision ID: a5b6c7d8e9f0
Revises: f01a9b2c3d4e
Create Date: 2026-02-16

platform_user_id matches platform_users.id type (VARCHAR(36)/UUID). Nullable.
Unique (tenant_id, platform_user_id) WHERE platform_user_id IS NOT NULL via partial index.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a5b6c7d8e9f0"
down_revision = "f01a9b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "people" not in inspector.get_table_names(schema="public"):
        return
    existing = {c["name"] for c in inspector.get_columns("people", schema="public")}
    if "platform_user_id" not in existing:
        op.add_column(
            "people",
            sa.Column("platform_user_id", sa.String(36), nullable=True),
            schema="public",
        )
    # Partial unique index: (tenant_id, platform_user_id) WHERE platform_user_id IS NOT NULL
    indexes = {i["name"] for i in inspector.get_indexes("people", schema="public")}
    if "uq_people_tenant_platform_user_id" not in indexes:
        op.execute(
            sa.text(
                "CREATE UNIQUE INDEX uq_people_tenant_platform_user_id ON public.people (tenant_id, platform_user_id) "
                "WHERE platform_user_id IS NOT NULL"
            )
        )
    # Lookup index (optional but useful)
    if "ix_people_platform_user_id" not in indexes:
        op.create_index(
            "ix_people_platform_user_id",
            "people",
            ["platform_user_id"],
            unique=False,
            schema="public",
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "people" not in inspector.get_table_names(schema="public"):
        return
    indexes = {i["name"] for i in inspector.get_indexes("people", schema="public")}
    if "ix_people_platform_user_id" in indexes:
        op.execute("DROP INDEX IF EXISTS public.ix_people_platform_user_id")
    if "uq_people_tenant_platform_user_id" in indexes:
        op.execute("DROP INDEX IF EXISTS public.uq_people_tenant_platform_user_id")
    cols = {c["name"] for c in inspector.get_columns("people", schema="public")}
    if "platform_user_id" in cols:
        op.drop_column("people", "platform_user_id", schema="public")
