"""DW-1: widen load_commercial_evidence.retention_class for commercial_permanent.

Revision ID: dw1d_load_commercial_evidence_retention_varchar32
Revises: dw1c_composite_fk_set_null_optional_columns
Create Date: 2026-10-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "dw1d_load_commercial_evidence_retention_varchar32"
down_revision: Union[str, Sequence[str], None] = "dw1c_composite_fk_set_null_optional_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "load_commercial_evidence",
        "retention_class",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_server_default="commercial_permanent",
    )


def downgrade() -> None:
    op.alter_column(
        "load_commercial_evidence",
        "retention_class",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
        existing_server_default="commercial_permanent",
    )
