"""Tenant broker link to platform global booking reference (logical id only).

Revision ID: b9a8c7d6e5f4
Revises: a8f7e6d5c4b3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "b9a8c7d6e5f4"
down_revision = "a8f7e6d5c4b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    cols = {c["name"] for c in inspector.get_columns("brokers")}
    if "platform_global_broker_id" not in cols:
        op.add_column("brokers", sa.Column("platform_global_broker_id", sa.Integer(), nullable=True))
    ix = {i["name"] for i in inspector.get_indexes("brokers")}
    if "ix_brokers_platform_global_broker_id" not in ix:
        op.create_index("ix_brokers_platform_global_broker_id", "brokers", ["platform_global_broker_id"])
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_brokers_tenant_platform_global_broker
        ON brokers (tenant_id, platform_global_broker_id)
        WHERE platform_global_broker_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_brokers_tenant_platform_global_broker")
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    ix = {i["name"] for i in inspector.get_indexes("brokers")}
    if "ix_brokers_platform_global_broker_id" in ix:
        op.drop_index("ix_brokers_platform_global_broker_id", table_name="brokers")
    cols = {c["name"] for c in inspector.get_columns("brokers")}
    if "platform_global_broker_id" in cols:
        op.drop_column("brokers", "platform_global_broker_id")
