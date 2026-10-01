"""Nationwide fuel provider persistence (staging + accepted source).

Revision ID: e6f7a8b9c0d1
Revises: c5d6e7f8a9b0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e6f7a8b9c0d1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None

_NW_SOURCE_COLUMNS = [
    "account_code",
    "invoice_number",
    "invoice_start_date",
    "invoice_end_date",
    "due_date",
    "customer_name",
    "card_number",
    "unit_number",
    "transaction_date",
    "city",
    "prov_st",
    "product",
    "volume",
    "ex_gst_per_unit",
    "total",
    "network",
    "currency",
    "usa_discount",
    "missed_disc",
    "oon_fees",
    "control_type",
    "row_label",
    "control_line_raw",
    "declared_amount",
    "gst",
    "pst",
    "qst",
    "control_volume",
]


def _source_columns() -> list[sa.Column]:
    cols: list[sa.Column] = []
    for name in _NW_SOURCE_COLUMNS:
        cols.append(sa.Column(name, sa.Text(), nullable=True))
    return cols


def upgrade() -> None:
    op.create_table(
        "fuel_nationwide",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_type", sa.Text(), nullable=False),
        *_source_columns(),
        sa.Column("source_file_name", sa.Text(), nullable=True),
        sa.Column("source_file_sha256", sa.Text(), nullable=True),
        sa.Column("source_storage_ref", sa.Text(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by", sa.Text(), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("processed_by", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.Text(), nullable=True),
        sa.Column("parse_status", sa.Text(), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("extraction_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fuel_nationwide_tenant_id_id"),
    )
    op.create_index("ix_fuel_nationwide_tenant_id", "fuel_nationwide", ["tenant_id"])
    op.create_index("ix_fuel_nationwide_tenant_import", "fuel_nationwide", ["tenant_id", "import_id"])
    op.create_index(
        "ix_fuel_nationwide_tenant_import_row",
        "fuel_nationwide",
        ["tenant_id", "import_id", "source_row_number"],
    )

    op.create_table(
        "fuel_nationwide_field_correction",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fuel_nationwide_id", sa.BigInteger(), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("extracted_value", sa.Text(), nullable=False),
        sa.Column("reviewed_value", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fuel_nationwide_field_correction_tenant_id_id"),
    )
    op.create_index("ix_fuel_nationwide_field_correction_tenant", "fuel_nationwide_field_correction", ["tenant_id"])
    op.create_index(
        "ix_fuel_nationwide_field_correction_tenant_import",
        "fuel_nationwide_field_correction",
        ["tenant_id", "import_id"],
    )

    op.create_table(
        "fuel_nationwide_import_stage",
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_code", sa.Text(), nullable=False, server_default="NATIONWIDE"),
        sa.Column("status", sa.Text(), nullable=False, server_default="ACTIVE"),
        sa.Column("source_file_name", sa.Text(), nullable=True),
        sa.Column("source_file_sha256", sa.Text(), nullable=True),
        sa.Column("source_storage_ref", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.Text(), nullable=True),
        sa.Column("parse_status", sa.Text(), nullable=True),
        sa.Column("extraction_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by", sa.Text(), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("invoice_number", sa.Text(), nullable=True),
        sa.Column("invoice_start_date", sa.Text(), nullable=True),
        sa.Column("invoice_end_date", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_fuel_nationwide_import_stage_tenant", "fuel_nationwide_import_stage", ["tenant_id"])
    op.create_index(
        "ix_fuel_nationwide_import_stage_tenant_status",
        "fuel_nationwide_import_stage",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_fuel_nationwide_import_stage_tenant_sha",
        "fuel_nationwide_import_stage",
        ["tenant_id", "source_file_sha256"],
    )

    op.create_table(
        "fuel_nationwide_stage_row",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_type", sa.Text(), nullable=False),
        *_source_columns(),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
    )
    op.create_index("ix_fuel_nationwide_stage_row_tenant", "fuel_nationwide_stage_row", ["tenant_id"])
    op.create_index(
        "ix_fuel_nationwide_stage_row_tenant_stage",
        "fuel_nationwide_stage_row",
        ["tenant_id", "stage_id"],
    )

    op.create_table(
        "fuel_nationwide_stage_field_correction",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_row_id", sa.BigInteger(), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("extracted_value", sa.Text(), nullable=False),
        sa.Column("reviewed_value", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_fuel_nationwide_stage_field_correction_tenant_stage",
        "fuel_nationwide_stage_field_correction",
        ["tenant_id", "stage_id"],
    )


def downgrade() -> None:
    op.drop_table("fuel_nationwide_stage_field_correction")
    op.drop_table("fuel_nationwide_stage_row")
    op.drop_table("fuel_nationwide_import_stage")
    op.drop_table("fuel_nationwide_field_correction")
    op.drop_table("fuel_nationwide")
