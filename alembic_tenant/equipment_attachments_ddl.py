"""Shared DDL for the two alternative tenant equipment-association revisions.

Schema checkpoint ONLY. These are sibling branch revisions: apply precisely one
after confirming tenant Alembic lineage. No equipment history or owner backfill.
Do not run `alembic upgrade head` on the split graph.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


def upgrade_equipment_attachments() -> None:
    # The existing trucks(tenant_id, id) unique constraint is supplied by the
    # Fuel historical-resolution foundation. Drivers/trailers lack equivalents.
    op.create_unique_constraint(
        "uq_drivers_tenant_id_id", "drivers", ["tenant_id", "id"]
    )
    op.create_unique_constraint(
        "uq_trailers_tenant_id_id", "trailers", ["tenant_id", "id"]
    )

    op.create_table(
        "driver_equipment_defaults",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("driver_id", sa.Integer(), nullable=False),
        sa.Column("default_truck_id", sa.Integer(), nullable=True),
        sa.Column(
            "equipment_binding_mode",
            sa.String(length=24),
            nullable=False,
            server_default="pooled",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "driver_id", name="pk_driver_equipment_defaults"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "driver_id"],
            ["drivers.tenant_id", "drivers.id"],
            name="fk_equipment_defaults_driver_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "default_truck_id"],
            ["trucks.tenant_id", "trucks.id"],
            name="fk_equipment_defaults_truck_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "equipment_binding_mode IN ('dedicated', 'owner_bound', 'shift_based', 'pooled')",
            name="ck_equipment_defaults_binding_mode",
        ),
    )
    op.create_index(
        "ix_driver_equipment_defaults_tenant_truck",
        "driver_equipment_defaults",
        ["tenant_id", "default_truck_id"],
    )

    # A truck's current driver and currently hooked trailer are independent
    # nullable facts. Trip assignment and Trip completion never write this row.
    # One truck per driver and one truck per trailer are database-enforced.
    op.create_table(
        "equipment_current_attachments",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("truck_id", sa.Integer(), nullable=False),
        sa.Column("driver_id", sa.Integer(), nullable=True),
        sa.Column("trailer_id", sa.Integer(), nullable=True),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "truck_id", name="pk_equipment_current_attachments"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "truck_id"],
            ["trucks.tenant_id", "trucks.id"],
            name="fk_equipment_attachments_truck_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "driver_id"],
            ["drivers.tenant_id", "drivers.id"],
            name="fk_equipment_attachments_driver_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "trailer_id"],
            ["trailers.tenant_id", "trailers.id"],
            name="fk_equipment_attachments_trailer_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_equipment_attachments_version_positive"
        ),
    )
    op.create_index(
        "uq_equipment_current_tenant_driver",
        "equipment_current_attachments",
        ["tenant_id", "driver_id"],
        unique=True,
        postgresql_where=sa.text("driver_id IS NOT NULL"),
    )
    op.create_index(
        "uq_equipment_current_tenant_trailer",
        "equipment_current_attachments",
        ["tenant_id", "trailer_id"],
        unique=True,
        postgresql_where=sa.text("trailer_id IS NOT NULL"),
    )


def downgrade_equipment_attachments() -> None:
    # Destructive downgrade only for a disposable/empty test tenant; a later
    # data-bearing production rollback requires a separately approved plan.
    op.drop_index(
        "uq_equipment_current_tenant_trailer",
        table_name="equipment_current_attachments",
    )
    op.drop_index(
        "uq_equipment_current_tenant_driver",
        table_name="equipment_current_attachments",
    )
    op.drop_table("equipment_current_attachments")
    op.drop_index(
        "ix_driver_equipment_defaults_tenant_truck",
        table_name="driver_equipment_defaults",
    )
    op.drop_table("driver_equipment_defaults")
    op.drop_constraint(
        "uq_trailers_tenant_id_id", "trailers", type_="unique"
    )
    op.drop_constraint(
        "uq_drivers_tenant_id_id", "drivers", type_="unique"
    )
