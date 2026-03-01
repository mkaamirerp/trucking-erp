"""person_roles composite FK: (tenant_id, person_id) -> people(tenant_id, id)

Revision ID: f1a2b3c4d5e6
Revises: e8f9a0b1c2d3
Create Date: 2026-02-22 00:00:00.000000

Why: A single-column FK on person_id alone allows a row from tenant A to reference
a person_id that belongs to tenant B (if the numeric IDs happen to match).
The composite FK (tenant_id, person_id) -> people(tenant_id, id) enforces
cross-tenant isolation at the DB constraint level.
"""

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add unique constraint on people(tenant_id, id) so it can be the target
    #    of a composite FK reference.
    op.execute(
        """
        ALTER TABLE people
          ADD CONSTRAINT uq_people_tenant_id_id UNIQUE (tenant_id, id);
        """
    )

    # 2. Drop the existing single-column FK on person_roles.person_id -> people.id
    op.drop_constraint(
        "person_roles_person_id_fkey",
        "person_roles",
        type_="foreignkey",
    )

    # 3. Create composite FK: (tenant_id, person_id) -> people(tenant_id, id)
    op.create_foreign_key(
        "fk_person_roles_tenant_person_to_people",
        "person_roles",
        "people",
        ["tenant_id", "person_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Reverse: drop composite FK, recreate original single-column FK
    op.drop_constraint(
        "fk_person_roles_tenant_person_to_people",
        "person_roles",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "person_roles_person_id_fkey",
        "person_roles",
        "people",
        ["person_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.execute(
        """
        ALTER TABLE people
          DROP CONSTRAINT IF EXISTS uq_people_tenant_id_id;
        """
    )
