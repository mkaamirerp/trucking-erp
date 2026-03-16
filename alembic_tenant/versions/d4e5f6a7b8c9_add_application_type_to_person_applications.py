"""Add application_type to person_applications.

application_type = onboarding workflow / form track (DRIVER, DISPATCHER, HR, etc.).
Controls which form the applicant sees. For MVP also used as the role assigned on approval.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "person_applications",
        sa.Column("application_type", sa.String(50), nullable=False, server_default="DRIVER"),
    )
    op.create_index(
        "ix_person_applications_tenant_application_type",
        "person_applications",
        ["tenant_id", "application_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_person_applications_tenant_application_type", table_name="person_applications")
    op.drop_column("person_applications", "application_type")
