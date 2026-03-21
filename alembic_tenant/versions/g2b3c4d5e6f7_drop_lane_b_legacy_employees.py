"""Drop Lane B legacy tables (employee_roles, employees_legacy_*)

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-15

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "g2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Drop FK from employee_roles to employees_legacy_* (if table exists)
    if insp.has_table("employee_roles"):
        for fk in insp.get_foreign_keys("employee_roles"):
            ref = fk.get("referred_table") or ""
            if ref.startswith("employees_legacy_"):
                op.drop_constraint(fk["name"], "employee_roles", type_="foreignkey")
                break

    # 2. Drop employee_roles
    op.execute(sa.text("DROP TABLE IF EXISTS employee_roles CASCADE"))

    # 3. Drop all employees_legacy_* tables (dynamic date suffix per tenant)
    result = bind.execute(
        sa.text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename LIKE 'employees_legacy_%'"
        )
    )
    for (tablename,) in result:
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{tablename}" CASCADE'))


def downgrade() -> None:
    pass
