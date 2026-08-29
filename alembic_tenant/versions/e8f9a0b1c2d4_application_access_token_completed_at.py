"""Add completed_at to application_access_tokens for DL capture sessions.

Revision ID: e8f9a0b1c2d4
Revises: d7e8f0a1b2c3
Create Date: 2026-08-29

DL capture reuses application_access_tokens with purpose=dl_capture.
FRONT/BACK progress stays in person_applications.intake_payload only.
completed_at marks the capture session COMPLETE after both sides PROCESSED.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e8f9a0b1c2d4"
down_revision = "d7e8f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_access_tokens",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application_access_tokens", "completed_at")
