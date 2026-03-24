"""CHECK constraint: intake_bucket allowed values include linked.

Revision ID: w2x3y4z5a6b7
Revises: v1a2b3c4d5e6
Create Date: 2026-03-24
"""

from __future__ import annotations

from alembic import op

revision = "w2x3y4z5a6b7"
down_revision = "v1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_email_threads_intake_bucket_allowed",
        "email_threads",
        "intake_bucket IN ('new_load', 'needs_review', 'linked', 'disregarded')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_email_threads_intake_bucket_allowed", "email_threads", type_="check")
