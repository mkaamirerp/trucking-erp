"""Audit events for global booking broker promotion lifecycle.

Revision ID: 0036_global_booking_broker_audit_events
Revises: 0035_global_booking_broker_reference
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0036_global_booking_broker_audit_events"
down_revision: Union[str, Sequence[str], None] = "0035_global_booking_broker_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("global_booking_broker_audit_events"):
        return
    op.execute(sa.text("DROP SEQUENCE IF EXISTS global_booking_broker_audit_events_id_seq CASCADE"))
    op.create_table(
        "global_booking_broker_audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("global_broker_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["global_broker_id"], ["global_booking_brokers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_global_booking_broker_audit_events_broker_id",
        "global_booking_broker_audit_events",
        ["global_broker_id"],
    )
    op.create_index(
        "ix_global_booking_broker_audit_events_created_at",
        "global_booking_broker_audit_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_global_booking_broker_audit_events_created_at", table_name="global_booking_broker_audit_events")
    op.drop_index("ix_global_booking_broker_audit_events_broker_id", table_name="global_booking_broker_audit_events")
    op.drop_table("global_booking_broker_audit_events")
