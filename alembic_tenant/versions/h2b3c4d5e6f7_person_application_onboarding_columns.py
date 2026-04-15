"""person_applications: onboarded_* and setup_status (people-level onboarding).

Revision ID: h2b3c4d5e6f7
Revises: p3a1b2c3d4e5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "h2b3c4d5e6f7"
down_revision = "p3a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "person_applications",
        sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "person_applications",
        sa.Column("onboarded_by_user_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "person_applications",
        sa.Column(
            "setup_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.execute(
        """
        UPDATE person_applications
        SET setup_status = 'pending_downstream'
        WHERE status = 'APPROVED'
        """
    )


def downgrade() -> None:
    op.drop_column("person_applications", "setup_status")
    op.drop_column("person_applications", "onboarded_by_user_id")
    op.drop_column("person_applications", "onboarded_at")
