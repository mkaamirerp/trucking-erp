"""Toll CSV persistence hardening: ordered headers, provenance, FILE format.

Revision ID: v3w4x5y6z7a8
Revises: u2v3w4x5y6z7

Does not rewrite t1a2b3c4d5e6 or u2v3w4x5y6z7.
Does not create toll_file_intakes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v3w4x5y6z7a8"
down_revision = "u2v3w4x5y6z7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "toll_source_batches",
        sa.Column("csv_raw_header_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "toll_source_batches",
        sa.Column("csv_column_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "toll_source_batches",
        sa.Column("csv_parsed_row_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "toll_source_batches",
        sa.Column("csv_skipped_blank_row_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "toll_source_batches",
        sa.Column("csv_parser_name", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "toll_source_batches",
        sa.Column("csv_parser_version", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "toll_source_batches",
        sa.Column("csv_encoding", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "toll_source_batches",
        sa.Column("csv_delimiter", sa.String(length=8), nullable=True),
    )
    op.create_check_constraint(
        "ck_toll_source_batches_file_requires_format",
        "toll_source_batches",
        "source_type <> 'FILE' OR file_format IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_toll_source_batches_csv_raw_header_names_array",
        "toll_source_batches",
        "csv_raw_header_names IS NULL OR jsonb_typeof(csv_raw_header_names) = 'array'",
    )
    op.create_check_constraint(
        "ck_toll_source_batches_csv_column_keys_array",
        "toll_source_batches",
        "csv_column_keys IS NULL OR jsonb_typeof(csv_column_keys) = 'array'",
    )
    op.add_column(
        "toll_file_source_rows",
        sa.Column("source_line_number", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("toll_file_source_rows", "source_line_number")
    op.drop_constraint(
        "ck_toll_source_batches_csv_column_keys_array",
        "toll_source_batches",
        type_="check",
    )
    op.drop_constraint(
        "ck_toll_source_batches_csv_raw_header_names_array",
        "toll_source_batches",
        type_="check",
    )
    op.drop_constraint(
        "ck_toll_source_batches_file_requires_format",
        "toll_source_batches",
        type_="check",
    )
    op.drop_column("toll_source_batches", "csv_delimiter")
    op.drop_column("toll_source_batches", "csv_encoding")
    op.drop_column("toll_source_batches", "csv_parser_version")
    op.drop_column("toll_source_batches", "csv_parser_name")
    op.drop_column("toll_source_batches", "csv_skipped_blank_row_count")
    op.drop_column("toll_source_batches", "csv_parsed_row_count")
    op.drop_column("toll_source_batches", "csv_column_keys")
    op.drop_column("toll_source_batches", "csv_raw_header_names")
