"""Rename credential_ref_id to credential_ref in tenant_email_mailboxes.

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-03-23

credential_ref is an opaque string ref, not a numeric ID.
"""

from __future__ import annotations

from alembic import op

revision = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tenant_email_mailboxes",
        "credential_ref_id",
        new_column_name="credential_ref",
    )


def downgrade() -> None:
    op.alter_column(
        "tenant_email_mailboxes",
        "credential_ref",
        new_column_name="credential_ref_id",
    )
