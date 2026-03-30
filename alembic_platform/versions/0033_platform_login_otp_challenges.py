"""Platform: login_otp_challenges + platform_otp_tokens.login_challenge_id for challenge-bound step-up.

Revision ID: 0033_platform_login_otp_challenges
Revises: 0032_platform_otp_tokens_tenant_id
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033_platform_login_otp_challenges"
down_revision: Union[str, Sequence[str], None] = "0032_platform_otp_tokens_tenant_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_login_otp_challenges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("email_norm", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("password_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("otp_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["platform_tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_login_otp_challenges_tid_email",
        "platform_login_otp_challenges",
        ["tenant_id", "email_norm"],
        unique=False,
    )
    op.add_column(
        "platform_otp_tokens",
        sa.Column("login_challenge_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_platform_otp_tokens_login_challenge_id",
        "platform_otp_tokens",
        "platform_login_otp_challenges",
        ["login_challenge_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_platform_otp_tokens_login_challenge_id",
        "platform_otp_tokens",
        ["login_challenge_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_otp_tokens_login_challenge_id", table_name="platform_otp_tokens")
    op.drop_constraint("fk_platform_otp_tokens_login_challenge_id", "platform_otp_tokens", type_="foreignkey")
    op.drop_column("platform_otp_tokens", "login_challenge_id")
    op.drop_index("ix_platform_login_otp_challenges_tid_email", table_name="platform_login_otp_challenges")
    op.drop_table("platform_login_otp_challenges")
