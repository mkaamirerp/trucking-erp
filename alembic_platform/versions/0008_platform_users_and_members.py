"""Add platform users and tenant memberships

Revision ID: 0008_platform_users_and_members
Revises: 0007_platform_subs
Create Date: 2025-12-31 23:59:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_platform_users_and_members"
down_revision: Union[str, Sequence[str], None] = "0007_platform_subs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("verification_token_hash", sa.String(length=128), nullable=True),
        sa.Column("verification_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name="uq_platform_users_email"),
    )

    op.create_table(
        "platform_tenant_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform_user_id", sa.String(length=36), sa.ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default=sa.text("'TENANT_OWNER'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "platform_user_id", name="uq_platform_tenant_member_unique"),
    )

    # Align defaults for provisioning
    op.alter_column("platform_tenants", "status", server_default=sa.text("'PROVISIONING'"))
    op.alter_column("platform_tenants", "db_status", server_default=sa.text("'NOT_PROVISIONED'"))


def downgrade() -> None:
    op.alter_column("platform_tenants", "status", server_default=None)
    op.alter_column("platform_tenants", "db_status", server_default=None)
    op.drop_table("platform_tenant_members")
    op.drop_table("platform_users")
