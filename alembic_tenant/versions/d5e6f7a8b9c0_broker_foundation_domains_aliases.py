"""Broker archive + broker_domains + broker_aliases (partial uniques).

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    # --- brokers ---
    cols_b = {c["name"] for c in inspector.get_columns("brokers")}
    if "is_active" not in cols_b:
        op.add_column(
            "brokers",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
        op.alter_column("brokers", "is_active", server_default=None)
    if "archived_at" not in cols_b:
        op.add_column("brokers", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    inspector = Inspector.from_engine(bind)
    ix_b = {i["name"] for i in inspector.get_indexes("brokers")}
    if "ix_brokers_tenant_active_name" not in ix_b:
        op.create_index("ix_brokers_tenant_active_name", "brokers", ["tenant_id", "is_active", "name"])

    # --- broker_contacts ---
    cols_c = {c["name"] for c in inspector.get_columns("broker_contacts")}
    if "is_active" not in cols_c:
        op.add_column(
            "broker_contacts",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
        op.alter_column("broker_contacts", "is_active", server_default=None)
    if "archived_at" not in cols_c:
        op.add_column("broker_contacts", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    inspector = Inspector.from_engine(bind)
    ix_c = {i["name"] for i in inspector.get_indexes("broker_contacts")}
    if "ix_broker_contacts_tenant_broker_active" not in ix_c:
        op.create_index(
            "ix_broker_contacts_tenant_broker_active",
            "broker_contacts",
            ["tenant_id", "broker_id", "is_active"],
        )

    tables = inspector.get_table_names()
    if "broker_domains" not in tables:
        op.create_table(
            "broker_domains",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("broker_id", sa.Integer(), nullable=False),
            sa.Column("domain", sa.String(length=255), nullable=False),
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
        op.create_index("ix_broker_domains_tenant_id", "broker_domains", ["tenant_id"])
        op.create_index("ix_broker_domains_broker_id", "broker_domains", ["broker_id"])
        op.create_index(
            "ix_broker_domains_tenant_broker",
            "broker_domains",
            ["tenant_id", "broker_id"],
        )
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_broker_domains_tenant_domain_active
            ON broker_domains (tenant_id, domain)
            WHERE is_active IS TRUE
            """
        )

    if "broker_aliases" not in tables:
        op.create_table(
            "broker_aliases",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("broker_id", sa.Integer(), nullable=False),
            sa.Column("alias", sa.String(length=255), nullable=False),
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
        op.create_index("ix_broker_aliases_tenant_id", "broker_aliases", ["tenant_id"])
        op.create_index("ix_broker_aliases_broker_id", "broker_aliases", ["broker_id"])
        op.create_index(
            "ix_broker_aliases_tenant_broker",
            "broker_aliases",
            ["tenant_id", "broker_id"],
        )
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_broker_aliases_tenant_alias_active
            ON broker_aliases (tenant_id, alias)
            WHERE is_active IS TRUE
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_broker_aliases_tenant_alias_active")
    op.drop_index("ix_broker_aliases_tenant_broker", table_name="broker_aliases")
    op.drop_index("ix_broker_aliases_broker_id", table_name="broker_aliases")
    op.drop_index("ix_broker_aliases_tenant_id", table_name="broker_aliases")
    op.drop_table("broker_aliases")

    op.execute("DROP INDEX IF EXISTS uq_broker_domains_tenant_domain_active")
    op.drop_index("ix_broker_domains_tenant_broker", table_name="broker_domains")
    op.drop_index("ix_broker_domains_broker_id", table_name="broker_domains")
    op.drop_index("ix_broker_domains_tenant_id", table_name="broker_domains")
    op.drop_table("broker_domains")

    op.drop_index("ix_broker_contacts_tenant_broker_active", table_name="broker_contacts")
    op.drop_column("broker_contacts", "archived_at")
    op.drop_column("broker_contacts", "is_active")

    op.drop_index("ix_brokers_tenant_active_name", table_name="brokers")
    op.drop_column("brokers", "archived_at")
    op.drop_column("brokers", "is_active")
