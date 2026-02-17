"""Drop tenant_id FKs from people, person_roles, driver_profiles (no cross-DB coupling)

Revision ID: f01a9b2c3d4e
Revises: ea59a17db8a3
Create Date: 2026-02-16

Removes FK constraints from tenant_id to tenants(id) in tenant DB.
Keeps tenant_id columns (INTEGER NOT NULL). Keeps all other FKs (person_id, etc.).
Idempotent: drops only if constraint exists. Downgrade: best-effort recreate FKs.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f01a9b2c3d4e"
down_revision = "ea59a17db8a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names(schema="public"))

    def drop_tenant_id_fk(table: str) -> None:
        if table not in tables:
            return
        for fk in inspector.get_foreign_keys(table, schema="public"):
            if fk.get("referred_table") == "tenants" and fk.get("constrained_columns") == ["tenant_id"]:
                name = fk.get("name")
                if name:
                    op.drop_constraint(name, table, type_="foreignkey", schema="public")
                return

    drop_tenant_id_fk("people")
    drop_tenant_id_fk("person_roles")
    drop_tenant_id_fk("driver_profiles")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names(schema="public"))

    def add_tenant_id_fk_if_missing(table: str) -> None:
        if table not in tables:
            return
        fks = inspector.get_foreign_keys(table, schema="public")
        has_tenant_fk = any(
            fk.get("referred_table") == "tenants" and fk.get("constrained_columns") == ["tenant_id"]
            for fk in fks
        )
        if not has_tenant_fk:
            op.create_foreign_key(
                f"{table}_tenant_id_fkey",
                table,
                "tenants",
                ["tenant_id"],
                ["id"],
                ondelete="CASCADE",
                source_schema="public",
                referent_schema="public",
            )

    add_tenant_id_fk_if_missing("driver_profiles")
    add_tenant_id_fk_if_missing("person_roles")
    add_tenant_id_fk_if_missing("people")
