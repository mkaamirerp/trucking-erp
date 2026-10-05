"""Toll FILE/CSV intake foundation (Segment 2).

Revision ID: u2v3w4x5y6z7
Revises: t1a2b3c4d5e6

Durable unmapped CSV source rows only. FILE envelope remains toll_source_batches.
Does not create toll_file_intakes. Does not write canonical toll_transactions.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "u2v3w4x5y6z7"
down_revision = "t1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "toll_file_source_rows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("source_row_order", sa.Integer(), nullable=False),
        sa.Column("source_row_id", sa.String(length=128), nullable=True),
        sa.Column("cells", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_toll_file_source_rows_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "batch_id",
            "source_row_order",
            name="uq_toll_file_source_rows_tenant_batch_source_row_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["toll_source_batches.tenant_id", "toll_source_batches.id"],
            name="fk_toll_file_source_rows_batch_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(cells) = 'object'",
            name="ck_toll_file_source_rows_cells_object",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(values) = 'array'",
            name="ck_toll_file_source_rows_values_array",
        ),
    )
    op.create_index(
        "ix_toll_file_source_rows_tenant_id",
        "toll_file_source_rows",
        ["tenant_id"],
    )
    op.create_index(
        "ix_toll_file_source_rows_tenant_batch",
        "toll_file_source_rows",
        ["tenant_id", "batch_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_toll_file_source_rows_tenant_batch", table_name="toll_file_source_rows"
    )
    op.drop_index("ix_toll_file_source_rows_tenant_id", table_name="toll_file_source_rows")
    op.drop_table("toll_file_source_rows")
