"""People foundation: people, person_roles, driver_profiles + drivers.person_id + backfill

Revision ID: 74ff8253c43c
Revises: fefd8f1df8d9
Create Date: 2026-02-16

Tenant-safe, idempotent: table/column existence checks, backfill only where person_id IS NULL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "74ff8253c43c"
down_revision: Union[str, Sequence[str], None] = "fefd8f1df8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names(schema="public"))

    # ---- Create people ----
    if "people" not in tables:
        op.create_table(
            "people",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("onboarding_status", sa.String(20), nullable=False, server_default=sa.text("'DRAFT'")),
            sa.Column("first_name", sa.String(100), nullable=False),
            sa.Column("last_name", sa.String(100), nullable=False),
            sa.Column("phone", sa.String(50), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("street_address", sa.Text(), nullable=True),
            sa.Column("city", sa.String(100), nullable=True),
            sa.Column("region", sa.String(100), nullable=True),
            sa.Column("postal_code", sa.String(20), nullable=True),
            sa.Column("country", sa.String(10), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            schema="public",
        )
        op.create_index("ix_people_tenant_id", "people", ["tenant_id"], unique=False, schema="public")
        op.create_index("ix_people_tenant_onboarding_status", "people", ["tenant_id", "onboarding_status"], unique=False, schema="public")

    tables = set(inspector.get_table_names(schema="public"))

    # ---- Create person_roles ----
    if "person_roles" not in tables:
        op.create_table(
            "person_roles",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("person_id", sa.BigInteger(), sa.ForeignKey("people.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role_code", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            schema="public",
        )
        op.create_index("ix_person_roles_tenant_id", "person_roles", ["tenant_id"], unique=False, schema="public")
        op.create_index("ix_person_roles_person_id", "person_roles", ["person_id"], unique=False, schema="public")

    tables = set(inspector.get_table_names(schema="public"))

    # ---- Create driver_profiles ----
    if "driver_profiles" not in tables:
        op.create_table(
            "driver_profiles",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("person_id", sa.BigInteger(), sa.ForeignKey("people.id", ondelete="CASCADE"), nullable=False),
            sa.Column("license_number", sa.String(100), nullable=True),
            sa.Column("license_region", sa.String(100), nullable=True),
            sa.Column("license_expiry", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            schema="public",
        )
        op.create_index("ix_driver_profiles_tenant_id", "driver_profiles", ["tenant_id"], unique=False, schema="public")
        op.create_index("ix_driver_profiles_person_id", "driver_profiles", ["person_id"], unique=True, schema="public")

    # ---- Add drivers.person_id if missing ----
    if "drivers" not in inspector.get_table_names(schema="public"):
        return

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

    # ---- Idempotent backfill: drivers with person_id IS NULL ----
    # Use raw SQL so we can INSERT ... RETURNING and avoid loading all into Python
    conn = op.get_bind()
    result = conn.execute(text("SELECT id, tenant_id, first_name, last_name, phone, email FROM drivers WHERE person_id IS NULL"))
    rows = result.fetchall()
    result.close()

    for row in rows:
        driver_id, tenant_id, first_name, last_name, phone, email = row
        first_name = first_name or ""
        last_name = last_name or ""

        r = conn.execute(
            text("""
                INSERT INTO people (tenant_id, onboarding_status, first_name, last_name, phone, email, created_at, updated_at)
                VALUES (:tenant_id, 'APPROVED', :first_name, :last_name, :phone, :email, now(), now())
                RETURNING id
            """),
            {"tenant_id": tenant_id, "first_name": first_name, "last_name": last_name, "phone": phone, "email": email},
        )
        person_id = r.scalar_one()
        r.close()

        conn.execute(text("UPDATE drivers SET person_id = :pid WHERE id = :did"), {"pid": person_id, "did": driver_id})

        # driver_profiles: one per person (idempotent: check if exists)
        r = conn.execute(text("SELECT 1 FROM driver_profiles WHERE person_id = :pid"), {"pid": person_id})
        if r.fetchone() is None:
            conn.execute(
                text("""
                    INSERT INTO driver_profiles (tenant_id, person_id, created_at, updated_at)
                    VALUES (:tenant_id, :person_id, now(), now())
                """),
                {"tenant_id": tenant_id, "person_id": person_id},
            )
        r.close()

        # person_roles: DRIVER role if missing
        r = conn.execute(
            text("SELECT 1 FROM person_roles WHERE person_id = :pid AND role_code = 'DRIVER'"),
            {"pid": person_id},
        )
        if r.fetchone() is None:
            conn.execute(
                text("""
                    INSERT INTO person_roles (tenant_id, person_id, role_code, is_active, created_at)
                    VALUES (:tenant_id, :person_id, 'DRIVER', true, now())
                """),
                {"tenant_id": tenant_id, "person_id": person_id},
            )
        r.close()


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names(schema="public"))

    # ---- Best-effort: remove drivers.person_id ----
    if "drivers" in tables:
        cols = {c["name"] for c in inspector.get_columns("drivers", schema="public")}
        if "person_id" in cols:
            fks = [fk["name"] for fk in inspector.get_foreign_keys("drivers", schema="public") if fk.get("constrained_columns") == ["person_id"]]
            for fk_name in fks:
                op.drop_constraint(fk_name, "drivers", type_="foreignkey", schema="public")
            indexes = {i["name"] for i in inspector.get_indexes("drivers", schema="public")}
            if "ix_drivers_person_id" in indexes:
                op.drop_index("ix_drivers_person_id", table_name="drivers", schema="public")
            op.drop_column("drivers", "person_id", schema="public")

    # ---- Best-effort: drop people-related tables (reverse order) ----
    if "driver_profiles" in tables:
        op.drop_index("ix_driver_profiles_person_id", table_name="driver_profiles", schema="public")
        op.drop_index("ix_driver_profiles_tenant_id", table_name="driver_profiles", schema="public")
        op.drop_table("driver_profiles", schema="public")
    tables = set(inspector.get_table_names(schema="public"))
    if "person_roles" in tables:
        op.drop_index("ix_person_roles_person_id", table_name="person_roles", schema="public")
        op.drop_index("ix_person_roles_tenant_id", table_name="person_roles", schema="public")
        op.drop_table("person_roles", schema="public")
    tables = set(inspector.get_table_names(schema="public"))
    if "people" in tables:
        op.drop_index("ix_people_tenant_onboarding_status", table_name="people", schema="public")
        op.drop_index("ix_people_tenant_id", table_name="people", schema="public")
        op.drop_table("people", schema="public")
