"""Segment A: canonical batch link + fuel_transactions provider extension fields.

Revision ID: c9d0e1f2a3b4
Revises: a1b2c3d4e5f8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "a1b2c3d4e5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fuel_source_batches",
        sa.Column("source_import_ref", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "uq_fuel_source_batches_tenant_provider_import_ref",
        "fuel_source_batches",
        ["tenant_id", "provider_code", "source_import_ref"],
        unique=True,
        postgresql_where=sa.text("source_import_ref IS NOT NULL"),
    )

    for col in (
        "provider_section_raw",
        "provider_reference_raw",
        "provider_reason_raw",
        "classification_status",
        "classification_source",
    ):
        op.add_column("fuel_transactions", sa.Column(col, sa.String(length=255), nullable=True))
    op.add_column("fuel_transactions", sa.Column("principal_amount", sa.Numeric(14, 4), nullable=True))
    op.add_column("fuel_transactions", sa.Column("provider_fee_amount", sa.Numeric(14, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("fuel_transactions", "provider_fee_amount")
    op.drop_column("fuel_transactions", "principal_amount")
    for col in (
        "classification_source",
        "classification_status",
        "provider_reason_raw",
        "provider_reference_raw",
        "provider_section_raw",
    ):
        op.drop_column("fuel_transactions", col)
    op.drop_index(
        "uq_fuel_source_batches_tenant_provider_import_ref",
        table_name="fuel_source_batches",
    )
    op.drop_column("fuel_source_batches", "source_import_ref")
