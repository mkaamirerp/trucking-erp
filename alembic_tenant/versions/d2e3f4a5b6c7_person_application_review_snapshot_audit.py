"""person_applications: submitted intake snapshot + admin review audit trail.

Revision ID: d2e3f4a5b6c7
Revises: c9f8e7d6b5a4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "d2e3f4a5b6c7"
down_revision = "c9f8e7d6b5a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("person_applications"):
        return
    cols = {c["name"] for c in insp.get_columns("person_applications")}
    if "intake_submitted_snapshot" not in cols:
        op.add_column(
            "person_applications",
            sa.Column("intake_submitted_snapshot", JSONB(), nullable=True),
        )
    if "intake_review_audit" not in cols:
        op.add_column(
            "person_applications",
            sa.Column(
                "intake_review_audit",
                JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("person_applications"):
        return
    cols = {c["name"] for c in insp.get_columns("person_applications")}
    if "intake_review_audit" in cols:
        op.drop_column("person_applications", "intake_review_audit")
    if "intake_submitted_snapshot" in cols:
        op.drop_column("person_applications", "intake_submitted_snapshot")
