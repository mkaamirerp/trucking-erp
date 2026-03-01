"""Add failed_attempts to platform_otp_tokens for brute-force protection."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_otp_failed_attempts"
down_revision: Union[str, Sequence[str], None] = "0018_onboarding_public_id_uuid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_otp_tokens",
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("platform_otp_tokens", "failed_attempts")
