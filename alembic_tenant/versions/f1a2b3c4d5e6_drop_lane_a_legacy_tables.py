"""Drop Lane A legacy tables (users, user_roles, driver_phones_old)

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-03-15

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Drop audit_log FK to users (must precede users drop)
    if insp.has_table("audit_log"):
        for fk in insp.get_foreign_keys("audit_log"):
            if fk.get("referred_table") == "users":
                op.drop_constraint(fk["name"], "audit_log", type_="foreignkey")
                break

    # 2. Drop tables (order: user_roles first, then users; driver_phones_old independent)
    op.execute(sa.text("DROP TABLE IF EXISTS user_roles CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS users CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS driver_phones_old CASCADE"))


def downgrade() -> None:
    # No downgrade — these tables are legacy; do not recreate
    pass
