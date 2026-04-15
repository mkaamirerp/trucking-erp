"""compensation_profiles: fuel discount participation flag (onboarding slice).

Revision ID: c9f8e7d6b5a4
Revises: h2b3c4d5e6f7

Note: revision id must not collide with h3c4d5e6f7a8_drop_tenants_table (legacy).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9f8e7d6b5a4"
down_revision = "h2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add column only when payroll/compensation tables exist (slim tenant DBs may omit them)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("compensation_profiles"):
        return
    cols = {c["name"] for c in insp.get_columns("compensation_profiles")}
    if "participates_in_fuel_discount_program" in cols:
        return
    op.add_column(
        "compensation_profiles",
        sa.Column(
            "participates_in_fuel_discount_program",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("compensation_profiles"):
        return
    cols = {c["name"] for c in insp.get_columns("compensation_profiles")}
    if "participates_in_fuel_discount_program" not in cols:
        return
    op.drop_column("compensation_profiles", "participates_in_fuel_discount_program")
