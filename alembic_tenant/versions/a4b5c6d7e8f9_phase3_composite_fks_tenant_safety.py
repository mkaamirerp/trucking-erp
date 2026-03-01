"""Phase 3 composite FK enforcement (tenant safety) — runbook 3.1–3.5

Revision ID: a4b5c6d7e8f9
Revises: fefd8f1df8d9
Create Date: 2026-02-23

Implements:
- 3.1: UNIQUE(tenant_id, id) on drivers, brokers, driver_documents
- 3.2: driver_documents(tenant_id, driver_id) → drivers(tenant_id, id)
- 3.3: driver_document_files(tenant_id, driver_document_id) → driver_documents(tenant_id, id)
- 3.4: loads(tenant_id, broker_id) → brokers(tenant_id, id)
- 3.5: loads(tenant_id, driver_id) → drivers(tenant_id, id)

Idempotent: safe if constraints already exist (IF EXISTS / exception handling).
Constraint names match runbook/remediation plan.
"""
from __future__ import annotations

from alembic import op

# revision identifiers
revision = "a4b5c6d7e8f9"
down_revision = "fefd8f1df8d9"
branch_labels = None
depends_on = None


def _add_unique_if_not_exists(table: str, constraint: str, columns: list[str]) -> None:
    """Idempotent: add UNIQUE constraint only if it does not exist."""
    cols = ", ".join(columns)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                WHERE c.conname = '{constraint}' AND t.relname = '{table}'
            ) THEN
                ALTER TABLE {table} ADD CONSTRAINT {constraint} UNIQUE ({cols});
            END IF;
        END $$;
        """
    )


def _add_fk_if_not_exists(
    table: str,
    constraint: str,
    columns: list[str],
    ref_table: str,
    ref_columns: list[str],
    ondelete: str = "CASCADE",
) -> None:
    """Idempotent: add FK only if it does not exist."""
    cols = ", ".join(columns)
    ref_cols = ", ".join(ref_columns)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                WHERE c.conname = '{constraint}' AND t.relname = '{table}'
            ) THEN
                ALTER TABLE {table} ADD CONSTRAINT {constraint}
                    FOREIGN KEY ({cols}) REFERENCES {ref_table} ({ref_cols}) ON DELETE {ondelete};
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    # ----- 3.1 Add UNIQUE(tenant_id, id) on drivers, brokers, driver_documents -----
    _add_unique_if_not_exists("drivers", "uq_drivers_tenant_id_id", ["tenant_id", "id"])
    _add_unique_if_not_exists("brokers", "uq_brokers_tenant_id_id", ["tenant_id", "id"])
    _add_unique_if_not_exists(
        "driver_documents", "uq_driver_documents_tenant_id_id", ["tenant_id", "id"]
    )

    # ----- 3.2 driver_documents: drop single-column FK, add composite FK -----
    op.execute(
        "ALTER TABLE driver_documents DROP CONSTRAINT IF EXISTS fk_driver_documents_driver_id;"
    )
    _add_fk_if_not_exists(
        "driver_documents",
        "fk_driver_documents_tenant_driver_to_drivers",
        ["tenant_id", "driver_id"],
        "drivers",
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )

    # ----- 3.3 driver_document_files: drop single-column FK, add composite FK -----
    op.execute(
        "ALTER TABLE driver_document_files "
        "DROP CONSTRAINT IF EXISTS fk_driver_document_files_driver_document_id;"
    )
    _add_fk_if_not_exists(
        "driver_document_files",
        "fk_driver_document_files_tenant_doc_to_driver_documents",
        ["tenant_id", "driver_document_id"],
        "driver_documents",
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )

    # ----- 3.4 loads: drop broker FK, add composite FK -----
    op.execute("ALTER TABLE loads DROP CONSTRAINT IF EXISTS loads_broker_id_fkey;")
    _add_fk_if_not_exists(
        "loads",
        "fk_loads_tenant_broker_to_brokers",
        ["tenant_id", "broker_id"],
        "brokers",
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    # ----- 3.5 loads: drop driver FK, add composite FK -----
    op.execute("ALTER TABLE loads DROP CONSTRAINT IF EXISTS loads_driver_id_fkey;")
    _add_fk_if_not_exists(
        "loads",
        "fk_loads_tenant_driver_to_drivers",
        ["tenant_id", "driver_id"],
        "drivers",
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # ----- Reverse 3.5: drop composite FK on loads (driver), recreate single-column FK -----
    op.execute(
        "ALTER TABLE loads DROP CONSTRAINT IF EXISTS fk_loads_tenant_driver_to_drivers;"
    )
    op.execute(
        """
        ALTER TABLE loads ADD CONSTRAINT loads_driver_id_fkey
            FOREIGN KEY (driver_id) REFERENCES drivers(id) ON DELETE SET NULL;
        """
    )

    # ----- Reverse 3.4: drop composite FK on loads (broker), recreate single-column FK -----
    op.execute(
        "ALTER TABLE loads DROP CONSTRAINT IF EXISTS fk_loads_tenant_broker_to_brokers;"
    )
    op.execute(
        """
        ALTER TABLE loads ADD CONSTRAINT loads_broker_id_fkey
            FOREIGN KEY (broker_id) REFERENCES brokers(id) ON DELETE RESTRICT;
        """
    )

    # ----- Reverse 3.3: drop composite FK on driver_document_files, recreate single-column FK -----
    op.execute(
        "ALTER TABLE driver_document_files "
        "DROP CONSTRAINT IF EXISTS fk_driver_document_files_tenant_doc_to_driver_documents;"
    )
    op.execute(
        """
        ALTER TABLE driver_document_files
            ADD CONSTRAINT fk_driver_document_files_driver_document_id
            FOREIGN KEY (driver_document_id) REFERENCES driver_documents(id) ON DELETE CASCADE;
        """
    )

    # ----- Reverse 3.2: drop composite FK on driver_documents, recreate single-column FK -----
    op.execute(
        "ALTER TABLE driver_documents "
        "DROP CONSTRAINT IF EXISTS fk_driver_documents_tenant_driver_to_drivers;"
    )
    op.execute(
        """
        ALTER TABLE driver_documents
            ADD CONSTRAINT fk_driver_documents_driver_id
            FOREIGN KEY (driver_id) REFERENCES drivers(id) ON DELETE CASCADE;
        """
    )

    # ----- Reverse 3.1: drop UNIQUE(tenant_id, id) on driver_documents, brokers, drivers -----
    op.execute(
        "ALTER TABLE driver_documents DROP CONSTRAINT IF EXISTS uq_driver_documents_tenant_id_id;"
    )
    op.execute("ALTER TABLE brokers DROP CONSTRAINT IF EXISTS uq_brokers_tenant_id_id;")
    op.execute("ALTER TABLE drivers DROP CONSTRAINT IF EXISTS uq_drivers_tenant_id_id;")
