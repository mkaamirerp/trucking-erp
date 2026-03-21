"""people foundation (people, roles, driver_profiles)

Revision ID: ea59a17db8a3
Revises: 74ff8253c43c
Create Date: 2026-02-16 17:30:28.558971

Idempotent: creates people, person_roles, driver_profiles if missing; adds drivers.person_id bridge.
Downgrade: best-effort, safe (existence checks, DROP INDEX IF EXISTS).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ea59a17db8a3'
down_revision = '74ff8253c43c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names(schema="public"))

    # ---- people ----
    if "people" not in tables:
        op.create_table(
            "people",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("first_name", sa.String(100), nullable=False),
            sa.Column("last_name", sa.String(100), nullable=False),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("phone", sa.String(50), nullable=True),
            sa.Column("street_address", sa.String(255), nullable=True),
            sa.Column("city", sa.String(120), nullable=True),
            sa.Column("region", sa.String(120), nullable=True),
            sa.Column("postal_code", sa.String(30), nullable=True),
            sa.Column("country", sa.String(2), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            schema="public",
        )
        op.create_index("ix_people_tenant_id", "people", ["tenant_id"], unique=False, schema="public")
        op.create_index("ix_people_tenant_id_email", "people", ["tenant_id", "email"], unique=False, schema="public")

    tables = set(inspector.get_table_names(schema="public"))

    # ---- person_roles ----
    if "person_roles" not in tables:
        op.create_table(
            "person_roles",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("person_id", sa.BigInteger(), nullable=False),
            sa.Column("role_code", sa.String(50), nullable=False),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["person_id"], ["people.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("tenant_id", "person_id", "role_code", "is_active", name="uq_person_roles_tenant_person_role_active"),
            schema="public",
        )
        op.create_index("ix_person_roles_tenant_id", "person_roles", ["tenant_id"], unique=False, schema="public")
        op.create_index("ix_person_roles_person_id", "person_roles", ["person_id"], unique=False, schema="public")

    tables = set(inspector.get_table_names(schema="public"))

    # ---- driver_profiles ----
    if "driver_profiles" not in tables:
        op.create_table(
            "driver_profiles",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("person_id", sa.BigInteger(), nullable=False),
            sa.Column("license_number", sa.String(100), nullable=True),
            sa.Column("license_region", sa.String(120), nullable=True),
            sa.Column("license_expiry", sa.Date(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["person_id"], ["people.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("person_id", name="uq_driver_profiles_person_id"),
            schema="public",
        )
        op.create_index("ix_driver_profiles_tenant_id", "driver_profiles", ["tenant_id"], unique=False, schema="public")
        op.create_index("ix_driver_profiles_person_id", "driver_profiles", ["person_id"], unique=False, schema="public")

    # ---- drivers.person_id (bridge for later backfill) ----
    if "drivers" in inspector.get_table_names(schema="public"):
        existing_columns = {c["name"] for c in inspector.get_columns("drivers", schema="public")}
        if "person_id" not in existing_columns:
            op.add_column("drivers", sa.Column("person_id", sa.BigInteger(), nullable=True), schema="public")
            op.create_index("ix_drivers_person_id", "drivers", ["person_id"], unique=False, schema="public")
            op.create_foreign_key(
                "fk_drivers_person_id_people",
                "drivers",
                "people",
                ["person_id"],
                ["id"],
                ondelete="SET NULL",
                source_schema="public",
                referent_schema="public",
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names(schema="public"))

    # ---- Remove drivers.person_id (FK, index, column) ----
    if "drivers" in tables:
        cols = {c["name"] for c in inspector.get_columns("drivers", schema="public")}
        if "person_id" in cols:
            # Drop FK if exists
            fks = [
                fk["name"]
                for fk in inspector.get_foreign_keys("drivers", schema="public")
                if fk.get("constrained_columns") == ["person_id"]
            ]
            for fk_name in fks:
                op.drop_constraint(fk_name, "drivers", type_="foreignkey", schema="public")

            # Drop index using safe DROP INDEX IF EXISTS
            op.execute("DROP INDEX IF EXISTS public.ix_drivers_person_id")

            # Drop column
            op.drop_column("drivers", "person_id", schema="public")

    # ---- Drop tables (reverse order: driver_profiles, person_roles, people) ----
    tables = set(inspector.get_table_names(schema="public"))
    if "driver_profiles" in tables:
        op.execute("DROP INDEX IF EXISTS public.ix_driver_profiles_person_id")
        op.execute("DROP INDEX IF EXISTS public.ix_driver_profiles_tenant_id")
        op.drop_table("driver_profiles", schema="public")

    tables = set(inspector.get_table_names(schema="public"))
    if "person_roles" in tables:
        op.execute("DROP INDEX IF EXISTS public.ix_person_roles_person_id")
        op.execute("DROP INDEX IF EXISTS public.ix_person_roles_tenant_id")
        op.drop_table("person_roles", schema="public")

    tables = set(inspector.get_table_names(schema="public"))
    if "people" in tables:
        op.execute("DROP INDEX IF EXISTS public.ix_people_tenant_id_email")
        op.execute("DROP INDEX IF EXISTS public.ix_people_tenant_id")
        op.drop_table("people", schema="public")
