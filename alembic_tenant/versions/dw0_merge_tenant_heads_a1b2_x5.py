"""Merge tenant Alembic heads before load workspace draft foundation (DW-1).

Revision ID: dw0_merge_tenant_heads_a1b2_x5
Revises: a1b2c3d4e5f7, x5y6z7a8b9c0
Create Date: 2026-10-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "dw0_merge_tenant_heads_a1b2_x5"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e5f7", "x5y6z7a8b9c0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
