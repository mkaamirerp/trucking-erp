"""fuel manual entry staging table

Revision ID: m7n8o9p0q1r2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-04 05:15:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "m7n8o9p0q1r2"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fuel_manual_entry_stage",
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_code", sa.Text(), nullable=False, server_default="MANUAL_ENTRY"),
        sa.Column("status", sa.Text(), nullable=False, server_default="ACTIVE"),
        sa.Column("entry_method", sa.Text(), nullable=False, server_default="DIRECT"),
        sa.Column("draft_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("extraction_raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("requires_review", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_file_name", sa.Text(), nullable=True),
        sa.Column("source_file_sha256", sa.Text(), nullable=True),
        sa.Column("source_storage_ref", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by", sa.Text(), nullable=True),
        sa.Column("processed_batch_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_fuel_manual_entry_stage_tenant", "fuel_manual_entry_stage", ["tenant_id"])
    op.create_index(
        "ix_fuel_manual_entry_stage_tenant_status",
        "fuel_manual_entry_stage",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_fuel_manual_entry_stage_tenant_status", table_name="fuel_manual_entry_stage")
    op.drop_index("ix_fuel_manual_entry_stage_tenant", table_name="fuel_manual_entry_stage")
    op.drop_table("fuel_manual_entry_stage")
