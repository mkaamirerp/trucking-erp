"""DW-1 review: tenant-scoped composite FKs (cross-tenant hardening).

Revision ID: dw1b_tenant_scope_dw1_foreign_keys
Revises: dw1f2a3b4c5d6
Create Date: 2026-10-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "dw1b_tenant_scope_dw1_foreign_keys"
down_revision: Union[str, Sequence[str], None] = "dw1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_email_threads_tenant_id_id",
        "email_threads",
        ["tenant_id", "id"],
    )

    op.drop_constraint(
        "load_workspace_drafts_email_thread_id_fkey",
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

    op.drop_constraint(
        "fk_loads_promotion_origin_workspace_draft",
        "loads",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_loads_promotion_origin_workspace_draft_tenant",
        "loads",
        "load_workspace_drafts",
        ["tenant_id", "promotion_origin_workspace_draft_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_email_threads_workspace_draft",
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
        "fk_email_intake_qr_extractions_workspace_draft",
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


def downgrade() -> None:
    op.drop_constraint(
        "fk_email_intake_qr_extractions_workspace_draft_tenant",
        "email_intake_qr_extractions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_email_intake_qr_extractions_workspace_draft",
        "email_intake_qr_extractions",
        "load_workspace_drafts",
        ["workspace_draft_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "fk_email_threads_workspace_draft_tenant",
        "email_threads",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_email_threads_workspace_draft",
        "email_threads",
        "load_workspace_drafts",
        ["workspace_draft_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "fk_loads_promotion_origin_workspace_draft_tenant",
        "loads",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_loads_promotion_origin_workspace_draft",
        "loads",
        "load_workspace_drafts",
        ["promotion_origin_workspace_draft_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_load_workspace_drafts_email_thread_tenant",
        "load_workspace_drafts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "load_workspace_drafts_email_thread_id_fkey",
        "load_workspace_drafts",
        "email_threads",
        ["email_thread_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("uq_email_threads_tenant_id_id", "email_threads", type_="unique")
