"""person_applications: add person_id link (idempotent, forward-only)

Revision ID: f8e353bbc2b9
Revises: a1b2c3d4e5f6
Create Date: 2026-02-25
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f8e353bbc2b9"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add person_id if missing
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'person_applications'
                  AND column_name = 'person_id'
            ) THEN
                ALTER TABLE public.person_applications
                ADD COLUMN person_id BIGINT;
            END IF;
        END $$;
        """
    )

    # 2) Add composite FK if missing
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public'
                  AND t.relname = 'person_applications'
                  AND c.conname = 'fk_person_applications_tenant_person_to_people'
            ) THEN
                ALTER TABLE public.person_applications
                ADD CONSTRAINT fk_person_applications_tenant_person_to_people
                FOREIGN KEY (tenant_id, person_id)
                REFERENCES public.people (tenant_id, id)
                ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )

    # 3) Add index if missing
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_person_applications_tenant_person_id
        ON public.person_applications (tenant_id, person_id);
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "This migration is forward-only for tenant safety. "
        "To roll back, restore the tenant DB from a backup."
    )
