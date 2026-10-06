"""Toll review corrections + Process/canonical lineage.

Revision ID: x5y6z7a8b9c0
Revises: w4x5y6z7a8b9

Does not rewrite w4x5y6z7a8b9.
Does not apply unit mapping.
Does not merge unrelated historical heads.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "x5y6z7a8b9c0"
down_revision = "w4x5y6z7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_toll_pdf_statement_review_status",
        "toll_pdf_statement_review",
        type_="check",
    )
    op.create_check_constraint(
        "ck_toll_pdf_statement_review_status",
        "toll_pdf_statement_review",
        "review_status IN ('NEEDS_REVIEW', 'RECONCILIATION_FAILED', 'PROCESSED')",
    )

    op.drop_constraint(
        "ck_toll_manual_entry_stages_status",
        "toll_manual_entry_stages",
        type_="check",
    )
    op.create_check_constraint(
        "ck_toll_manual_entry_stages_status",
        "toll_manual_entry_stages",
        "status IN ('DRAFT', 'NEEDS_REVIEW', 'PROCESSED', 'DISCARDED')",
    )

    op.create_table(
        "toll_pdf_review_field_corrections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("review_row_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("original_value", sa.Text(), nullable=True),
        sa.Column("corrected_value", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(length=36), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "field_name IN ('post_date','entry_date','entry_time','exit_date','exit_time',"
            "'agency_raw','entry_location','entry_lane','exit_location','exit_lane',"
            "'transponder_number','plate_number','trip_charge')",
            name="ck_toll_pdf_review_field_corrections_field_name",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_row_id"],
            ["toll_pdf_review_rows.tenant_id", "toll_pdf_review_rows.id"],
            name="fk_toll_pdf_review_field_corrections_row_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_toll_pdf_review_field_corrections_tenant_id_id"),
    )
    op.create_index(
        "ix_toll_pdf_review_field_corrections_tenant_id",
        "toll_pdf_review_field_corrections",
        ["tenant_id"],
    )
    op.create_index(
        "ix_toll_pdf_review_field_corrections_tenant_row_field",
        "toll_pdf_review_field_corrections",
        ["tenant_id", "review_row_id", "field_name", "id"],
    )

    op.add_column("toll_transactions", sa.Column("pdf_review_row_id", sa.Integer(), nullable=True))
    op.add_column("toll_transactions", sa.Column("manual_stage_id", sa.Integer(), nullable=True))
    op.add_column(
        "toll_transactions",
        sa.Column("accepted_effective_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("toll_transactions", sa.Column("post_date", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_toll_transactions_accepted_effective_object",
        "toll_transactions",
        "accepted_effective_json IS NULL OR jsonb_typeof(accepted_effective_json) = 'object'",
    )
    op.create_foreign_key(
        "fk_toll_transactions_pdf_review_row_tenant",
        "toll_transactions",
        "toll_pdf_review_rows",
        ["tenant_id", "pdf_review_row_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_toll_transactions_manual_stage_tenant",
        "toll_transactions",
        "toll_manual_entry_stages",
        ["tenant_id", "manual_stage_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_toll_transactions_tenant_pdf_review_row",
        "toll_transactions",
        ["tenant_id", "pdf_review_row_id"],
    )
    op.create_unique_constraint(
        "uq_toll_transactions_tenant_manual_stage",
        "toll_transactions",
        ["tenant_id", "manual_stage_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_toll_transactions_tenant_manual_stage", "toll_transactions", type_="unique")
    op.drop_constraint("uq_toll_transactions_tenant_pdf_review_row", "toll_transactions", type_="unique")
    op.drop_constraint("fk_toll_transactions_manual_stage_tenant", "toll_transactions", type_="foreignkey")
    op.drop_constraint("fk_toll_transactions_pdf_review_row_tenant", "toll_transactions", type_="foreignkey")
    op.drop_constraint("ck_toll_transactions_accepted_effective_object", "toll_transactions", type_="check")
    op.drop_column("toll_transactions", "post_date")
    op.drop_column("toll_transactions", "accepted_effective_json")
    op.drop_column("toll_transactions", "manual_stage_id")
    op.drop_column("toll_transactions", "pdf_review_row_id")
    op.drop_index(
        "ix_toll_pdf_review_field_corrections_tenant_row_field",
        table_name="toll_pdf_review_field_corrections",
    )
    op.drop_index(
        "ix_toll_pdf_review_field_corrections_tenant_id",
        table_name="toll_pdf_review_field_corrections",
    )
    op.drop_table("toll_pdf_review_field_corrections")
    op.drop_constraint("ck_toll_manual_entry_stages_status", "toll_manual_entry_stages", type_="check")
    op.create_check_constraint(
        "ck_toll_manual_entry_stages_status",
        "toll_manual_entry_stages",
        "status IN ('DRAFT', 'NEEDS_REVIEW', 'DISCARDED')",
    )
    op.drop_constraint("ck_toll_pdf_statement_review_status", "toll_pdf_statement_review", type_="check")
    op.create_check_constraint(
        "ck_toll_pdf_statement_review_status",
        "toll_pdf_statement_review",
        "review_status IN ('NEEDS_REVIEW', 'RECONCILIATION_FAILED')",
    )
