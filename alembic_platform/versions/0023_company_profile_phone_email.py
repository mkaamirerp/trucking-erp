"""Add company_phone and company_email to platform_company_profiles.

Revision ID: 0023_company_profile_phone_email
Revises: 0022_platform_admins
Create Date: 2026-03-07

For invoices and pay stubs: business address is canonical; phone and email
collected at signup flow into company profile. Nullable for backfill.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023_company_profile_phone_email"
down_revision: Union[str, Sequence[str], None] = "0022_platform_admins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_company_profiles",
        sa.Column("company_phone", sa.String(50), nullable=True),
    )
    op.add_column(
        "platform_company_profiles",
        sa.Column("company_email", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("platform_company_profiles", "company_email")
    op.drop_column("platform_company_profiles", "company_phone")
