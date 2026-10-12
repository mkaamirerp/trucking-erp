"""DW-1: PG15 column-specific ON DELETE SET NULL for composite tenant FKs.

Composite FK ON DELETE SET NULL without a column list would null all FK columns,
including NOT NULL tenant_id. PostgreSQL 15+ supports ON DELETE SET NULL (col).

Revision ID: dw1c_composite_fk_set_null_optional_columns
Revises: dw1b_tenant_scope_dw1_foreign_keys
Create Date: 2026-10-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "dw1c_composite_fk_set_null_optional_columns"
down_revision: Union[str, Sequence[str], None] = "dw1b_tenant_scope_dw1_foreign_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _replace_set_null_fk(
    table: str,
    constraint: str,
    local_cols: str,
    ref_table: str,
    ref_cols: str,
    null_col: str,
) -> None:
    op.drop_constraint(constraint, table, type_="foreignkey")
    op.execute(
        f"""
        ALTER TABLE {table}
        ADD CONSTRAINT {constraint}
        FOREIGN KEY ({local_cols})
        REFERENCES {ref_table} ({ref_cols})
        ON DELETE SET NULL ({null_col})
        """
    )


def upgrade() -> None:
    _replace_set_null_fk(
        "load_workspace_drafts",
        "fk_load_workspace_drafts_email_thread_tenant",
        "tenant_id, email_thread_id",
        "email_threads",
        "tenant_id, id",
        "email_thread_id",
    )
    _replace_set_null_fk(
        "email_threads",
        "fk_email_threads_workspace_draft_tenant",
        "tenant_id, workspace_draft_id",
        "load_workspace_drafts",
        "tenant_id, id",
        "workspace_draft_id",
    )
    _replace_set_null_fk(
        "email_intake_qr_extractions",
        "fk_email_intake_qr_extractions_workspace_draft_tenant",
        "tenant_id, workspace_draft_id",
        "load_workspace_drafts",
        "tenant_id, id",
        "workspace_draft_id",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_email_intake_qr_extractions_workspace_draft_tenant",
        "email_intake_qr_extractions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_email_intake_qr_extractions_workspace_draft_tenant",
        "email_intake_qr_extractions",
        "load_workspace_drafts",
        ["tenant_id", "workspace_draft_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "fk_email_threads_workspace_draft_tenant",
        "email_threads",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_email_threads_workspace_draft_tenant",
        "email_threads",
        "load_workspace_drafts",
        ["tenant_id", "workspace_draft_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "fk_load_workspace_drafts_email_thread_tenant",
        "load_workspace_drafts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_load_workspace_drafts_email_thread_tenant",
        "load_workspace_drafts",
        "email_threads",
        ["tenant_id", "email_thread_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )
