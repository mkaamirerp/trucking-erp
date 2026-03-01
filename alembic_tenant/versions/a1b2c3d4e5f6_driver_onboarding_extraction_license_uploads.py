"""Add extraction_status, extraction_result_json, license_uploads_json for DL extraction and license uploads.

Revision ID: a1b2c3d4e5f6
Revises: f9a0b1c2d3e4
Create Date: 2026-02-24

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "driver_onboarding_submissions",
        sa.Column("extraction_status", sa.String(32), nullable=True),
        schema="public",
    )
    op.add_column(
        "driver_onboarding_submissions",
        sa.Column("extraction_result_json", sa.Text(), nullable=True),
        schema="public",
    )
    op.add_column(
        "driver_onboarding_submissions",
        sa.Column("license_uploads_json", sa.Text(), nullable=True),
        schema="public",
    )
    op.add_column(
        "driver_onboarding_submissions",
        sa.Column("middle_name", sa.Text(), nullable=True),
        schema="public",
    )
    # Allow draft submissions created from upload-first (no name yet)
    op.alter_column(
        "driver_onboarding_submissions",
        "first_name",
        existing_type=sa.Text(),
        nullable=True,
        schema="public",
    )
    op.alter_column(
        "driver_onboarding_submissions",
        "last_name",
        existing_type=sa.Text(),
        nullable=True,
        schema="public",
    )


def downgrade() -> None:
    op.alter_column(
        "driver_onboarding_submissions",
        "last_name",
        existing_type=sa.Text(),
        nullable=False,
        schema="public",
    )
    op.alter_column(
        "driver_onboarding_submissions",
        "first_name",
        existing_type=sa.Text(),
        nullable=False,
        schema="public",
    )
    op.drop_column("driver_onboarding_submissions", "middle_name", schema="public")
    op.drop_column("driver_onboarding_submissions", "license_uploads_json", schema="public")
    op.drop_column("driver_onboarding_submissions", "extraction_result_json", schema="public")
    op.drop_column("driver_onboarding_submissions", "extraction_status", schema="public")
