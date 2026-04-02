"""Customs broker master, contacts, load link + document snapshot confirmation.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-03-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customs_brokers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("admin_area", sa.String(50), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("phone_primary", sa.String(50), nullable=True),
        sa.Column("phone_secondary", sa.String(50), nullable=True),
        sa.Column("fax", sa.String(50), nullable=True),
        sa.Column("generic_email", sa.String(255), nullable=True),
        sa.Column("website_url", sa.String(512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_customs_brokers_tenant_id_id"),
    )
    op.create_index("ix_customs_brokers_tenant_id", "customs_brokers", ["tenant_id"], unique=False)
    op.create_index("ix_customs_brokers_tenant_legal_name", "customs_brokers", ["tenant_id", "legal_name"], unique=False)

    op.create_table(
        "customs_broker_contacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("customs_broker_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role_label", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("fax", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customs_broker_id"],
            ["customs_brokers.tenant_id", "customs_brokers.id"],
            ondelete="CASCADE",
            name="fk_customs_broker_contacts_broker_tenant",
        ),
    )
    op.create_index("ix_customs_broker_contacts_tenant_id", "customs_broker_contacts", ["tenant_id"], unique=False)
    op.create_index(
        "ix_customs_broker_contacts_tenant_broker", "customs_broker_contacts", ["tenant_id", "customs_broker_id"], unique=False
    )

    op.add_column("loads", sa.Column("customs_broker_id", sa.Integer(), nullable=True))
    op.add_column("loads", sa.Column("document_snapshot_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("loads", sa.Column("document_snapshot_confirmed_by_user_id", sa.String(36), nullable=True))
    op.add_column(
        "loads",
        sa.Column("document_snapshot_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_loads_customs_broker_id", "loads", ["customs_broker_id"], unique=False)

    op.create_unique_constraint("uq_loads_tenant_id_id", "loads", ["tenant_id", "id"])

    op.create_foreign_key(
        "fk_loads_customs_broker_tenant",
        "loads",
        "customs_brokers",
        ["tenant_id", "customs_broker_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "load_customs_snapshots",
        sa.Column("load_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("legal_name_snapshot", sa.String(255), nullable=True),
        sa.Column("address_line1_snapshot", sa.String(255), nullable=True),
        sa.Column("address_line2_snapshot", sa.String(255), nullable=True),
        sa.Column("city_snapshot", sa.String(100), nullable=True),
        sa.Column("admin_area_snapshot", sa.String(50), nullable=True),
        sa.Column("postal_code_snapshot", sa.String(20), nullable=True),
        sa.Column("country_code_snapshot", sa.String(2), nullable=True),
        sa.Column("phone_primary_snapshot", sa.String(50), nullable=True),
        sa.Column("phone_secondary_snapshot", sa.String(50), nullable=True),
        sa.Column("fax_snapshot", sa.String(50), nullable=True),
        sa.Column("generic_email_snapshot", sa.String(255), nullable=True),
        sa.Column("website_url_snapshot", sa.String(512), nullable=True),
        sa.Column("customs_broker_id_at_confirm", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            ondelete="CASCADE",
            name="fk_load_customs_snapshots_load_tenant",
        ),
        sa.PrimaryKeyConstraint("load_id", name="pk_load_customs_snapshots"),
    )
    op.create_index("ix_load_customs_snapshots_tenant_id", "load_customs_snapshots", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_load_customs_snapshots_tenant_id", table_name="load_customs_snapshots")
    op.drop_table("load_customs_snapshots")

    op.drop_constraint("fk_loads_customs_broker_tenant", "loads", type_="foreignkey")
    op.drop_constraint("uq_loads_tenant_id_id", "loads", type_="unique")
    op.drop_index("ix_loads_customs_broker_id", table_name="loads")
    op.drop_column("loads", "document_snapshot_version")
    op.drop_column("loads", "document_snapshot_confirmed_by_user_id")
    op.drop_column("loads", "document_snapshot_confirmed_at")
    op.drop_column("loads", "customs_broker_id")

    op.drop_index("ix_customs_broker_contacts_tenant_broker", table_name="customs_broker_contacts")
    op.drop_index("ix_customs_broker_contacts_tenant_id", table_name="customs_broker_contacts")
    op.drop_table("customs_broker_contacts")

    op.drop_index("ix_customs_brokers_tenant_legal_name", table_name="customs_brokers")
    op.drop_index("ix_customs_brokers_tenant_id", table_name="customs_brokers")
    op.drop_table("customs_brokers")
