"""Add public_id (UUID) to platform_onboarding_payloads for unguessable signup_id in API."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_onboarding_public_id_uuid"
down_revision: Union[str, Sequence[str], None] = "0017_otp_signup_refinements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_onboarding_payloads",
        sa.Column("public_id", sa.String(36), nullable=True),
    )
    # Backfill existing rows with a UUID
    op.execute(
        "UPDATE platform_onboarding_payloads SET public_id = gen_random_uuid()::text WHERE public_id IS NULL"
    )
    op.alter_column(
        "platform_onboarding_payloads",
        "public_id",
        nullable=False,
    )
    op.create_index(
        "ix_platform_onboarding_payloads_public_id",
        "platform_onboarding_payloads",
        ["public_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_onboarding_payloads_public_id", table_name="platform_onboarding_payloads")
    op.drop_column("platform_onboarding_payloads", "public_id")
