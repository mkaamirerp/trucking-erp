"""tenant_email_accounts.last_gmail_webhook_at for operator visibility.

Revision ID: z1a2b3c4d5e6
Revises: y9z8a7b6c5d4
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "y9z8a7b6c5d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenant_email_accounts",
        sa.Column("last_gmail_webhook_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_email_accounts", "last_gmail_webhook_at")
