"""BVD Implementation 1 — fuel_bvd source-fidelity table.

Revision ID: f6a7b8c9d0e1
Revises: f5a6b7c8d9e0

Created only — not applied. One table per docs/FUEL_BVD_IMPLEMENTATION_1.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f6a7b8c9d0e1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuel_bvd",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_type", sa.Text(), nullable=False),
        sa.Column("invoice_number", sa.Text(), nullable=True),
        sa.Column("invoice_date", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Text(), nullable=True),
        sa.Column("end_date", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Text(), nullable=True),
        sa.Column("client_name", sa.Text(), nullable=True),
        sa.Column("client_address", sa.Text(), nullable=True),
        sa.Column("client_phone", sa.Text(), nullable=True),
        sa.Column("client_email", sa.Text(), nullable=True),
        sa.Column("card_number", sa.Text(), nullable=True),
        sa.Column("hst_number", sa.Text(), nullable=True),
        sa.Column("qst_number", sa.Text(), nullable=True),
        sa.Column("auth_code", sa.Text(), nullable=True),
        sa.Column("driver_name", sa.Text(), nullable=True),
        sa.Column("unit_number", sa.Text(), nullable=True),
        sa.Column("transaction_date", sa.Text(), nullable=True),
        sa.Column("site_number", sa.Text(), nullable=True),
        sa.Column("site_name", sa.Text(), nullable=True),
        sa.Column("site_city", sa.Text(), nullable=True),
        sa.Column("prov_st", sa.Text(), nullable=True),
        sa.Column("prod", sa.Text(), nullable=True),
        sa.Column("qty", sa.Text(), nullable=True),
        sa.Column("retail", sa.Text(), nullable=True),
        sa.Column("billed", sa.Text(), nullable=True),
        sa.Column("pre_tax_amt", sa.Text(), nullable=True),
        sa.Column("hst", sa.Text(), nullable=True),
        sa.Column("gst", sa.Text(), nullable=True),
        sa.Column("pst", sa.Text(), nullable=True),
        sa.Column("qst", sa.Text(), nullable=True),
        sa.Column("disc_rate", sa.Text(), nullable=True),
        sa.Column("disc_amt", sa.Text(), nullable=True),
        sa.Column("final_amt", sa.Text(), nullable=True),
        sa.Column("cur", sa.Text(), nullable=True),
        sa.Column("row_label", sa.Text(), nullable=True),
        sa.Column("product", sa.Text(), nullable=True),
        sa.Column("final_amount", sa.Text(), nullable=True),
        sa.Column("legend_code", sa.Text(), nullable=True),
        sa.Column("legend_product_name", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_fuel_bvd_tenant_id_id"),
    )
    op.create_index("ix_fuel_bvd_tenant_id", "fuel_bvd", ["tenant_id"])
    op.create_index("ix_fuel_bvd_tenant_import", "fuel_bvd", ["tenant_id", "import_id"])
    op.create_index(
        "ix_fuel_bvd_tenant_import_row",
        "fuel_bvd",
        ["tenant_id", "import_id", "source_row_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_fuel_bvd_tenant_import_row", table_name="fuel_bvd")
    op.drop_index("ix_fuel_bvd_tenant_import", table_name="fuel_bvd")
    op.drop_index("ix_fuel_bvd_tenant_id", table_name="fuel_bvd")
    op.drop_table("fuel_bvd")
