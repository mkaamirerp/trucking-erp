"""Create trucks, trailers, fleet_documents tables (inventory-only fleet)

Revision ID: i4d5e6f7a8b9
Revises: h3c4d5e6f7a8
Create Date: 2026-03-17

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector


revision = "i4d5e6f7a8b9"
down_revision = "h3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = set(inspector.get_table_names(schema="public"))

    # Replace legacy trucks table (plate_number, model, driver_name) with new inventory schema
    if "trucks" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("trucks", schema="public")}
        if "unit_number" not in existing_cols:
            op.drop_table("trucks")
            tables.discard("trucks")

    if "trucks" not in tables:
        op.create_table(
            "trucks",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer, nullable=False),
            sa.Column("unit_number", sa.String(length=50), nullable=False),
            sa.Column("vin", sa.String(length=50), nullable=False),
            sa.Column("year", sa.Integer, nullable=True),
            sa.Column("make", sa.String(length=100), nullable=True),
            sa.Column("model", sa.String(length=100), nullable=True),
            sa.Column("color", sa.String(length=50), nullable=True),
            sa.Column("plate_number", sa.String(length=50), nullable=True),
            sa.Column("plate_region", sa.String(length=20), nullable=True),
            sa.Column("ownership_type", sa.String(length=30), nullable=False, server_default="company"),
            sa.Column("owner_person_id", sa.BigInteger, nullable=True),
            sa.Column("purchase_date", sa.Date, nullable=True),
            sa.Column("purchase_price", sa.Numeric(14, 2), nullable=True),
            sa.Column("engine_make", sa.String(length=100), nullable=True),
            sa.Column("engine_model", sa.String(length=100), nullable=True),
            sa.Column("engine_serial", sa.String(length=100), nullable=True),
            sa.Column("horsepower", sa.Integer, nullable=True),
            sa.Column("fuel_type", sa.String(length=30), nullable=True),
            sa.Column("transmission", sa.String(length=30), nullable=True),
            sa.Column("num_axles", sa.Integer, nullable=True),
            sa.Column("gvwr_lbs", sa.Integer, nullable=True),
            sa.Column("odometer_at_purchase", sa.Integer, nullable=True),
            sa.Column("current_odometer", sa.Integer, nullable=True),
            sa.Column("odometer_last_updated", sa.DateTime(timezone=True), nullable=True),
            sa.Column("insurance_carrier", sa.String(length=255), nullable=True),
            sa.Column("insurance_policy_number", sa.String(length=100), nullable=True),
            sa.Column("insurance_expiry", sa.Date, nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "unit_number", name="uq_trucks_tenant_unit_number"),
            sa.UniqueConstraint("tenant_id", "vin", name="uq_trucks_tenant_vin"),
        )
        op.create_index("ix_trucks_tenant_id", "trucks", ["tenant_id"])
        op.create_index("ix_trucks_status", "trucks", ["status"])
        op.create_index("ix_trucks_ownership_type", "trucks", ["ownership_type"])
        op.create_index("ix_trucks_unit_number", "trucks", ["tenant_id", "unit_number"])
        op.create_index("ix_trucks_vin", "trucks", ["tenant_id", "vin"])
        op.create_index("ix_trucks_plate_number", "trucks", ["plate_number"])

        if "people" in tables:
            op.create_foreign_key(
                "fk_trucks_owner_person_to_people",
                "trucks",
                "people",
                ["tenant_id", "owner_person_id"],
                ["tenant_id", "id"],
                ondelete="SET NULL",
            )

    if "trailers" not in tables:
        op.create_table(
            "trailers",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer, nullable=False),
            sa.Column("unit_number", sa.String(length=50), nullable=False),
            sa.Column("vin", sa.String(length=50), nullable=True),
            sa.Column("year", sa.Integer, nullable=True),
            sa.Column("make", sa.String(length=100), nullable=True),
            sa.Column("model", sa.String(length=100), nullable=True),
            sa.Column("plate_number", sa.String(length=50), nullable=True),
            sa.Column("plate_region", sa.String(length=20), nullable=True),
            sa.Column("trailer_type", sa.String(length=30), nullable=False, server_default="dry_van"),
            sa.Column("length_ft", sa.Integer, nullable=True),
            sa.Column("num_axles", sa.Integer, nullable=True),
            sa.Column("gvwr_lbs", sa.Integer, nullable=True),
            sa.Column("door_type", sa.String(length=30), nullable=True),
            sa.Column("reefer_make", sa.String(length=100), nullable=True),
            sa.Column("reefer_model", sa.String(length=100), nullable=True),
            sa.Column("reefer_serial", sa.String(length=100), nullable=True),
            sa.Column("ownership_type", sa.String(length=30), nullable=False, server_default="company"),
            sa.Column("owner_person_id", sa.BigInteger, nullable=True),
            sa.Column("purchase_date", sa.Date, nullable=True),
            sa.Column("purchase_price", sa.Numeric(14, 2), nullable=True),
            sa.Column("insurance_carrier", sa.String(length=255), nullable=True),
            sa.Column("insurance_policy_number", sa.String(length=100), nullable=True),
            sa.Column("insurance_expiry", sa.Date, nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "unit_number", name="uq_trailers_tenant_unit_number"),
        )
        op.create_index("ix_trailers_tenant_id", "trailers", ["tenant_id"])
        op.create_index("ix_trailers_status", "trailers", ["status"])
        op.create_index("ix_trailers_ownership_type", "trailers", ["ownership_type"])
        op.create_index("ix_trailers_unit_number", "trailers", ["tenant_id", "unit_number"])
        op.create_index("ix_trailers_plate_number", "trailers", ["plate_number"])

        op.execute(
            sa.text(
                "CREATE UNIQUE INDEX uq_trailers_tenant_vin ON trailers (tenant_id, vin) WHERE vin IS NOT NULL"
            )
        )

        if "people" in tables:
            op.create_foreign_key(
                "fk_trailers_owner_person_to_people",
                "trailers",
                "people",
                ["tenant_id", "owner_person_id"],
                ["tenant_id", "id"],
                ondelete="SET NULL",
            )

    if "fleet_documents" not in tables:
        op.create_table(
            "fleet_documents",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer, nullable=False),
            sa.Column("entity_type", sa.String(length=20), nullable=False),
            sa.Column("entity_id", sa.Integer, nullable=False),
            sa.Column("doc_type", sa.String(length=50), nullable=True),
            sa.Column("doc_number", sa.String(length=100), nullable=True),
            sa.Column("issued_date", sa.Date, nullable=True),
            sa.Column("expiry_date", sa.Date, nullable=True),
            sa.Column("storage_key", sa.String(length=512), nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )
        op.create_index("ix_fleet_documents_tenant_id", "fleet_documents", ["tenant_id"])
        op.create_index("ix_fleet_documents_entity", "fleet_documents", ["entity_type", "entity_id"])


def _constraint_exists(conn, table: str, name: str) -> bool:
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

    if "fleet_documents" in tables:
        op.drop_index("ix_fleet_documents_entity", table_name="fleet_documents")
        op.drop_index("ix_fleet_documents_tenant_id", table_name="fleet_documents")
        op.drop_table("fleet_documents")

    if "trailers" in tables:
        op.execute(sa.text("DROP INDEX IF EXISTS uq_trailers_tenant_vin"))
        if _constraint_exists(conn, "trailers", "fk_trailers_owner_person_to_people"):
            op.drop_constraint(
                "fk_trailers_owner_person_to_people",
                "trailers",
                type_="foreignkey",
            )
        op.drop_index("ix_trailers_plate_number", table_name="trailers")
        op.drop_index("ix_trailers_unit_number", table_name="trailers")
        op.drop_index("ix_trailers_ownership_type", table_name="trailers")
        op.drop_index("ix_trailers_status", table_name="trailers")
        op.drop_index("ix_trailers_tenant_id", table_name="trailers")
        op.drop_table("trailers")

    if "trucks" in tables:
        if _constraint_exists(conn, "trucks", "fk_trucks_owner_person_to_people"):
            op.drop_constraint(
                "fk_trucks_owner_person_to_people",
                "trucks",
                type_="foreignkey",
            )
        op.drop_index("ix_trucks_plate_number", table_name="trucks")
        op.drop_index("ix_trucks_vin", table_name="trucks")
        op.drop_index("ix_trucks_unit_number", table_name="trucks")
        op.drop_index("ix_trucks_ownership_type", table_name="trucks")
        op.drop_index("ix_trucks_status", table_name="trucks")
        op.drop_index("ix_trucks_tenant_id", table_name="trucks")
        op.drop_table("trucks")
