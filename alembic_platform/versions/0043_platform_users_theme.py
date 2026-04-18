"""platform_users: add theme preference column.

Revision ID: 0043_platform_users_theme
Revises: 0042_platform_tenants_doc_request_link_expiry_days
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0043_platform_users_theme"
down_revision: str = "0042_platform_tenants_doc_request_link_expiry_days"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_users",
        sa.Column(
            "theme",
            sa.String(20),
            nullable=False,
            server_default="dark",
        ),
    )


def downgrade() -> None:
    op.drop_column("platform_users", "theme")
