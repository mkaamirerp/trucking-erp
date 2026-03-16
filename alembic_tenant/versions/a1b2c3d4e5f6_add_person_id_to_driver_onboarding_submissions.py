"""Add person_id to driver_onboarding_submissions (idempotent).

Revision ID: a1b2c3d4e5f6
Revises: f00a1b2c3d4e
Create Date: 2026-03-03

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f00a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "driver_onboarding_submissions" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("driver_onboarding_submissions")}
    if "person_id" in cols:
        return
    op.add_column(
        "driver_onboarding_submissions",
        sa.Column("person_id", sa.BigInteger(), nullable=True),
        schema="public",
    )
    op.create_index(
        "ix_driver_onboarding_submissions_person_id",
        "driver_onboarding_submissions",
        ["person_id"],
        unique=False,
        schema="public",
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "driver_onboarding_submissions" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("driver_onboarding_submissions")}
    if "person_id" not in cols:
        return
    op.drop_index(
        "ix_driver_onboarding_submissions_person_id",
        table_name="driver_onboarding_submissions",
        schema="public",
    )
    op.drop_column("driver_onboarding_submissions", "person_id", schema="public")
