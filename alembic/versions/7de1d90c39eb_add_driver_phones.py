"""add driver phones (safe create)

Revision ID: 7de1d90c39eb
Revises: 55da366e2878
Create Date: 2025-12-24 07:19:42.127233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7de1d90c39eb"
down_revision: Union[str, Sequence[str], None] = "55da366e2878"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) If an old driver_phones table exists (from earlier experiments),
    #    rename it so we don't destroy columns/data unexpectedly.
    bind = op.get_bind()
    exists = bind.execute(sa.text("SELECT to_regclass('public.driver_phones')")).scalar()

    if exists:
        # rename only if backup name not already taken
        backup_exists = bind.execute(sa.text("SELECT to_regclass('public.driver_phones_old')")).scalar()
        if not backup_exists:
            op.execute("ALTER TABLE driver_phones RENAME TO driver_phones_old")
        else:
            # If both exist, we won't touch them further; fail loudly to avoid damage.
            raise RuntimeError("Both driver_phones and driver_phones_old exist; manual cleanup required.")

    # 2) Create the clean table we want
    op.create_table(
        "driver_phones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("extension", sa.String(length=10), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_driver_phones_driver_id ON driver_phones (driver_id)")


def downgrade() -> None:
    op.drop_index("ix_driver_phones_driver_id", table_name="driver_phones")
    op.drop_table("driver_phones")

    # Put the old table back if we renamed it
    bind = op.get_bind()
    old_exists = bind.execute(sa.text("SELECT to_regclass('public.driver_phones_old')")).scalar()
    current_exists = bind.execute(sa.text("SELECT to_regclass('public.driver_phones')")).scalar()
    if old_exists and not current_exists:
        op.execute("ALTER TABLE driver_phones_old RENAME TO driver_phones")
