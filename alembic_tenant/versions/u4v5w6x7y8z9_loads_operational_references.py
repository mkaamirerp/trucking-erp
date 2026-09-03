"""Add loads.operational_references JSONB collection.

Revision ID: u4v5w6x7y8z9
Revises: f9a0b1c2d3e5
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "u4v5w6x7y8z9"
down_revision = "f9a0b1c2d3e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "loads",
        sa.Column(
            "operational_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_loads_operational_references_is_array",
        "loads",
        "jsonb_typeof(operational_references) = 'array'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_loads_operational_references_is_array", "loads", type_="check")
    op.drop_column("loads", "operational_references")
