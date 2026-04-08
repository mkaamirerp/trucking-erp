"""Broker intake policy, load broker provenance, attachment content hash.

Revision ID: a8f7e6d5c4b3
Revises: f9a0b1c2d3e4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "a8f7e6d5c4b3"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    # --- brokers ---
    cols = {c["name"] for c in inspector.get_columns("brokers")}
    if "intake_blocked" not in cols:
        op.add_column(
            "brokers",
            sa.Column("intake_blocked", sa.Boolean(), nullable=False, server_default="false"),
        )
    if "auto_created" not in cols:
        op.add_column(
            "brokers",
            sa.Column("auto_created", sa.Boolean(), nullable=False, server_default="false"),
        )
    if "auto_create_origin" not in cols:
        op.add_column("brokers", sa.Column("auto_create_origin", sa.String(length=64), nullable=True))
    if "auto_create_needs_review" not in cols:
        op.add_column(
            "brokers",
            sa.Column("auto_create_needs_review", sa.Boolean(), nullable=False, server_default="false"),
        )

    # --- loads ---
    lcols = {c["name"] for c in inspector.get_columns("loads")}
    if "broker_match_method" not in lcols:
        op.add_column("loads", sa.Column("broker_match_method", sa.String(length=32), nullable=True))
    if "broker_match_confidence_tier" not in lcols:
        op.add_column("loads", sa.Column("broker_match_confidence_tier", sa.String(length=8), nullable=True))
    if "broker_match_explanation" not in lcols:
        op.add_column("loads", sa.Column("broker_match_explanation", sa.Text(), nullable=True))
    if "review_required" not in lcols:
        op.add_column(
            "loads",
            sa.Column("review_required", sa.Boolean(), nullable=False, server_default="false"),
        )
    if "is_duplicate_of_load_id" not in lcols:
        op.add_column("loads", sa.Column("is_duplicate_of_load_id", sa.Integer(), nullable=True))

    inspector = Inspector.from_engine(bind)
    fk_names = {fk["name"] for fk in inspector.get_foreign_keys("loads")}
    if "fk_loads_is_duplicate_of_load_id" not in fk_names:
        op.create_foreign_key(
            "fk_loads_is_duplicate_of_load_id",
            "loads",
            "loads",
            ["is_duplicate_of_load_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # --- email_message_attachments ---
    acols = {c["name"] for c in inspector.get_columns("email_message_attachments")}
    if "content_sha256" not in acols:
        op.add_column(
            "email_message_attachments",
            sa.Column("content_sha256", sa.String(length=64), nullable=True),
        )

    inspector = Inspector.from_engine(bind)
    idx_names = {i["name"] for i in inspector.get_indexes("email_message_attachments")}
    if "ix_email_message_attachments_tenant_content_sha256" not in idx_names:
        op.create_index(
            "ix_email_message_attachments_tenant_content_sha256",
            "email_message_attachments",
            ["tenant_id", "content_sha256"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    idx_names = {i["name"] for i in inspector.get_indexes("email_message_attachments")}
    if "ix_email_message_attachments_tenant_content_sha256" in idx_names:
        op.drop_index("ix_email_message_attachments_tenant_content_sha256", table_name="email_message_attachments")

    acols = {c["name"] for c in inspector.get_columns("email_message_attachments")}
    if "content_sha256" in acols:
        op.drop_column("email_message_attachments", "content_sha256")

    fk_names = {fk["name"] for fk in inspector.get_foreign_keys("loads")}
    if "fk_loads_is_duplicate_of_load_id" in fk_names:
        op.drop_constraint("fk_loads_is_duplicate_of_load_id", "loads", type_="foreignkey")

    lcols = {c["name"] for c in inspector.get_columns("loads")}
    for col in (
        "is_duplicate_of_load_id",
        "review_required",
        "broker_match_explanation",
        "broker_match_confidence_tier",
        "broker_match_method",
    ):
        if col in lcols:
            op.drop_column("loads", col)

    cols = {c["name"] for c in inspector.get_columns("brokers")}
    for col in ("auto_create_needs_review", "auto_create_origin", "auto_created", "intake_blocked"):
        if col in cols:
            op.drop_column("brokers", col)
