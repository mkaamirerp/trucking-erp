"""Load V1: broker_contacts, loads snapshot/header fields, load_stops expanded

Revision ID: k6f7a8b9c0d1
Revises: j5e6f7a8b9c0
Create Date: 2026-03-21

Adds:
- broker_contacts table (agent under broker)
- loads: broker/contact snapshot fields, broker_load_reference, mode, trailer_type,
  trailer_size, commodity, estimated_weight, hazmat_flag, temperature_requirement,
  pallet_case_count, internal_notes; broker_contact_id FK
- load_stops: facility_name, street, city, state_or_province, postal_code, country,
  reference_number, appointment_type, appointment_date, appointment_time_text,
  commodity_notes (keeps location for backward compat)
- status: add draft, ready; default new loads to draft
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector


revision = "k6f7a8b9c0d1"
down_revision = "j5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = set(inspector.get_table_names(schema="public"))

    # --- broker_contacts ---
    if "broker_contacts" not in tables:
        op.create_table(
            "broker_contacts",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer, nullable=False),
            sa.Column("broker_id", sa.Integer, sa.ForeignKey("brokers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("phone", sa.String(50), nullable=True),
            sa.Column("extension", sa.String(20), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )
        op.create_index("ix_broker_contacts_tenant_id", "broker_contacts", ["tenant_id"])
        op.create_index("ix_broker_contacts_broker_id", "broker_contacts", ["broker_id"])

    # --- loads new columns ---
    load_cols = {c["name"] for c in inspector.get_columns("loads", schema="public")}

    if "broker_contact_id" not in load_cols:
        op.add_column("loads", sa.Column("broker_contact_id", sa.Integer, nullable=True), schema="public")
        op.create_index("ix_loads_broker_contact_id", "loads", ["broker_contact_id"])
        op.create_foreign_key(
            "fk_loads_broker_contact_id_broker_contacts",
            "loads", "broker_contacts",
            ["broker_contact_id"], ["id"],
            ondelete="SET NULL",
        )
        load_cols = load_cols | {"broker_contact_id"}

    # Other load columns
    for col_name, col_type, default in [
        ("broker_name_snapshot", sa.String(255), None),
        ("broker_contact_name_snapshot", sa.String(255), None),
        ("broker_contact_phone_snapshot", sa.String(50), None),
        ("broker_contact_extension_snapshot", sa.String(20), None),
        ("broker_contact_email_snapshot", sa.String(255), None),
        ("broker_load_reference", sa.String(100), None),
        ("mode", sa.String(50), None),
        ("trailer_type", sa.String(50), None),
        ("trailer_size", sa.String(20), None),
        ("commodity", sa.String(255), None),
        ("estimated_weight", sa.Integer, None),
        ("hazmat_flag", sa.Boolean(), sa.text("false")),
        ("temperature_requirement", sa.String(50), None),
        ("pallet_case_count", sa.String(50), None),
        ("internal_notes", sa.Text(), None),
    ]:
        if col_name not in load_cols:
            kw = {"nullable": True}
            if default is not None:
                kw["server_default"] = default
            op.add_column("loads", sa.Column(col_name, col_type, **kw), schema="public")

    # status: add draft, ready; default new loads to draft
    op.alter_column(
        "loads", "status",
        existing_type=sa.String(32),
        server_default="draft",
        schema="public",
    )

    # --- load_stops new columns ---
    if "load_stops" in tables:
        stop_cols = {c["name"] for c in inspector.get_columns("load_stops", schema="public")}
        new_stop_cols = [
            ("facility_name", sa.String(255)),
            ("street", sa.String(255)),
            ("city", sa.String(100)),
            ("state_or_province", sa.String(50)),
            ("postal_code", sa.String(20)),
            ("country", sa.String(2)),
            ("reference_number", sa.String(100)),
            ("appointment_type", sa.String(50)),
            ("appointment_date", sa.Date()),
            ("appointment_time_text", sa.String(50)),
            ("commodity_notes", sa.Text()),
        ]
        for col_name, col_type in new_stop_cols:
            if col_name not in stop_cols:
                op.add_column(
                    "load_stops",
                    sa.Column(col_name, col_type, nullable=True),
                    schema="public",
                )

    # --- Drop legacy fields (no prod data; stops are source of truth) ---
    load_cols = {c["name"] for c in inspector.get_columns("loads", schema="public")}
    for col in ("pickup_date", "delivery_date", "pickup_time", "delivery_time", "pickup_location", "delivery_location"):
        if col in load_cols:
            op.drop_column("loads", col, schema="public")

    if "load_stops" in tables:
        stop_cols = {c["name"] for c in inspector.get_columns("load_stops", schema="public")}
        if "location" in stop_cols:
            op.drop_column("load_stops", "location", schema="public")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = set(inspector.get_table_names(schema="public"))

    # load_stops: drop new columns
    if "load_stops" in tables:
        stop_cols = {c["name"] for c in inspector.get_columns("load_stops", schema="public")}
        for col in ("commodity_notes", "appointment_time_text", "appointment_date", "appointment_type",
                    "reference_number", "country", "postal_code", "state_or_province", "city",
                    "street", "facility_name"):
            if col in stop_cols:
                op.drop_column("load_stops", col, schema="public")

    # loads: revert status default, drop new columns
    op.alter_column(
        "loads", "status",
        existing_type=sa.String(32),
        server_default="unassigned",
        schema="public",
    )
    load_cols = {c["name"] for c in inspector.get_columns("loads", schema="public")}
    drop_order = [
        "internal_notes", "pallet_case_count", "temperature_requirement", "hazmat_flag",
        "estimated_weight", "commodity", "trailer_size", "trailer_type", "mode",
        "broker_load_reference", "broker_contact_email_snapshot", "broker_contact_extension_snapshot",
        "broker_contact_phone_snapshot", "broker_contact_name_snapshot", "broker_name_snapshot",
    ]
    for col in drop_order:
        if col in load_cols:
            op.drop_column("loads", col, schema="public")
    if "broker_contact_id" in load_cols:
        try:
            op.drop_constraint("fk_loads_broker_contact_id_broker_contacts", "loads", type_="foreignkey")
        except Exception:
            pass
        op.drop_index("ix_loads_broker_contact_id", table_name="loads")
        op.drop_column("loads", "broker_contact_id", schema="public")

    # Restore legacy load columns (downgrade)
    load_cols = {c["name"] for c in inspector.get_columns("loads", schema="public")}
    for col, ctype in [
        ("pickup_location", sa.String(255)),
        ("delivery_location", sa.String(255)),
        ("pickup_date", sa.Date()),
        ("delivery_date", sa.Date()),
        ("pickup_time", sa.DateTime(timezone=True)),
        ("delivery_time", sa.DateTime(timezone=True)),
    ]:
        if col not in load_cols:
            op.add_column("loads", sa.Column(col, ctype, nullable=True), schema="public")

    if "load_stops" in tables:
        stop_cols = {c["name"] for c in inspector.get_columns("load_stops", schema="public")}
        if "location" not in stop_cols:
            op.add_column("load_stops", sa.Column("location", sa.String(255), nullable=True), schema="public")

    # broker_contacts
    if "broker_contacts" in tables:
        op.drop_index("ix_broker_contacts_broker_id", table_name="broker_contacts")
        op.drop_index("ix_broker_contacts_tenant_id", table_name="broker_contacts")
        op.drop_table("broker_contacts")
