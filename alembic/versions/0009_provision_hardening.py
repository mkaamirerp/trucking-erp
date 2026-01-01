"""Hardening platform_tenants for provisioning

Revision ID: 0009_provision_hardening
Revises: 0008_platform_users_and_members
Create Date: 2025-12-31 23:59:59.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009_provision_hardening"
down_revision: Union[str, Sequence[str], None] = "0008_platform_users_and_members"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop password column to avoid storing secrets (only if it exists)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("platform_tenants")}
    with op.batch_alter_table("platform_tenants") as batch:
        if "db_password_encrypted" in cols:
            batch.drop_column("db_password_encrypted")
        batch.add_column(sa.Column("db_last_error_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("provisioned_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("platform_tenants") as batch:
        batch.drop_column("provisioned_at")
        batch.drop_column("db_last_error_at")
        batch.add_column(sa.Column("db_password_encrypted", sa.String(length=1024), nullable=True))
