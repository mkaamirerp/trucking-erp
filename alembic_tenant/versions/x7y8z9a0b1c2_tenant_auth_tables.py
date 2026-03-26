"""Tenant-local auth: tenant_users, tenant_workspace_members, tenant_user_invites.

Revision ID: x7y8z9a0b1c2
Revises: w2x3y4z5a6b7
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "x7y8z9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "w2x3y4z5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
        sa.Column("email_norm", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("password_reset_token_hash", sa.String(255), nullable=True),
        sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("person_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name="fk_tenant_users_person",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("tenant_id", "email_norm", name="uq_tenant_users_tenant_email_norm"),
    )
    op.create_index("ix_tenant_users_tenant_id_email", "tenant_users", ["tenant_id", "email_norm"], unique=False)

    op.create_table(
        "tenant_workspace_members",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
        sa.Column("tenant_user_id", sa.BigInteger(), sa.ForeignKey("tenant_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="invited"),
        sa.Column("role", sa.String(50), nullable=False, server_default="TENANT_MEMBER"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "tenant_user_id", name="uq_twm_tenant_user"),
    )
    op.create_index("ix_twm_tenant_status", "tenant_workspace_members", ["tenant_id", "status"], unique=False)

    op.create_table(
        "tenant_user_invites",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("tenant_user_id", sa.BigInteger(), sa.ForeignKey("tenant_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inviter_tenant_user_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_tenant_user_invites_token_hash"),
    )
    op.create_index("ix_tenant_user_invites_tu", "tenant_user_invites", ["tenant_id", "tenant_user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("tenant_user_invites")
    op.drop_table("tenant_workspace_members")
    op.drop_table("tenant_users")
