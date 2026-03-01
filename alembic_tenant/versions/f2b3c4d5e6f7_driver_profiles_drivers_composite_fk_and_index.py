"""driver_profiles + drivers composite FK; person_roles (tenant_id, person_id) index

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-02-23

Same invariant as person_roles: (tenant_id, person_id) -> people(tenant_id, id)
so cross-tenant leakage is a DB constraint violation. Also add btree index on
person_roles(tenant_id, person_id) for composite FK check performance.
"""

from alembic import op

revision = "f2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. driver_profiles: drop single-column FK, add composite FK
    op.drop_constraint(
        "driver_profiles_person_id_fkey",
        "driver_profiles",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_driver_profiles_tenant_person_to_people",
        "driver_profiles",
        "people",
        ["tenant_id", "person_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )

    # 2. drivers (legacy): drop single-column FK, add composite FK
    op.drop_constraint(
        "fk_drivers_person_id_people",
        "drivers",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_drivers_tenant_person_to_people",
        "drivers",
        "people",
        ["tenant_id", "person_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )

    # 3. person_roles: index for composite FK checks (Postgres doesn't auto-create)
    op.create_index(
        "ix_person_roles_tenant_person_id",
        "person_roles",
        ["tenant_id", "person_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_person_roles_tenant_person_id",
        table_name="person_roles",
    )

    op.drop_constraint(
        "fk_drivers_tenant_person_to_people",
        "drivers",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_drivers_person_id_people",
        "drivers",
        "people",
        ["person_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "fk_driver_profiles_tenant_person_to_people",
        "driver_profiles",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "driver_profiles_person_id_fkey",
        "driver_profiles",
        "people",
        ["person_id"],
        ["id"],
        ondelete="CASCADE",
    )
