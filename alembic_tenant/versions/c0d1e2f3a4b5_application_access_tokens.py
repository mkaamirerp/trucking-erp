"""application_access_tokens (tenant DB): token for invite links.

Revision ID: c0d1e2f3a4b5
Revises: b9c8d7e6f5a4
Create Date: 2026-02-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c0d1e2f3a4b5"
down_revision = "b9c8d7e6f5a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_access_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.BigInteger(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_application_access_tokens_tenant_id_id"),
    )
    op.create_foreign_key(
        "fk_application_access_tokens_tenant_app_to_applications",
        "application_access_tokens",
        "person_applications",
        ["tenant_id", "application_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_application_access_tokens_tenant_application_id",
        "application_access_tokens",
        ["tenant_id", "application_id"],
    )
    op.create_index(
        "ix_application_access_tokens_token",
        "application_access_tokens",
        ["token"],
        unique=True,
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration; restore from backup to roll back.")
