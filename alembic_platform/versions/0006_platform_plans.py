"""Add platform plans and plan_features tables

Revision ID: 0006_platform_plans
Revises: 0005_platform_registry
Create Date: 2025-01-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_platform_plans"
down_revision: Union[str, Sequence[str], None] = "0005_platform_registry"  # depends on prior migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("tagline", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("monthly_price", sa.Float(), nullable=True),
        sa.Column("annual_price", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("is_contact_sales", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("trial_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("trial_days", sa.Integer(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("max_drivers", sa.Integer(), nullable=True),
        sa.Column("max_trucks", sa.Integer(), nullable=True),
        sa.Column("max_trailers", sa.Integer(), nullable=True),
        sa.Column("storage_limit_gb", sa.Integer(), nullable=True),
        sa.Column("integrations_enabled", sa.Boolean(), nullable=True),
        sa.Column("audit_retention_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_plans_slug"),
    )
    op.execute("CREATE UNIQUE INDEX uq_plans_featured_true ON plans (is_featured) WHERE is_featured = true;")
    op.create_table(
        "plan_features",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("plan_features")
    op.drop_table("plans")
