"""BVD import staging — temporary review before Process commits fuel_bvd.

Revision ID: f8c9d0e1f2a3
Revises: f7b8b9c0d1e2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f8c9d0e1f2a3"
down_revision = "f7b8b9c0d1e2"
branch_labels = None
depends_on = None

_BVD_SOURCE_COLUMNS = [
    "invoice_number",
    "invoice_date",
    "start_date",
    "end_date",
    "due_date",
    "client_name",
    "client_address",
    "client_phone",
    "client_email",
    "card_number",
    "hst_number",
    "qst_number",
    "auth_code",
    "driver_name",
    "unit_number",
    "transaction_date",
    "site_number",
    "site_name",
    "site_city",
    "prov_st",
    "prod",
    "qty",
    "retail",
    "billed",
    "pre_tax_amt",
    "hst",
    "gst",
    "pst",
    "qst",
    "disc_rate",
    "disc_amt",
    "final_amt",
    "cur",
    "row_label",
    "product",
    "final_amount",
    "legend_code",
    "legend_product_name",
]


def upgrade() -> None:
    op.create_table(
        "fuel_bvd_import_stage",
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_code", sa.Text(), nullable=False, server_default="BVD"),
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
        sa.Column("invoice_date", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Text(), nullable=True),
        sa.Column("end_date", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
    )
    op.create_index("ix_fuel_bvd_import_stage_tenant", "fuel_bvd_import_stage", ["tenant_id"])
    op.create_index(
        "ix_fuel_bvd_import_stage_tenant_status",
        "fuel_bvd_import_stage",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_fuel_bvd_import_stage_tenant_sha",
        "fuel_bvd_import_stage",
        ["tenant_id", "source_file_sha256"],
    )
    op.create_index(
        "ix_fuel_bvd_import_stage_tenant_invoice",
        "fuel_bvd_import_stage",
        ["tenant_id", "invoice_number"],
    )

    row_cols = [
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_type", sa.Text(), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
    ]
    for name in _BVD_SOURCE_COLUMNS:
        row_cols.append(sa.Column(name, sa.Text(), nullable=True))
    op.create_table("fuel_bvd_stage_row", *row_cols)
    op.create_index("ix_fuel_bvd_stage_row_tenant", "fuel_bvd_stage_row", ["tenant_id"])
    op.create_index(
        "ix_fuel_bvd_stage_row_tenant_stage",
        "fuel_bvd_stage_row",
        ["tenant_id", "stage_id"],
    )

    op.create_table(
        "fuel_bvd_stage_field_correction",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_row_id", sa.BigInteger(), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("extracted_value", sa.Text(), nullable=False),
        sa.Column("reviewed_value", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_fuel_bvd_stage_field_correction_tenant_stage",
        "fuel_bvd_stage_field_correction",
        ["tenant_id", "stage_id"],
    )


def downgrade() -> None:
    op.drop_table("fuel_bvd_stage_field_correction")
    op.drop_table("fuel_bvd_stage_row")
    op.drop_table("fuel_bvd_import_stage")
