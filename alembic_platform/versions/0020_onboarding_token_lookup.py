"""Add onboarding_token_lookup for token -> (tenant_id, application_id) resolution."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020_onboarding_token_lookup"
down_revision: Union[str, Sequence[str], None] = "0019_otp_failed_attempts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "onboarding_token_lookup",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("application_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_onboarding_token_lookup_token", "onboarding_token_lookup", ["token"], unique=True)
    op.create_index("ix_onboarding_token_lookup_tenant_id", "onboarding_token_lookup", ["tenant_id"], unique=False)
    op.create_index("ix_onboarding_token_lookup_application_id", "onboarding_token_lookup", ["application_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_onboarding_token_lookup_application_id", table_name="onboarding_token_lookup")
    op.drop_index("ix_onboarding_token_lookup_tenant_id", table_name="onboarding_token_lookup")
    op.drop_index("ix_onboarding_token_lookup_token", table_name="onboarding_token_lookup")
    op.drop_table("onboarding_token_lookup")
