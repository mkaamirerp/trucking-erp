"""Merge loser groundwork: merged_into + merged_at on global booking brokers.

Revision ID: 0039_global_booking_broker_merge_links
Revises: 0038_global_booking_broker_cvor
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0039_global_booking_broker_merge_links"
down_revision: Union[str, Sequence[str], None] = "0038_global_booking_broker_cvor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("global_booking_brokers")}
    if "merged_into_global_broker_id" not in cols:
        op.add_column(
            "global_booking_brokers",
            sa.Column("merged_into_global_broker_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_global_booking_brokers_merged_into",
            "global_booking_brokers",
            "global_booking_brokers",
            ["merged_into_global_broker_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            "ix_global_booking_brokers_merged_into",
            "global_booking_brokers",
            ["merged_into_global_broker_id"],
        )
    if "merged_at" not in cols:
        op.add_column(
            "global_booking_brokers",
            sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("global_booking_brokers")}
    if "merged_at" in cols:
        op.drop_column("global_booking_brokers", "merged_at")
    if "merged_into_global_broker_id" in cols:
        op.drop_index(
            "ix_global_booking_brokers_merged_into",
            table_name="global_booking_brokers",
        )
        op.drop_constraint(
            "fk_global_booking_brokers_merged_into",
            "global_booking_brokers",
            type_="foreignkey",
        )
        op.drop_column("global_booking_brokers", "merged_into_global_broker_id")
