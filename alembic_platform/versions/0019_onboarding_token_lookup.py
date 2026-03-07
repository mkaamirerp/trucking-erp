"""Add onboarding_token_lookup for invite-link token resolution (token -> tenant_id, application_id)."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_onboarding_token_lookup"
down_revision: Union[str, Sequence[str], None] = "0018_onboarding_public_id_uuid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "onboarding_token_lookup",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("application_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_onboarding_token_lookup_token", "onboarding_token_lookup", ["token"], unique=True)
    op.create_index("ix_onboarding_token_lookup_tenant_id", "onboarding_token_lookup", ["tenant_id"])
    op.create_index("ix_onboarding_token_lookup_application_id", "onboarding_token_lookup", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_onboarding_token_lookup_application_id", table_name="onboarding_token_lookup")
    op.drop_index("ix_onboarding_token_lookup_tenant_id", table_name="onboarding_token_lookup")
    op.drop_index("ix_onboarding_token_lookup_token", table_name="onboarding_token_lookup")
    op.drop_table("onboarding_token_lookup")
