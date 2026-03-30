"""Platform: tenant_id on platform_otp_tokens for login step-up OTP context.

Revision ID: 0032_platform_otp_tokens_tenant_id
Revises: 0031_platform_login_password_fail_streaks
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_platform_otp_tokens_tenant_id"
down_revision: Union[str, Sequence[str], None] = "0031_platform_login_password_fail_streaks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_otp_tokens",
        sa.Column("tenant_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_platform_otp_tokens_tenant_id",
        "platform_otp_tokens",
        "platform_tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_platform_otp_tokens_login_step_up_lookup",
        "platform_otp_tokens",
        ["purpose", "tenant_id", "email"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_otp_tokens_login_step_up_lookup", table_name="platform_otp_tokens")
    op.drop_constraint("fk_platform_otp_tokens_tenant_id", "platform_otp_tokens", type_="foreignkey")
    op.drop_column("platform_otp_tokens", "tenant_id")
