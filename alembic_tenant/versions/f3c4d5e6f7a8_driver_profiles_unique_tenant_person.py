"""driver_profiles: unique on (tenant_id, person_id) instead of person_id

Revision ID: f3c4d5e6f7a8
Revises: f2b3c4d5e6f7
Create Date: 2026-02-23

Drop ix_driver_profiles_person_id (unique on person_id).
Create ux_driver_profiles_tenant_person_id UNIQUE on (tenant_id, person_id)
so one person per tenant has at most one driver_profile, enforced at DB level.
"""

from alembic import op

revision = "f3c4d5e6f7a8"
down_revision = "f2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_driver_profiles_person_id;")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_driver_profiles_tenant_person_id
        ON driver_profiles (tenant_id, person_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_driver_profiles_tenant_person_id;")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_driver_profiles_person_id
        ON driver_profiles (person_id);
        """
    )
