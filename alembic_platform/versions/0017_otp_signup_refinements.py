"""OTP signup refinements: onboarding_payload_id + superseded_at on otp_tokens; status on onboarding_payloads."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_otp_signup_refinements"
down_revision: Union[str, Sequence[str], None] = "0016_onboarding_payload_tenant_id_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── platform_otp_tokens ────────────────────────────────────────────────────
    conn = op.get_bind()

    # Add onboarding_payload_id (nullable FK → platform_onboarding_payloads.id)
    op.add_column(
        "platform_otp_tokens",
        sa.Column("onboarding_payload_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_otp_tokens_onboarding_payload_id",
        "platform_otp_tokens",
        "platform_onboarding_payloads",
        ["onboarding_payload_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_otp_tokens_onboarding_payload_id",
        "platform_otp_tokens",
        ["onboarding_payload_id"],
    )

    # Add superseded_at (nullable timestamp)
    op.add_column(
        "platform_otp_tokens",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Composite index for email + created_at: used by verify-otp fallback
    # (WHERE email = ? AND ... ORDER BY created_at DESC)
    op.create_index(
        "ix_otp_tokens_email_created",
        "platform_otp_tokens",
        ["email", "created_at"],
    )

    # ── platform_onboarding_payloads ───────────────────────────────────────────
    op.add_column(
        "platform_onboarding_payloads",
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
    )
    op.add_column(
        "platform_onboarding_payloads",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill: rows with tenant_id already set are COMPLETED; others stay PENDING
    op.execute(
        "UPDATE platform_onboarding_payloads SET status = 'COMPLETED' WHERE tenant_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_otp_tokens_email_created", table_name="platform_otp_tokens")
    op.drop_index("ix_otp_tokens_onboarding_payload_id", table_name="platform_otp_tokens")
    op.drop_constraint(
        "fk_otp_tokens_onboarding_payload_id", "platform_otp_tokens", type_="foreignkey"
    )
    op.drop_column("platform_otp_tokens", "superseded_at")
    op.drop_column("platform_otp_tokens", "onboarding_payload_id")
    op.drop_column("platform_onboarding_payloads", "updated_at")
    op.drop_column("platform_onboarding_payloads", "status")
