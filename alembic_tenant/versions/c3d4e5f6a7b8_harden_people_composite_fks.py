"""Harden people-related tenant FKs to composite references.

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-03-12

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def _constraint_exists(conn: sa.Connection, table: str, constraint_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                select 1
                from pg_constraint
                where conrelid = (:table_name)::regclass
                  and conname = :constraint_name
                """
            ),
            {"table_name": f"public.{table}", "constraint_name": constraint_name},
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names(schema="public"))
    required_tables = {"people", "person_roles", "driver_profiles", "drivers"}
    if not required_tables.issubset(tables):
        return

    if not _constraint_exists(conn, "people", "uq_people_tenant_id_id"):
        op.create_unique_constraint(
            "uq_people_tenant_id_id",
            "people",
            ["tenant_id", "id"],
            schema="public",
        )

    if _constraint_exists(conn, "person_roles", "person_roles_person_id_fkey"):
        op.drop_constraint("person_roles_person_id_fkey", "person_roles", type_="foreignkey", schema="public")
    if not _constraint_exists(conn, "person_roles", "fk_person_roles_tenant_person_to_people"):
        op.create_foreign_key(
            "fk_person_roles_tenant_person_to_people",
            "person_roles",
            "people",
            ["tenant_id", "person_id"],
            ["tenant_id", "id"],
            source_schema="public",
            referent_schema="public",
            ondelete="CASCADE",
        )

    if _constraint_exists(conn, "driver_profiles", "driver_profiles_person_id_fkey"):
        op.drop_constraint("driver_profiles_person_id_fkey", "driver_profiles", type_="foreignkey", schema="public")
    if not _constraint_exists(conn, "driver_profiles", "fk_driver_profiles_tenant_person_to_people"):
        op.create_foreign_key(
            "fk_driver_profiles_tenant_person_to_people",
            "driver_profiles",
            "people",
            ["tenant_id", "person_id"],
            ["tenant_id", "id"],
            source_schema="public",
            referent_schema="public",
            ondelete="CASCADE",
        )

    if _constraint_exists(conn, "drivers", "fk_drivers_person_id_people"):
        op.drop_constraint("fk_drivers_person_id_people", "drivers", type_="foreignkey", schema="public")
    if not _constraint_exists(conn, "drivers", "fk_drivers_tenant_person_to_people"):
        op.execute(
            """
            ALTER TABLE public.drivers
            ADD CONSTRAINT fk_drivers_tenant_person_to_people
            FOREIGN KEY (tenant_id, person_id)
            REFERENCES public.people (tenant_id, id)
            ON DELETE SET NULL (person_id)
            """
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names(schema="public"))
    required_tables = {"people", "person_roles", "driver_profiles", "drivers"}
    if not required_tables.issubset(tables):
        return

    if _constraint_exists(conn, "drivers", "fk_drivers_tenant_person_to_people"):
        op.drop_constraint("fk_drivers_tenant_person_to_people", "drivers", type_="foreignkey", schema="public")
    if not _constraint_exists(conn, "drivers", "fk_drivers_person_id_people"):
        op.create_foreign_key(
            "fk_drivers_person_id_people",
            "drivers",
            "people",
            ["person_id"],
            ["id"],
            source_schema="public",
            referent_schema="public",
            ondelete="SET NULL",
        )

    if _constraint_exists(conn, "driver_profiles", "fk_driver_profiles_tenant_person_to_people"):
        op.drop_constraint("fk_driver_profiles_tenant_person_to_people", "driver_profiles", type_="foreignkey", schema="public")
    if not _constraint_exists(conn, "driver_profiles", "driver_profiles_person_id_fkey"):
        op.create_foreign_key(
            "driver_profiles_person_id_fkey",
            "driver_profiles",
            "people",
            ["person_id"],
            ["id"],
            source_schema="public",
            referent_schema="public",
            ondelete="CASCADE",
        )

    if _constraint_exists(conn, "person_roles", "fk_person_roles_tenant_person_to_people"):
        op.drop_constraint("fk_person_roles_tenant_person_to_people", "person_roles", type_="foreignkey", schema="public")
    if not _constraint_exists(conn, "person_roles", "person_roles_person_id_fkey"):
        op.create_foreign_key(
            "person_roles_person_id_fkey",
            "person_roles",
            "people",
            ["person_id"],
            ["id"],
            source_schema="public",
            referent_schema="public",
            ondelete="CASCADE",
        )

    if _constraint_exists(conn, "people", "uq_people_tenant_id_id"):
        op.drop_constraint("uq_people_tenant_id_id", "people", type_="unique", schema="public")
