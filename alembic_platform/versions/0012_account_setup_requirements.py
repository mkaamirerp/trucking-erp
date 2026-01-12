"""Add W9 and HST fields for company profiles"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0012_account_setup_requirements"
down_revision: Union[str, Sequence[str], None] = "0011_company_setup_completed_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    with op.batch_alter_table("platform_company_profiles") as batch:
        if not _has_column("platform_company_profiles", "hst_number"):
            batch.add_column(sa.Column("hst_number", sa.String(length=50), nullable=True))
        if not _has_column("platform_company_profiles", "w9_storage_key"):
            batch.add_column(sa.Column("w9_storage_key", sa.String(length=255), nullable=True))
        if not _has_column("platform_company_profiles", "w9_original_filename"):
            batch.add_column(sa.Column("w9_original_filename", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("platform_company_profiles") as batch:
        if _has_column("platform_company_profiles", "w9_original_filename"):
            batch.drop_column("w9_original_filename")
        if _has_column("platform_company_profiles", "w9_storage_key"):
            batch.drop_column("w9_storage_key")
        if _has_column("platform_company_profiles", "hst_number"):
            batch.drop_column("hst_number")
