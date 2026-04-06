"""Broker master data: rich firm fields, contacts, domains, aliases, known senders.

Revision ID: f9a0b1c2d3e4
Revises: e7f8a9b0c1d2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "f9a0b1c2d3e4"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    # --- brokers ---
    cols = {c["name"] for c in inspector.get_columns("brokers")}
    if "legal_name" not in cols:
        op.add_column("brokers", sa.Column("legal_name", sa.String(length=500), nullable=True))
    if "display_name" not in cols:
        op.add_column("brokers", sa.Column("display_name", sa.String(length=255), nullable=True))
    if "dot_number" not in cols:
        op.add_column("brokers", sa.Column("dot_number", sa.String(length=32), nullable=True))
    if "scac" not in cols:
        op.add_column("brokers", sa.Column("scac", sa.String(length=16), nullable=True))
    if "phone_secondary" not in cols:
        op.add_column("brokers", sa.Column("phone_secondary", sa.String(length=50), nullable=True))
    if "email_secondary" not in cols:
        op.add_column("brokers", sa.Column("email_secondary", sa.String(length=255), nullable=True))
    if "website" not in cols:
        op.add_column("brokers", sa.Column("website", sa.String(length=512), nullable=True))
    if "address_line1" not in cols:
        op.add_column("brokers", sa.Column("address_line1", sa.String(length=255), nullable=True))
    if "address_line2" not in cols:
        op.add_column("brokers", sa.Column("address_line2", sa.String(length=255), nullable=True))
    if "address_city" not in cols:
        op.add_column("brokers", sa.Column("address_city", sa.String(length=120), nullable=True))
    if "address_region" not in cols:
        op.add_column("brokers", sa.Column("address_region", sa.String(length=120), nullable=True))
    if "address_postal" not in cols:
        op.add_column("brokers", sa.Column("address_postal", sa.String(length=32), nullable=True))
    if "address_country" not in cols:
        op.add_column("brokers", sa.Column("address_country", sa.String(length=2), nullable=True))
    if "classification_notes" not in cols:
        op.add_column("brokers", sa.Column("classification_notes", sa.Text(), nullable=True))
    if "internal_notes" not in cols:
        op.add_column("brokers", sa.Column("internal_notes", sa.Text(), nullable=True))

    inspector = Inspector.from_engine(bind)
    cols = {c["name"] for c in inspector.get_columns("brokers")}
    if "legal_name" in cols and "display_name" in cols:
        op.execute(
            """
            UPDATE brokers
            SET legal_name = name
            WHERE legal_name IS NULL AND name IS NOT NULL
            """
        )
        op.execute(
            """
            UPDATE brokers
            SET display_name = name
            WHERE display_name IS NULL AND name IS NOT NULL
            """
        )
        op.execute(
            """
            UPDATE brokers
            SET internal_notes = notes
            WHERE internal_notes IS NULL AND notes IS NOT NULL AND trim(notes) <> ''
            """
        )

    # --- broker_contacts ---
    inspector = Inspector.from_engine(bind)
    ccols = {c["name"] for c in inspector.get_columns("broker_contacts")}
    if "first_name" not in ccols:
        op.add_column("broker_contacts", sa.Column("first_name", sa.String(length=120), nullable=True))
    if "last_name" not in ccols:
        op.add_column("broker_contacts", sa.Column("last_name", sa.String(length=120), nullable=True))
    if "role" not in ccols:
        op.add_column("broker_contacts", sa.Column("role", sa.String(length=120), nullable=True))
    if "department" not in ccols:
        op.add_column("broker_contacts", sa.Column("department", sa.String(length=120), nullable=True))
    if "fax" not in ccols:
        op.add_column("broker_contacts", sa.Column("fax", sa.String(length=50), nullable=True))
    if "is_primary" not in ccols:
        op.add_column(
            "broker_contacts",
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        op.alter_column("broker_contacts", "is_primary", server_default=None)
    if "notes" not in ccols:
        op.add_column("broker_contacts", sa.Column("notes", sa.Text(), nullable=True))

    # --- broker_domains ---
    inspector = Inspector.from_engine(bind)
    dcols = {c["name"] for c in inspector.get_columns("broker_domains")}
    if "is_primary" not in dcols:
        op.add_column(
            "broker_domains",
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        op.alter_column("broker_domains", "is_primary", server_default=None)
    if "notes" not in dcols:
        op.add_column("broker_domains", sa.Column("notes", sa.Text(), nullable=True))

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_broker_domains_one_primary_active
        ON broker_domains (tenant_id, broker_id)
        WHERE is_active IS TRUE AND is_primary IS TRUE
        """
    )

    # --- broker_aliases ---
    inspector = Inspector.from_engine(bind)
    acols = {c["name"] for c in inspector.get_columns("broker_aliases")}
    if "alias_type" not in acols:
        op.add_column(
            "broker_aliases",
            sa.Column(
                "alias_type",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'display'"),
            ),
        )
        op.alter_column("broker_aliases", "alias_type", server_default=None)

    # --- broker_known_senders ---
    tables = inspector.get_table_names()
    if "broker_known_senders" not in tables:
        op.create_table(
            "broker_known_senders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("broker_id", sa.Integer(), nullable=False),
            sa.Column("email_normalized", sa.String(length=320), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["broker_id"], ["brokers.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_broker_known_senders_tenant_id", "broker_known_senders", ["tenant_id"])
        op.create_index("ix_broker_known_senders_broker_id", "broker_known_senders", ["broker_id"])
        op.create_index(
            "ix_broker_known_senders_tenant_broker",
            "broker_known_senders",
            ["tenant_id", "broker_id"],
        )
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_broker_known_senders_tenant_email_active
            ON broker_known_senders (tenant_id, email_normalized)
            WHERE is_active IS TRUE
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_broker_known_senders_tenant_email_active")
    op.drop_index("ix_broker_known_senders_tenant_broker", table_name="broker_known_senders")
    op.drop_index("ix_broker_known_senders_broker_id", table_name="broker_known_senders")
    op.drop_index("ix_broker_known_senders_tenant_id", table_name="broker_known_senders")
    op.drop_table("broker_known_senders")

    op.execute("DROP INDEX IF EXISTS uq_broker_domains_one_primary_active")

    op.drop_column("broker_aliases", "alias_type")
    op.drop_column("broker_domains", "notes")
    op.drop_column("broker_domains", "is_primary")
    op.drop_column("broker_contacts", "notes")
    op.drop_column("broker_contacts", "is_primary")
    op.drop_column("broker_contacts", "fax")
    op.drop_column("broker_contacts", "department")
    op.drop_column("broker_contacts", "role")
    op.drop_column("broker_contacts", "last_name")
    op.drop_column("broker_contacts", "first_name")

    op.drop_column("brokers", "internal_notes")
    op.drop_column("brokers", "classification_notes")
    op.drop_column("brokers", "address_country")
    op.drop_column("brokers", "address_postal")
    op.drop_column("brokers", "address_region")
    op.drop_column("brokers", "address_city")
    op.drop_column("brokers", "address_line2")
    op.drop_column("brokers", "address_line1")
    op.drop_column("brokers", "website")
    op.drop_column("brokers", "email_secondary")
    op.drop_column("brokers", "phone_secondary")
    op.drop_column("brokers", "scac")
    op.drop_column("brokers", "dot_number")
    op.drop_column("brokers", "display_name")
    op.drop_column("brokers", "legal_name")
