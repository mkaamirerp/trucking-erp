"""Duplicate candidate pairs for global booking brokers (operator review; no auto-merge).

Revision ID: 0037_global_booking_broker_duplicate_candidates
Revises: 0036_global_booking_broker_audit_events
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0037_global_booking_broker_duplicate_candidates"
down_revision: Union[str, Sequence[str], None] = "0036_global_booking_broker_audit_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("global_booking_broker_duplicate_candidates"):
        return
    op.execute(sa.text("DROP SEQUENCE IF EXISTS global_booking_broker_duplicate_candidates_id_seq CASCADE"))
    op.create_table(
        "global_booking_broker_duplicate_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("broker_id_low", sa.Integer(), nullable=False),
        sa.Column("broker_id_high", sa.Integer(), nullable=False),
        sa.Column("match_signals", sa.Text(), server_default="[]", nullable=False),
        sa.Column("review_status", sa.String(length=32), server_default="open", nullable=False),
        sa.Column("duplicate_review_reason_code", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["broker_id_low"], ["global_booking_brokers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["broker_id_high"], ["global_booking_brokers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("broker_id_low", "broker_id_high", name="uq_global_booking_broker_dup_pair"),
    )
    op.create_index(
        "ix_gbb_dup_candidates_low",
        "global_booking_broker_duplicate_candidates",
        ["broker_id_low"],
    )
    op.create_index(
        "ix_gbb_dup_candidates_high",
        "global_booking_broker_duplicate_candidates",
        ["broker_id_high"],
    )
    op.create_index(
        "ix_gbb_dup_candidates_review_status",
        "global_booking_broker_duplicate_candidates",
        ["review_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_gbb_dup_candidates_review_status", table_name="global_booking_broker_duplicate_candidates")
    op.drop_index("ix_gbb_dup_candidates_high", table_name="global_booking_broker_duplicate_candidates")
    op.drop_index("ix_gbb_dup_candidates_low", table_name="global_booking_broker_duplicate_candidates")
    op.drop_table("global_booking_broker_duplicate_candidates")
