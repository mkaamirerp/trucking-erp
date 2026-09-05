"""Add domain_event_outbox for durable transport-independent domain events.

Revision ID: f9a0b1c2d3e5
Revises: e8f9a0b1c2d4
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f9a0b1c2d3e5"
down_revision = "e8f9a0b1c2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domain_event_outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.UniqueConstraint("event_id", name="uq_domain_event_outbox_event_id"),
    )
    op.create_index(
        "ix_domain_event_outbox_tenant_aggregate_id",
        "domain_event_outbox",
        ["tenant_id", "aggregate_type", "aggregate_id", "id"],
    )
    op.create_index(
        "ix_domain_event_outbox_pending",
        "domain_event_outbox",
        ["published_at", "id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_domain_event_outbox_pending", table_name="domain_event_outbox")
    op.drop_index("ix_domain_event_outbox_tenant_aggregate_id", table_name="domain_event_outbox")
    op.drop_table("domain_event_outbox")
