"""Add billing and locale fields to platform_tenants

Revision ID: 0010_platform_billing_fields
Revises: 0009_provision_hardening
Create Date: 2026-01-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_platform_billing_fields"
down_revision = "0009_provision_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_tenants",
        sa.Column("base_currency", sa.CHAR(length=3), nullable=False, server_default=sa.text("'USD'")),
    )
    op.add_column(
        "platform_tenants",
        sa.Column("timezone", sa.Text(), nullable=False, server_default=sa.text("'America/Toronto'")),
    )
    op.add_column("platform_tenants", sa.Column("country_code", sa.CHAR(length=2), nullable=True))
    op.add_column("platform_tenants", sa.Column("billing_status", sa.Text(), nullable=True))
    op.add_column("platform_tenants", sa.Column("billing_provider", sa.Text(), nullable=True))

    op.create_check_constraint(
        "chk_platform_tenants_base_currency_len",
        "platform_tenants",
        "char_length(base_currency) = 3",
    )


def downgrade() -> None:
    op.drop_constraint("chk_platform_tenants_base_currency_len", "platform_tenants", type_="check")
    op.drop_column("platform_tenants", "billing_provider")
    op.drop_column("platform_tenants", "billing_status")
    op.drop_column("platform_tenants", "country_code")
    op.drop_column("platform_tenants", "timezone")
    op.drop_column("platform_tenants", "base_currency")

