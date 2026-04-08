"""Global booking broker reference tables + tenant auto-create policy flag.

Revision ID: 0035_global_booking_broker_reference
Revises: 0034_platform_login_unlock_step_up_pending
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035_global_booking_broker_reference"
down_revision: Union[str, Sequence[str], None] = "0034_platform_login_unlock_step_up_pending"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "global_booking_brokers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("legal_name", sa.String(length=500), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("mc_number", sa.String(length=100), nullable=True),
        sa.Column("dot_number", sa.String(length=32), nullable=True),
        sa.Column("canonical_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_global_booking_brokers_canonical_status", "global_booking_brokers", ["canonical_status"])

    op.create_table(
        "global_booking_broker_domains",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("global_broker_id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["global_broker_id"], ["global_booking_brokers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_global_booking_broker_domains_broker_id", "global_booking_broker_domains", ["global_broker_id"]
    )

    op.create_table(
        "global_booking_broker_known_senders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("global_broker_id", sa.Integer(), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["global_broker_id"], ["global_booking_brokers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_global_booking_broker_known_senders_broker_id",
        "global_booking_broker_known_senders",
        ["global_broker_id"],
    )

    op.create_table(
        "global_booking_broker_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("global_broker_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["global_broker_id"], ["global_booking_brokers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_global_booking_broker_aliases_broker_id", "global_booking_broker_aliases", ["global_broker_id"])

    op.execute(
        """
        CREATE UNIQUE INDEX uq_global_booking_broker_domains_domain_active
        ON global_booking_broker_domains (domain)
        WHERE is_active IS TRUE
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_global_booking_broker_known_senders_email_active
        ON global_booking_broker_known_senders (email_normalized)
        WHERE is_active IS TRUE
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_global_booking_broker_aliases_alias_active
        ON global_booking_broker_aliases (alias)
        WHERE is_active IS TRUE
        """
    )

    op.add_column(
        "platform_tenants",
        sa.Column("broker_auto_create_from_global", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("platform_tenants", "broker_auto_create_from_global")
    op.execute("DROP INDEX IF EXISTS uq_global_booking_broker_aliases_alias_active")
    op.execute("DROP INDEX IF EXISTS uq_global_booking_broker_known_senders_email_active")
    op.execute("DROP INDEX IF EXISTS uq_global_booking_broker_domains_domain_active")
    op.drop_table("global_booking_broker_aliases")
    op.drop_table("global_booking_broker_known_senders")
    op.drop_table("global_booking_broker_domains")
    op.drop_index("ix_global_booking_brokers_canonical_status", table_name="global_booking_brokers")
    op.drop_table("global_booking_brokers")
