"""Gmail delta-sync cursor on tenant_email_accounts; intake_bucket 'background'.

Revision ID: y9z8a7b6c5d4
Revises: x7y8z9a0b1c2
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "y9z8a7b6c5d4"
down_revision: Union[str, Sequence[str], None] = "x7y8z9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenant_email_accounts",
        sa.Column("gmail_history_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tenant_email_accounts",
        sa.Column("gmail_watch_expiration_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.drop_constraint("ck_email_threads_intake_bucket_allowed", "email_threads", type_="check")
    op.create_check_constraint(
        "ck_email_threads_intake_bucket_allowed",
        "email_threads",
        "intake_bucket IN ('new_load', 'needs_review', 'linked', 'disregarded', 'background')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_email_threads_intake_bucket_allowed", "email_threads", type_="check")
    op.create_check_constraint(
        "ck_email_threads_intake_bucket_allowed",
        "email_threads",
        "intake_bucket IN ('new_load', 'needs_review', 'linked', 'disregarded')",
    )

    op.drop_column("tenant_email_accounts", "gmail_watch_expiration_at")
    op.drop_column("tenant_email_accounts", "gmail_history_id")
