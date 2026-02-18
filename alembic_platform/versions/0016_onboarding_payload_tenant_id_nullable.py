"""Allow platform_onboarding_payloads.tenant_id NULL for draft signup (pre-OTP)."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_onboarding_payload_tenant_id_nullable"
down_revision: Union[str, Sequence[str], None] = "0015_password_reset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow tenant_id NULL for draft signup (pre-OTP); unique index still allows one payload per tenant when set
    op.alter_column(
        "platform_onboarding_payloads",
        "tenant_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "platform_onboarding_payloads",
        "tenant_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
