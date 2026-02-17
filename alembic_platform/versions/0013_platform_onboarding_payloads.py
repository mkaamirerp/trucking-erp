"""Add platform_onboarding_payloads for server-side signup payload (prefill at setup, consume on complete)."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0013_onboarding_payloads"
down_revision: Union[str, Sequence[str], None] = "0012_account_setup_requirements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_onboarding_payloads",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload_json", JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_platform_onboarding_payloads_tenant_id", "platform_onboarding_payloads", ["tenant_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_platform_onboarding_payloads_tenant_id", table_name="platform_onboarding_payloads")
    op.drop_table("platform_onboarding_payloads")
