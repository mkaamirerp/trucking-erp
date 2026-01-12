"""create loads table

Revision ID: 0102_create_loads
Revises: 0101_create_brokers
Create Date: 2026-01-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "0102_create_loads"
down_revision = "0101_create_brokers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if "loads" in inspector.get_table_names():
        return

    op.create_table(
        "loads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("load_number", sa.String(length=50), nullable=False),
        sa.Column("broker_id", sa.Integer, sa.ForeignKey("brokers.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("driver_id", sa.Integer, sa.ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pickup_date", sa.Date, nullable=True),
        sa.Column("delivery_date", sa.Date, nullable=True),
        sa.Column("pickup_location", sa.String(length=255), nullable=True),
        sa.Column("delivery_location", sa.String(length=255), nullable=True),
        sa.Column("rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("miles", sa.Integer, nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "load_number", name="uq_loads_tenant_load_number"),
    )
    op.create_index("ix_loads_tenant_id", "loads", ["tenant_id"])
    op.create_index("ix_loads_broker_id", "loads", ["broker_id"])
    op.create_index("ix_loads_driver_id", "loads", ["driver_id"])
    op.create_index("ix_loads_status", "loads", ["status"])


def downgrade() -> None:
    op.drop_index("ix_loads_status", table_name="loads")
    op.drop_index("ix_loads_driver_id", table_name="loads")
    op.drop_index("ix_loads_broker_id", table_name="loads")
    op.drop_index("ix_loads_tenant_id", table_name="loads")
    op.drop_table("loads")
