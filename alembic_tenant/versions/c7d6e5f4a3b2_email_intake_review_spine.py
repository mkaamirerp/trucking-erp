"""Email intake review state + append-only events (tenant spine for broker/email review).

Revision ID: c7d6e5f4a3b2
Revises: b9a8c7d6e5f4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "c7d6e5f4a3b2"
down_revision = "b9a8c7d6e5f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = inspector.get_table_names()

    if "email_intake_reviews" not in tables:
        op.create_table(
            "email_intake_reviews",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("email_thread_id", sa.Integer(), nullable=False),
            sa.Column("primary_code", sa.String(length=128), nullable=False),
            sa.Column("detail_json", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
            sa.Column("claimed_by_tenant_user_id", sa.BigInteger(), nullable=True),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_routing_reason_snapshot", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["email_thread_id"], ["email_threads.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["claimed_by_tenant_user_id"], ["tenant_users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "email_thread_id", name="uq_email_intake_reviews_tenant_thread"),
        )
        op.create_index("ix_email_intake_reviews_tenant_status", "email_intake_reviews", ["tenant_id", "status"])
        op.create_index("ix_email_intake_reviews_thread", "email_intake_reviews", ["tenant_id", "email_thread_id"])

    if "email_intake_review_events" not in tables:
        op.create_table(
            "email_intake_review_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("email_intake_review_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("actor_kind", sa.String(length=24), nullable=False, server_default="system"),
            sa.Column("actor_tenant_user_id", sa.BigInteger(), nullable=True),
            sa.Column("actor_platform_user_id", sa.String(length=64), nullable=True),
            sa.Column("old_value_json", sa.JSON(), nullable=True),
            sa.Column("new_value_json", sa.JSON(), nullable=True),
            sa.Column("reason_code", sa.String(length=128), nullable=True),
            sa.Column("payload_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(
                ["email_intake_review_id"],
                ["email_intake_reviews.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["actor_tenant_user_id"], ["tenant_users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_email_intake_review_events_review_id",
            "email_intake_review_events",
            ["email_intake_review_id"],
        )
        op.create_index("ix_email_intake_review_events_tenant_created", "email_intake_review_events", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_email_intake_review_events_tenant_created", table_name="email_intake_review_events")
    op.drop_index("ix_email_intake_review_events_review_id", table_name="email_intake_review_events")
    op.drop_table("email_intake_review_events")
    op.drop_index("ix_email_intake_reviews_thread", table_name="email_intake_reviews")
    op.drop_index("ix_email_intake_reviews_tenant_status", table_name="email_intake_reviews")
    op.drop_table("email_intake_reviews")
