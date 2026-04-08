"""Persisted merge preview rows (read-only analysis; execute in later revision).

Revision ID: 0040_global_booking_broker_merge_previews
Revises: 0039_global_booking_broker_merge_links
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0040_global_booking_broker_merge_previews"
down_revision: Union[str, Sequence[str], None] = "0039_global_booking_broker_merge_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("global_booking_broker_merge_previews"):
        return
    op.execute(sa.text("DROP SEQUENCE IF EXISTS global_booking_broker_merge_previews_id_seq CASCADE"))
    op.create_table(
        "global_booking_broker_merge_previews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_global_broker_id", sa.Integer(), nullable=False),
        sa.Column("survivor_global_broker_id", sa.Integer(), nullable=False),
        sa.Column("duplicate_candidate_id", sa.Integer(), nullable=True),
        sa.Column("preview_hash", sa.String(length=64), nullable=False),
        sa.Column("preview_payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_global_broker_id"],
            ["global_booking_brokers.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["survivor_global_broker_id"],
            ["global_booking_brokers.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_candidate_id"],
            ["global_booking_broker_duplicate_candidates.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gbb_merge_previews_hash",
        "global_booking_broker_merge_previews",
        ["preview_hash"],
    )
    op.create_index(
        "ix_gbb_merge_previews_created",
        "global_booking_broker_merge_previews",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_gbb_merge_previews_created", table_name="global_booking_broker_merge_previews")
    op.drop_index("ix_gbb_merge_previews_hash", table_name="global_booking_broker_merge_previews")
    op.drop_table("global_booking_broker_merge_previews")
