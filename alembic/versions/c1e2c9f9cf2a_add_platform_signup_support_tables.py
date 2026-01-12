"""Add platform signup support tables (OTP, security events, company profiles, reserved slugs)

Revision ID: c1e2c9f9cf2a
Revises: b8f9cfe34f1b
Create Date: 2026-01-11 07:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1e2c9f9cf2a"
down_revision: Union[str, Sequence[str], None] = "b8f9cfe34f1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "platform_security_events" not in tables:
        op.create_table(
            "platform_security_events",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("user_id", sa.String(36), nullable=True),
            sa.Column("tenant_id", sa.Integer, nullable=True),
            sa.Column("ip", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.Text, nullable=True),
            sa.Column("metadata", sa.dialects.postgresql.JSONB, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if "platform_otp_tokens" not in tables:
        op.create_table(
            "platform_otp_tokens",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("purpose", sa.String(50), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=True),
            sa.Column("otp_hash", sa.String(128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("request_ip", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if "platform_company_profiles" not in tables:
        op.create_table(
            "platform_company_profiles",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer,
                sa.ForeignKey("platform_tenants.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("legal_name", sa.String(255), nullable=False),
            sa.Column("address_street", sa.String(255), nullable=False),
            sa.Column("address_city", sa.String(100), nullable=False),
            sa.Column("address_region", sa.String(100), nullable=False),
            sa.Column("address_postal", sa.String(20), nullable=False),
            sa.Column("address_country", sa.String(2), nullable=False),
            sa.Column("usdot_number", sa.String(50), nullable=True),
            sa.Column("mc_number", sa.String(50), nullable=True),
            sa.Column("cvor_number", sa.String(50), nullable=True),
            sa.Column("operator_license", sa.String(100), nullable=True),
            sa.Column("setup_completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if "reserved_slugs" not in tables:
        op.create_table(
            "reserved_slugs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("slug", sa.String(63), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "reserved_slugs" in tables:
        op.drop_table("reserved_slugs")
    if "platform_company_profiles" in tables:
        op.drop_table("platform_company_profiles")
    if "platform_otp_tokens" in tables:
        op.drop_table("platform_otp_tokens")
    if "platform_security_events" in tables:
        op.drop_table("platform_security_events")
