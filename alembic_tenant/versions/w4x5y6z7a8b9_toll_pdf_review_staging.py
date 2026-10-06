"""Toll PDF review staging + MANUAL review-stage foundation.

Revision ID: w4x5y6z7a8b9
Revises: v3w4x5y6z7a8

Does not rewrite prior Toll revisions.
Does not create toll_file_intakes.
Does not create or alter toll_transactions.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "w4x5y6z7a8b9"
down_revision = "v3w4x5y6z7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "toll_pdf_statement_review",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("profile_code", sa.String(length=64), nullable=False),
        sa.Column("parser_name", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=16), nullable=False),
        sa.Column("statement_date", sa.Date(), nullable=True),
        sa.Column("account_number", sa.String(length=64), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("start_balance", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("end_balance", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("total_payment_amount", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("total_payment_count", sa.Integer(), nullable=True),
        sa.Column("source_total_trip_count", sa.Integer(), nullable=True),
        sa.Column("source_total_trip_charge", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("parsed_trip_count", sa.Integer(), nullable=False),
        sa.Column("parsed_total_trip_charge", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("trip_count_matches", sa.Boolean(), nullable=False),
        sa.Column("trip_total_matches", sa.Boolean(), nullable=False),
        sa.Column("reconciliation_ok", sa.Boolean(), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("source_page_count", sa.Integer(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "profile_code IN ('EZPASS_WVPA_MONTHLY_STATEMENT_PDF')",
            name="ck_toll_pdf_statement_review_profile_code",
        ),
        sa.CheckConstraint(
            "review_status IN ('NEEDS_REVIEW', 'RECONCILIATION_FAILED')",
            name="ck_toll_pdf_statement_review_status",
        ),
        sa.CheckConstraint(
            "source_metadata IS NULL OR jsonb_typeof(source_metadata) = 'object'",
            name="ck_toll_pdf_statement_review_source_metadata_object",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["toll_source_batches.tenant_id", "toll_source_batches.id"],
            name="fk_toll_pdf_statement_review_batch_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_toll_pdf_statement_review_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "batch_id",
            name="uq_toll_pdf_statement_review_tenant_batch",
        ),
    )
    op.create_index(
        "ix_toll_pdf_statement_review_tenant_id",
        "toll_pdf_statement_review",
        ["tenant_id"],
    )
    op.create_index(
        "ix_toll_pdf_statement_review_tenant_batch",
        "toll_pdf_statement_review",
        ["tenant_id", "batch_id"],
    )
    op.create_index(
        "ix_toll_pdf_statement_review_tenant_status",
        "toll_pdf_statement_review",
        ["tenant_id", "review_status"],
    )

    op.create_table(
        "toll_pdf_review_rows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("source_row_order", sa.Integer(), nullable=False),
        sa.Column("source_page_number", sa.Integer(), nullable=True),
        sa.Column("post_date", sa.Date(), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=True),
        sa.Column("entry_time", sa.String(length=16), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("exit_time", sa.String(length=16), nullable=True),
        sa.Column("agency_raw", sa.String(length=64), nullable=True),
        sa.Column("entry_location", sa.String(length=255), nullable=True),
        sa.Column("entry_lane", sa.String(length=32), nullable=True),
        sa.Column("exit_location", sa.String(length=255), nullable=True),
        sa.Column("exit_lane", sa.String(length=32), nullable=True),
        sa.Column("transponder_number", sa.String(length=64), nullable=True),
        sa.Column("plate_number", sa.String(length=32), nullable=True),
        sa.Column("trip_charge", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("trip_charge_raw", sa.String(length=32), nullable=True),
        sa.Column("source_group_transponder", sa.String(length=64), nullable=True),
        sa.Column("source_group_plate", sa.String(length=32), nullable=True),
        sa.Column("provider_raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(provider_raw) = 'object'",
            name="ck_toll_pdf_review_rows_provider_raw_object",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["toll_source_batches.tenant_id", "toll_source_batches.id"],
            name="fk_toll_pdf_review_rows_batch_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_toll_pdf_review_rows_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "batch_id",
            "source_row_order",
            name="uq_toll_pdf_review_rows_tenant_batch_source_row_order",
        ),
    )
    op.create_index(
        "ix_toll_pdf_review_rows_tenant_id",
        "toll_pdf_review_rows",
        ["tenant_id"],
    )
    op.create_index(
        "ix_toll_pdf_review_rows_tenant_batch",
        "toll_pdf_review_rows",
        ["tenant_id", "batch_id"],
    )

    op.create_table(
        "toll_manual_entry_stages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("file_format", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("post_date", sa.Date(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("event_time", sa.String(length=16), nullable=True),
        sa.Column("agency_raw", sa.String(length=64), nullable=True),
        sa.Column("entry_location", sa.String(length=255), nullable=True),
        sa.Column("entry_lane", sa.String(length=32), nullable=True),
        sa.Column("exit_location", sa.String(length=255), nullable=True),
        sa.Column("exit_lane", sa.String(length=32), nullable=True),
        sa.Column("transponder_number", sa.String(length=64), nullable=True),
        sa.Column("plate_number", sa.String(length=32), nullable=True),
        sa.Column("plate_state", sa.String(length=16), nullable=True),
        sa.Column("trip_charge", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("unresolved_vehicle_identity", sa.Boolean(), nullable=False),
        sa.Column("vehicle_identity_status", sa.String(length=32), nullable=True),
        sa.Column("source_evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("source_type = 'MANUAL'", name="ck_toll_manual_entry_stages_source_type"),
        sa.CheckConstraint("file_format IS NULL", name="ck_toll_manual_entry_stages_file_format_null"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'NEEDS_REVIEW', 'DISCARDED')",
            name="ck_toll_manual_entry_stages_status",
        ),
        sa.CheckConstraint(
            "source_evidence_json IS NULL OR jsonb_typeof(source_evidence_json) = 'object'",
            name="ck_toll_manual_entry_stages_source_evidence_object",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_toll_manual_entry_stages_tenant_id_id"),
    )
    op.create_index(
        "ix_toll_manual_entry_stages_tenant_id",
        "toll_manual_entry_stages",
        ["tenant_id"],
    )
    op.create_index(
        "ix_toll_manual_entry_stages_tenant_status",
        "toll_manual_entry_stages",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_toll_manual_entry_stages_tenant_status",
        table_name="toll_manual_entry_stages",
    )
    op.drop_index("ix_toll_manual_entry_stages_tenant_id", table_name="toll_manual_entry_stages")
    op.drop_table("toll_manual_entry_stages")
    op.drop_index("ix_toll_pdf_review_rows_tenant_batch", table_name="toll_pdf_review_rows")
    op.drop_index("ix_toll_pdf_review_rows_tenant_id", table_name="toll_pdf_review_rows")
    op.drop_table("toll_pdf_review_rows")
    op.drop_index(
        "ix_toll_pdf_statement_review_tenant_status",
        table_name="toll_pdf_statement_review",
    )
    op.drop_index(
        "ix_toll_pdf_statement_review_tenant_batch",
        table_name="toll_pdf_statement_review",
    )
    op.drop_index(
        "ix_toll_pdf_statement_review_tenant_id",
        table_name="toll_pdf_statement_review",
    )
    op.drop_table("toll_pdf_statement_review")
