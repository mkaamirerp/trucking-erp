"""Add requested_role_code to person_applications.

requested_role_code = role assigned on approval (person_roles.role_code).
Kept separate from application_type (form track). For MVP backfill: same as application_type.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "person_applications",
        sa.Column("requested_role_code", sa.String(50), nullable=True),
    )
    op.execute(
        sa.text("UPDATE person_applications SET requested_role_code = COALESCE(application_type, 'DRIVER')")
    )
    op.alter_column(
        "person_applications",
        "requested_role_code",
        existing_type=sa.String(50),
        nullable=False,
        server_default="DRIVER",
    )


def downgrade() -> None:
    op.drop_column("person_applications", "requested_role_code")
