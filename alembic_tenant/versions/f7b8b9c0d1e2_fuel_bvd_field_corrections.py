"""BVD Implementation 1 — append-only field review corrections overlay.

Revision ID: f7b8b9c0d1e2
Revises: f6a7b8c9d0e1

Does not mutate fuel_bvd extracted TEXT columns. Latest correction per (row, field) wins at read time.
Created only — apply via tenant_upgrade_head.sh when approved.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f7b8b9c0d1e2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuel_bvd_field_correction",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fuel_bvd_id", sa.BigInteger(), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("extracted_value", sa.Text(), nullable=False),
        sa.Column("reviewed_value", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fuel_bvd_field_correction_tenant_id_id"),
    )
    op.create_index("ix_fuel_bvd_field_correction_tenant", "fuel_bvd_field_correction", ["tenant_id"])
    op.create_index(
        "ix_fuel_bvd_field_correction_tenant_import",
        "fuel_bvd_field_correction",
        ["tenant_id", "import_id"],
    )
    op.create_index(
        "ix_fuel_bvd_field_correction_tenant_row_field",
        "fuel_bvd_field_correction",
        ["tenant_id", "fuel_bvd_id", "field_name", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_fuel_bvd_field_correction_tenant_row_field", table_name="fuel_bvd_field_correction")
    op.drop_index("ix_fuel_bvd_field_correction_tenant_import", table_name="fuel_bvd_field_correction")
    op.drop_index("ix_fuel_bvd_field_correction_tenant", table_name="fuel_bvd_field_correction")
    op.drop_table("fuel_bvd_field_correction")
