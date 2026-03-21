"""Create driver onboarding submissions table.

Revision ID: 9e4f2c1b7a6d
Revises: 8c84780c154b
Create Date: 2026-02-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9e4f2c1b7a6d"
down_revision: Union[str, Sequence[str], None] = "8c84780c154b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names(schema="public"))

    if "driver_onboarding_submissions" not in tables:
        op.create_table(
            "driver_onboarding_submissions",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("created_by_user_id", sa.BigInteger(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("source", sa.Text(), nullable=False, server_default="driver_portal"),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_by_user_id", sa.BigInteger(), nullable=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("first_name", sa.Text(), nullable=False),
            sa.Column("last_name", sa.Text(), nullable=False),
            sa.Column("phone", sa.Text(), nullable=True),
            sa.Column("email", sa.Text(), nullable=True),
            sa.Column("address_street", sa.Text(), nullable=True),
            sa.Column("address_city", sa.Text(), nullable=True),
            sa.Column("address_region", sa.Text(), nullable=True),
            sa.Column("address_postal", sa.Text(), nullable=True),
            sa.Column("address_country", sa.Text(), nullable=True),
            sa.Column("driver_license_number", sa.Text(), nullable=True),
            sa.Column("license_region", sa.Text(), nullable=True),
            sa.Column("license_expiry", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            schema="public",
        )
        inspector = sa.inspect(bind)

    indexes = {idx["name"] for idx in inspector.get_indexes("driver_onboarding_submissions", schema="public")}
    if "ix_driver_onboarding_submissions_tenant_status" not in indexes:
        op.create_index(
            "ix_driver_onboarding_submissions_tenant_status",
            "driver_onboarding_submissions",
            ["tenant_id", "status"],
            unique=False,
            schema="public",
        )
    if "ix_driver_onboarding_submissions_tenant_created_at" not in indexes:
        op.create_index(
            "ix_driver_onboarding_submissions_tenant_created_at",
            "driver_onboarding_submissions",
            ["tenant_id", sa.text("created_at DESC")],
            unique=False,
            schema="public",
        )


def downgrade() -> None:
    op.drop_index(
        "ix_driver_onboarding_submissions_tenant_created_at",
        table_name="driver_onboarding_submissions",
        schema="public",
    )
    op.drop_index(
        "ix_driver_onboarding_submissions_tenant_status",
        table_name="driver_onboarding_submissions",
        schema="public",
    )
    op.drop_table("driver_onboarding_submissions", schema="public")
