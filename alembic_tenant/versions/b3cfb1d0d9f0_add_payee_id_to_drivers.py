"""Add payee_id to drivers (with optional FK).

Revision ID: b3cfb1d0d9f0
Revises: t001_merge_heads_driver_license_payroll
Create Date: 2026-01-06 00:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3cfb1d0d9f0"
down_revision: Union[str, Sequence[str], None] = "t001_merge_heads_driver_license_payroll"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    tables = set(inspector.get_table_names(schema="public"))
    if "drivers" not in tables:
        return
    columns = {col["name"] for col in inspector.get_columns("drivers", schema="public")}
    if "payee_id" not in columns:
        op.add_column(
            "drivers",
            sa.Column("payee_id", sa.Integer(), nullable=True),
            schema="public",
        )
        columns.add("payee_id")

    uniques = {uc["name"] for uc in inspector.get_unique_constraints("drivers", schema="public")}
    if "uq_drivers_payee_id" not in uniques and "payee_id" in columns:
        op.create_unique_constraint("uq_drivers_payee_id", "drivers", ["payee_id"], schema="public")

    fk_names = {fk["name"] for fk in inspector.get_foreign_keys("drivers", schema="public")}
    if "payees" in tables and "fk_drivers_payee_id" not in fk_names and "payee_id" in columns:
        op.create_foreign_key(
            "fk_drivers_payee_id",
            "drivers",
            "payees",
            local_cols=["payee_id"],
            remote_cols=["id"],
            source_schema="public",
            referent_schema="public",
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    op.drop_constraint("fk_drivers_payee_id", "drivers", type_="foreignkey")
    op.drop_constraint("uq_drivers_payee_id", "drivers", type_="unique")
    op.drop_column("drivers", "payee_id")
