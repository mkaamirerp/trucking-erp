"""platform_tenants: person_setup_ui_mode (combined vs segmented).

Revision ID: 0041_platform_tenants_person_setup_ui_mode
Revises: 0040_global_booking_broker_merge_previews
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0041_platform_tenants_person_setup_ui_mode"
down_revision: Union[str, Sequence[str], None] = "0040_global_booking_broker_merge_previews"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_tenants",
        sa.Column(
            "person_setup_ui_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'combined'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("platform_tenants", "person_setup_ui_mode")
