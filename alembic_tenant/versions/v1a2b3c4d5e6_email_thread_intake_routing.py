"""Email thread intake routing and confidence fields.

Revision ID: v1a2b3c4d5e6
Revises: u7v8w9x0y1z2
Create Date: 2026-03-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v1a2b3c4d5e6"
down_revision = "u7v8w9x0y1z2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_threads",
        sa.Column("intake_bucket", sa.String(length=32), server_default="needs_review", nullable=False),
    )
    op.add_column("email_threads", sa.Column("confidence_level", sa.String(length=16), nullable=True))
    op.add_column("email_threads", sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("email_threads", sa.Column("routing_reason", sa.Text(), nullable=True))
    op.create_index("ix_email_threads_intake_bucket", "email_threads", ["intake_bucket"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_email_threads_intake_bucket", table_name="email_threads")
    op.drop_column("email_threads", "routing_reason")
    op.drop_column("email_threads", "confidence_score")
    op.drop_column("email_threads", "confidence_level")
    op.drop_column("email_threads", "intake_bucket")
