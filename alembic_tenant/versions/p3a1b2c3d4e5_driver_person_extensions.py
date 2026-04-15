"""Phase 3A: driver_person_extensions (tenant-scoped person-centered extension).

Revision ID: p3a1b2c3d4e5
Revises: g0a1b2c3d4e5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p3a1b2c3d4e5"
down_revision = "g0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "driver_person_extensions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.BigInteger(), nullable=False),
        sa.Column("employment_relationship_type", sa.String(length=50), nullable=False),
        sa.Column("driver_operating_subtype", sa.String(length=50), nullable=False),
        sa.Column("is_team_driver", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("team_role_type", sa.String(length=50), nullable=True),
        sa.Column("provides_own_truck", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("provides_own_trailer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("equipment_contribution_type", sa.String(length=50), nullable=False),
        sa.Column(
            "insurance_commercial_approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name="fk_driver_person_extensions_tenant_person_to_people",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "person_id",
            name="uq_driver_person_extensions_tenant_person",
        ),
    )
    op.create_index(
        "ix_driver_person_extensions_tenant_id",
        "driver_person_extensions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_driver_person_extensions_person_id",
        "driver_person_extensions",
        ["person_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_driver_person_extensions_person_id", table_name="driver_person_extensions")
    op.drop_index("ix_driver_person_extensions_tenant_id", table_name="driver_person_extensions")
    op.drop_table("driver_person_extensions")
