"""Idempotent: driver_profiles + drivers composite FK; person_roles index (ensure final state)

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-02-23

Ensures same final state as f2b3c4d5e6f7 without editing that revision.
Use when f2b3c4d5e6f7 may already be applied (tenant_demo) or when constraint names differ.
- Drops/creates only if needed (catalog checks).
- Hard-fails if cross-tenant violations exist before adding composite FKs.

Forward-only: Downgrade is not supported. People-first model enforces composite uniqueness
(tenant_id, id) on people; people.id may not be globally UNIQUE, so recreating single-column
FK -> people(id) would fail. Use backup/restore if rollback is required.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def _constraint_exists(table: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    r = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = current_schema()
              AND t.relname = :table
              AND c.conname = :cname
            LIMIT 1
            """
        ),
        {"table": table, "cname": constraint_name},
    )
    return r.scalar() is not None


def _index_exists(index_name: str) -> bool:
    bind = op.get_bind()
    r = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relkind = 'i'
              AND c.relname = :iname
            LIMIT 1
            """
        ),
        {"iname": index_name},
    )
    return r.scalar() is not None


def _assert_no_cross_tenant_violations() -> None:
    bind = op.get_bind()

    r = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM driver_profiles dp
            JOIN people p
              ON p.id = dp.person_id
            WHERE dp.person_id IS NOT NULL
              AND dp.tenant_id <> p.tenant_id
            """
        )
    )
    dp_bad = r.scalar() or 0

    r = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM drivers d
            JOIN people p
              ON p.id = d.person_id
            WHERE d.person_id IS NOT NULL
              AND d.tenant_id <> p.tenant_id
            """
        )
    )
    d_bad = r.scalar() or 0

    if dp_bad or d_bad:
        raise RuntimeError(
            "Composite tenant FK hardening blocked: cross-tenant person_id links exist. "
            f"driver_profiles violations={dp_bad}, drivers violations={d_bad}. "
            "Clean/NULL these rows before applying this migration."
        )


def upgrade() -> None:
    _assert_no_cross_tenant_violations()

    # 1) driver_profiles: drop single-column FK, add composite FK
    old_dp_fk = "driver_profiles_person_id_fkey"
    new_dp_fk = "fk_driver_profiles_tenant_person_to_people"

    if _constraint_exists("driver_profiles", old_dp_fk):
        op.drop_constraint(old_dp_fk, "driver_profiles", type_="foreignkey")

    if not _constraint_exists("driver_profiles", new_dp_fk):
        op.create_foreign_key(
            new_dp_fk,
            "driver_profiles",
            "people",
            ["tenant_id", "person_id"],
            ["tenant_id", "id"],
            ondelete="CASCADE",
        )

    # 2) drivers (legacy): drop single-column FK, add composite FK
    old_d_fk = "fk_drivers_person_id_people"
    new_d_fk = "fk_drivers_tenant_person_to_people"

    if _constraint_exists("drivers", old_d_fk):
        op.drop_constraint(old_d_fk, "drivers", type_="foreignkey")

    if not _constraint_exists("drivers", new_d_fk):
        op.create_foreign_key(
            new_d_fk,
            "drivers",
            "people",
            ["tenant_id", "person_id"],
            ["tenant_id", "id"],
            ondelete="SET NULL",
        )

    # 3) person_roles: index for composite FK checks + joins
    ix = "ix_person_roles_tenant_person_id"
    if not _index_exists(ix):
        op.create_index(ix, "person_roles", ["tenant_id", "person_id"], unique=False)


def downgrade() -> None:
    raise RuntimeError(
        "Revision c6d7e8f9a0b1 is forward-only for tenant safety hardening. "
        "People-first model uses composite UNIQUE(tenant_id, id) on people; people.id is not "
        "guaranteed globally unique, so single-column FK -> people(id) cannot be recreated. "
        "To roll back, restore the tenant DB from a pre-migration backup."
    )
