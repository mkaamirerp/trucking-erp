"""Fuel Segment 8 — review queue corrections + batch review state.

Revision ID: f5a6b7c8d9e0
Revises: f4e5f6a7b8c9

Created only — not applied in Segment 8. Append-only extraction corrections;
batch review_version for optimistic concurrency; row review_status on
transactions and controls. Does not implement reconciliation/finalization.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f5a6b7c8d9e0"
down_revision = "f4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fuel_source_batches",
        sa.Column("provider_profile_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "fuel_source_batches",
        sa.Column("layout_status", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "fuel_source_batches",
        sa.Column(
            "review_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.add_column(
        "fuel_source_batches",
        sa.Column("review_started_by", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "fuel_source_batches",
        sa.Column("review_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fuel_source_batches",
        sa.Column(
            "problem_summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_fuel_source_batches_tenant_status",
        "fuel_source_batches",
        ["tenant_id", "status"],
    )

    op.add_column(
        "fuel_transactions",
        sa.Column(
            "review_status",
            sa.String(length=20),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column(
            "requires_review",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column("review_reason", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column("parsed_row_role", sa.String(length=20), server_default="TRANSACTION", nullable=False),
    )
    op.add_column(
        "fuel_transactions",
        sa.Column("reviewed_row_role", sa.String(length=20), nullable=True),
    )

    op.add_column(
        "fuel_source_controls",
        sa.Column(
            "review_status",
            sa.String(length=20),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.add_column(
        "fuel_source_controls",
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "fuel_source_controls",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fuel_source_controls",
        sa.Column("parsed_row_role", sa.String(length=20), server_default="CONTROL", nullable=False),
    )
    op.add_column(
        "fuel_source_controls",
        sa.Column("reviewed_row_role", sa.String(length=20), nullable=True),
    )

    op.create_table(
        "fuel_extraction_corrections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column(
            "parsed_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "reviewed_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_fuel_extraction_corrections_tenant_id_id",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["fuel_source_batches.tenant_id", "fuel_source_batches.id"],
            name="fk_fuel_extraction_corrections_batch_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "entity_type IN ('TRANSACTION', 'CONTROL')",
            name="ck_fuel_extraction_corrections_entity_type",
        ),
        sa.CheckConstraint(
            "char_length(btrim(reason)) > 0",
            name="ck_fuel_extraction_corrections_reason_nonempty",
        ),
    )
    op.create_index(
        "ix_fuel_extraction_corrections_tenant_id",
        "fuel_extraction_corrections",
        ["tenant_id"],
    )
    op.create_index(
        "ix_fuel_extraction_corrections_tenant_batch",
        "fuel_extraction_corrections",
        ["tenant_id", "batch_id"],
    )
    op.create_index(
        "ix_fuel_extraction_corrections_tenant_entity",
        "fuel_extraction_corrections",
        ["tenant_id", "entity_type", "entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_fuel_extraction_corrections_tenant_entity", table_name="fuel_extraction_corrections")
    op.drop_index("ix_fuel_extraction_corrections_tenant_batch", table_name="fuel_extraction_corrections")
    op.drop_index("ix_fuel_extraction_corrections_tenant_id", table_name="fuel_extraction_corrections")
    op.drop_table("fuel_extraction_corrections")

    op.drop_column("fuel_source_controls", "reviewed_row_role")
    op.drop_column("fuel_source_controls", "parsed_row_role")
    op.drop_column("fuel_source_controls", "reviewed_at")
    op.drop_column("fuel_source_controls", "reviewed_by")
    op.drop_column("fuel_source_controls", "review_status")

    op.drop_column("fuel_transactions", "reviewed_row_role")
    op.drop_column("fuel_transactions", "parsed_row_role")
    op.drop_column("fuel_transactions", "review_reason")
    op.drop_column("fuel_transactions", "requires_review")
    op.drop_column("fuel_transactions", "reviewed_at")
    op.drop_column("fuel_transactions", "reviewed_by")
    op.drop_column("fuel_transactions", "review_status")

    op.drop_index("ix_fuel_source_batches_tenant_status", table_name="fuel_source_batches")
    op.drop_column("fuel_source_batches", "problem_summary_json")
    op.drop_column("fuel_source_batches", "review_started_at")
    op.drop_column("fuel_source_batches", "review_started_by")
    op.drop_column("fuel_source_batches", "review_version")
    op.drop_column("fuel_source_batches", "layout_status")
    op.drop_column("fuel_source_batches", "provider_profile_code")
