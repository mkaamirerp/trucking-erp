"""platform_tenants: doc_request_link_expiry_days (configurable document-request token lifetime).

Revision ID: 0042_platform_tenants_doc_request_link_expiry_days
Revises: 0041_platform_tenants_person_setup_ui_mode
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0042_platform_tenants_doc_request_link_expiry_days"
down_revision: Union[str, Sequence[str], None] = "0041_platform_tenants_person_setup_ui_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_tenants",
        sa.Column(
            "doc_request_link_expiry_days",
            sa.Integer(),
            nullable=False,
            server_default="21",
        ),
    )


def downgrade() -> None:
    op.drop_column("platform_tenants", "doc_request_link_expiry_days")
