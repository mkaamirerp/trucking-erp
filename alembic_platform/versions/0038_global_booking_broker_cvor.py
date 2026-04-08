"""Add CVOR (regulatory identifier) to global booking brokers.

Revision ID: 0038_global_booking_broker_cvor
Revises: 0037_global_booking_broker_duplicate_candidates
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0038_global_booking_broker_cvor"
down_revision: Union[str, Sequence[str], None] = "0037_global_booking_broker_duplicate_candidates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = [c["name"] for c in insp.get_columns("global_booking_brokers")]
    if "cvor_number" in cols:
        return
    op.add_column(
        "global_booking_brokers",
        sa.Column("cvor_number", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = [c["name"] for c in insp.get_columns("global_booking_brokers")]
    if "cvor_number" not in cols:
        return
    op.drop_column("global_booking_brokers", "cvor_number")
