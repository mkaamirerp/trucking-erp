"""Make platform_company_profiles.setup_completed_at nullable"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0011_company_setup_completed_nullable"
down_revision: Union[str, Sequence[str], None] = "0010_platform_billing_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("platform_company_profiles")}
    if "setup_completed_at" in columns:
        with op.batch_alter_table("platform_company_profiles") as batch:
            batch.alter_column(
                "setup_completed_at",
                existing_type=sa.DateTime(timezone=True),
                server_default=None,
                nullable=True,
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("platform_company_profiles")}
    if "setup_completed_at" in columns:
        with op.batch_alter_table("platform_company_profiles") as batch:
            batch.alter_column(
                "setup_completed_at",
                existing_type=sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            )
