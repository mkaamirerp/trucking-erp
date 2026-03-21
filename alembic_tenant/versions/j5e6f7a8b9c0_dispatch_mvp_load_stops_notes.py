"""Dispatch MVP: load dispatch fields, load_stops, load_stop_actions, load_notes

Revision ID: j5e6f7a8b9c0
Revises: i4d5e6f7a8b9
Create Date: 2026-03-17

Dispatch status model: unassigned, assigned, dispatched, arrived_pickup, in_transit,
arrived_delivery, delivered, issue_hold.
ELD-ready fields (no logic): current_location, last_ping_at, location_source.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector


revision = "j5e6f7a8b9c0"
down_revision = "i4d5e6f7a8b9"
branch_labels = None
depends_on = None

DISPATCH_STATUSES = [
    "unassigned", "assigned", "dispatched", "arrived_pickup", "in_transit",
    "arrived_delivery", "delivered", "issue_hold",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    cols = {c["name"] for c in inspector.get_columns("loads", schema="public")}

    if "truck_id" not in cols:
        op.add_column("loads", sa.Column("truck_id", sa.Integer, nullable=True), schema="public")
        op.create_index("ix_loads_truck_id", "loads", ["truck_id"])
        if "trucks" in inspector.get_table_names(schema="public"):
            op.create_foreign_key(
                "fk_loads_truck_id_trucks",
                "loads", "trucks",
                ["truck_id"], ["id"],
                ondelete="SET NULL",
            )
    if "trailer_id" not in cols:
        op.add_column("loads", sa.Column("trailer_id", sa.Integer, nullable=True), schema="public")
        op.create_index("ix_loads_trailer_id", "loads", ["trailer_id"])
        if "trailers" in inspector.get_table_names(schema="public"):
            op.create_foreign_key(
                "fk_loads_trailer_id_trailers",
                "loads", "trailers",
                ["trailer_id"], ["id"],
                ondelete="SET NULL",
            )
    if "equipment_type" not in cols:
        op.add_column("loads", sa.Column("equipment_type", sa.String(50), nullable=True), schema="public")
    if "customer_rate" not in cols:
        op.add_column("loads", sa.Column("customer_rate", sa.Numeric(14, 2), nullable=True), schema="public")
    if "pickup_time" not in cols:
        op.add_column("loads", sa.Column("pickup_time", sa.DateTime(timezone=True), nullable=True), schema="public")
    if "delivery_time" not in cols:
        op.add_column("loads", sa.Column("delivery_time", sa.DateTime(timezone=True), nullable=True), schema="public")
    if "current_location" not in cols:
        op.add_column("loads", sa.Column("current_location", sa.String(255), nullable=True), schema="public")
    if "last_ping_at" not in cols:
        op.add_column("loads", sa.Column("last_ping_at", sa.DateTime(timezone=True), nullable=True), schema="public")
    if "location_source" not in cols:
        op.add_column("loads", sa.Column("location_source", sa.String(50), nullable=True), schema="public")

    try:
        op.execute(
            sa.text("""
                UPDATE loads SET status = CASE
                    WHEN status = 'planned' AND driver_id IS NULL THEN 'unassigned'
                    WHEN status = 'planned' AND driver_id IS NOT NULL THEN 'assigned'
                    WHEN status = 'assigned' THEN 'dispatched'
                    WHEN status = 'picked_up' THEN 'in_transit'
                    WHEN status = 'delivered' THEN 'delivered'
                    WHEN status = 'invoiced' THEN 'delivered'
                    WHEN status = 'cancelled' THEN 'issue_hold'
                    ELSE 'unassigned'
                END
            """)
        )
    except Exception:
        pass
    op.alter_column(
        "loads", "status",
        existing_type=sa.String(32),
        server_default="unassigned",
        schema="public",
    )

    if "load_stops" not in inspector.get_table_names(schema="public"):
        op.create_table(
            "load_stops",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer, nullable=False),
            sa.Column("load_id", sa.Integer, sa.ForeignKey("loads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stop_type", sa.String(20), nullable=False),
            sa.Column("sequence", sa.Integer, nullable=False, server_default="0"),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("departed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )
        op.create_index("ix_load_stops_load_id", "load_stops", ["load_id"])
        op.create_index("ix_load_stops_tenant_id", "load_stops", ["tenant_id"])

    if "load_stop_actions" not in inspector.get_table_names(schema="public"):
        op.create_table(
            "load_stop_actions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer, nullable=False),
            sa.Column("load_stop_id", sa.Integer, sa.ForeignKey("load_stops.id", ondelete="CASCADE"), nullable=False),
            sa.Column("action_type", sa.String(30), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_load_stop_actions_load_stop_id", "load_stop_actions", ["load_stop_id"])

    if "load_notes" not in inspector.get_table_names(schema="public"):
        op.create_table(
            "load_notes",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer, nullable=False),
            sa.Column("load_id", sa.Integer, sa.ForeignKey("loads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("author_user_id", sa.String(36), nullable=True),
            sa.Column("body", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_load_notes_load_id", "load_notes", ["load_id"])
        op.create_index("ix_load_notes_tenant_id", "load_notes", ["tenant_id"])
        op.create_index("ix_load_notes_created_at", "load_notes", ["load_id", "created_at"])


def _fk_exists(conn, table: str, name: str) -> bool:
    r = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint WHERE conrelid = (:t)::regclass AND conname = :n"
        ),
        {"t": f"public.{table}", "n": name},
    )
    return r.scalar() is not None


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = set(inspector.get_table_names(schema="public"))

    if "load_notes" in tables:
        op.drop_index("ix_load_notes_created_at", table_name="load_notes")
        op.drop_index("ix_load_notes_tenant_id", table_name="load_notes")
        op.drop_index("ix_load_notes_load_id", table_name="load_notes")
        op.drop_table("load_notes")

    if "load_stop_actions" in tables:
        op.drop_index("ix_load_stop_actions_load_stop_id", table_name="load_stop_actions")
        op.drop_table("load_stop_actions")

    if "load_stops" in tables:
        op.drop_index("ix_load_stops_tenant_id", table_name="load_stops")
        op.drop_index("ix_load_stops_load_id", table_name="load_stops")
        op.drop_table("load_stops")

    cols = {c["name"] for c in inspector.get_columns("loads", schema="public")}
    if "trailer_id" in cols:
        if _fk_exists(conn, "loads", "fk_loads_trailer_id_trailers"):
            op.drop_constraint("fk_loads_trailer_id_trailers", "loads", type_="foreignkey")
        op.drop_index("ix_loads_trailer_id", table_name="loads")
        op.drop_column("loads", "trailer_id", schema="public")
    if "truck_id" in cols:
        if _fk_exists(conn, "loads", "fk_loads_truck_id_trucks"):
            op.drop_constraint("fk_loads_truck_id_trucks", "loads", type_="foreignkey")
        op.drop_index("ix_loads_truck_id", table_name="loads")
        op.drop_column("loads", "truck_id", schema="public")
    for col in ("location_source", "last_ping_at", "current_location", "delivery_time", "pickup_time",
                "customer_rate", "equipment_type"):
        if col in cols:
            op.drop_column("loads", col, schema="public")

    op.alter_column("loads", "status", server_default="planned", schema="public")
