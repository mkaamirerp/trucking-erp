"""Merge tenant heads: driver license + payroll

Revision ID: t001_merge_heads_driver_license_payroll
Revises: 2f3c3c4a0b1a, a12c8f7f2c2d
Create Date: 2026-01-04
"""

from alembic import op


revision = "t001_merge_heads_driver_license_payroll"
down_revision = ("2f3c3c4a0b1a", "a12c8f7f2c2d")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
