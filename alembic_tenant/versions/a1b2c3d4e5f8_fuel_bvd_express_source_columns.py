"""BVD Express source columns on fuel_bvd and fuel_bvd_stage_row.

Revision ID: a1b2c3d4e5f8
Revises: f8c9d0e1f2a3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f8"
down_revision = "f8c9d0e1f2a3"
branch_labels = None
depends_on = None

_EXPRESS_COLS = (
    "express_code",
    "express_tractor",
    "express_trailer",
    "express_cdl",
    "express_trip_number",
    "amount_cashed",
    "express_fee",
    "payee_raw",
    "notes_raw",
)


def upgrade() -> None:
    for table in ("fuel_bvd", "fuel_bvd_stage_row"):
        for col in _EXPRESS_COLS:
            op.add_column(table, sa.Column(col, sa.Text(), nullable=True))


def downgrade() -> None:
    for table in ("fuel_bvd", "fuel_bvd_stage_row"):
        for col in reversed(_EXPRESS_COLS):
            op.drop_column(table, col)
