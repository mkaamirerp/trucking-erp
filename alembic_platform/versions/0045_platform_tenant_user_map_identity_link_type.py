"""Add identity_link_type provenance to platform_tenant_user_map.

Revision ID: 0045_platform_identity_link_type
Revises: 0044_platform_extraction_sanitized_patterns
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0045_platform_identity_link_type"
down_revision: Union[str, Sequence[str], None] = "0044_platform_extraction_sanitized_patterns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IDENTITY_LINK_LEGACY_COMPAT = "LEGACY_COMPAT"


def upgrade() -> None:
    op.add_column(
        "platform_tenant_user_map",
        sa.Column(
            "identity_link_type",
            sa.String(length=32),
            nullable=False,
            server_default=IDENTITY_LINK_LEGACY_COMPAT,
        ),
    )
    # Existing rows: provenance unknown — never promote from email matching.
    op.execute(
        sa.text(
            "UPDATE platform_tenant_user_map SET identity_link_type = :t WHERE identity_link_type IS NULL"
        ).bindparams(t=IDENTITY_LINK_LEGACY_COMPAT)
    )


def downgrade() -> None:
    op.drop_column("platform_tenant_user_map", "identity_link_type")
