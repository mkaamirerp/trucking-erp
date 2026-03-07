"""person_applications + application_access_tokens for invite-link flow (tenant-safe).

Revision ID: f00a1b2c3d4e
Revises: e8f9a0b1c2d3
Create Date: 2026-03-03

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "f00a1b2c3d4e"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) person_applications (tenant-scoped; optional link to people)
    op.create_table(
        "person_applications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("source", sa.String(length=30), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("street_address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("country", sa.String(length=10), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("intake_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_person_applications_tenant_id_id"),
    )
    op.create_index("ix_person_applications_tenant_id", "person_applications", ["tenant_id"])
    op.create_index("ix_person_applications_tenant_status", "person_applications", ["tenant_id", "status"])
    op.create_index("ix_person_applications_tenant_person_id", "person_applications", ["tenant_id", "person_id"])

    # 2) application_access_tokens (invite link tokens)
    op.create_table(
        "application_access_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.BigInteger(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_application_access_tokens_token", "application_access_tokens", ["token"], unique=True)
    op.create_index("ix_application_access_tokens_token_hash", "application_access_tokens", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_application_access_tokens_token_hash", table_name="application_access_tokens")
    op.drop_index("ix_application_access_tokens_token", table_name="application_access_tokens")
    op.drop_index("ix_application_access_tokens_tenant_application_id", table_name="application_access_tokens")
    op.drop_table("application_access_tokens")
    op.drop_index("ix_person_applications_tenant_person_id", table_name="person_applications")
    op.drop_index("ix_person_applications_tenant_status", table_name="person_applications")
    op.drop_index("ix_person_applications_tenant_id", table_name="person_applications")
    op.drop_table("person_applications")
