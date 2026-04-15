"""application_access_tokens: purpose (invite vs document_resume).

Revision ID: q2w3e4r5t6y7
Revises: d2e3f4a5b6c7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "q2w3e4r5t6y7"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_access_tokens",
        sa.Column(
            "purpose",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'invite'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("application_access_tokens", "purpose")
