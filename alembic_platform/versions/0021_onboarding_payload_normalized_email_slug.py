"""platform_onboarding_payloads: add normalized_email/normalized_slug + pending unique guards.

Fixes concurrency issues in public signup draft creation:
- Ensure at most one PENDING (tenant_id IS NULL) draft per normalized email.
- Ensure at most one PENDING (tenant_id IS NULL) draft per normalized workspace slug.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_onboarding_payload_normalized_email_slug"
down_revision: Union[str, Sequence[str], None] = "0020_onboarding_token_lookup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Columns (nullable; backfilled best-effort)
    op.add_column(
        "platform_onboarding_payloads",
        sa.Column("normalized_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "platform_onboarding_payloads",
        sa.Column("normalized_slug", sa.String(length=63), nullable=True),
    )

    # 2) Backfill from payload_json where possible (lower/trim)
    op.execute(
        """
        UPDATE platform_onboarding_payloads
        SET normalized_email = lower(trim(payload_json->>'email'))
        WHERE normalized_email IS NULL
          AND payload_json ? 'email';
        """
    )
    op.execute(
        """
        UPDATE platform_onboarding_payloads
        SET normalized_slug = lower(trim(payload_json->>'workspace_slug'))
        WHERE normalized_slug IS NULL
          AND payload_json ? 'workspace_slug';
        """
    )

    # 3) Indexes + partial unique guards for pending drafts only
    op.create_index(
        "ix_platform_onboarding_payloads_normalized_email",
        "platform_onboarding_payloads",
        ["normalized_email"],
        unique=False,
    )
    op.create_index(
        "ix_platform_onboarding_payloads_normalized_slug",
        "platform_onboarding_payloads",
        ["normalized_slug"],
        unique=False,
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_platform_onboarding_payloads_pending_email
        ON platform_onboarding_payloads (normalized_email)
        WHERE tenant_id IS NULL
          AND status = 'PENDING'
          AND normalized_email IS NOT NULL;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_platform_onboarding_payloads_pending_slug
        ON platform_onboarding_payloads (normalized_slug)
        WHERE tenant_id IS NULL
          AND status = 'PENDING'
          AND normalized_slug IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_platform_onboarding_payloads_pending_slug")
    op.execute("DROP INDEX IF EXISTS uq_platform_onboarding_payloads_pending_email")
    op.drop_index("ix_platform_onboarding_payloads_normalized_slug", table_name="platform_onboarding_payloads")
    op.drop_index("ix_platform_onboarding_payloads_normalized_email", table_name="platform_onboarding_payloads")
    op.drop_column("platform_onboarding_payloads", "normalized_slug")
    op.drop_column("platform_onboarding_payloads", "normalized_email")

