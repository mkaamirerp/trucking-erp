"""
Tenant Database Schema Validation

Validates that provisioned tenant DBs have the expected schema (tables, columns, constraints).
Prevents silent schema drift and catches migration conflicts early.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL


class SchemaValidationError(Exception):
    """Raised when tenant schema validation fails."""

    pass


def validate_tenant_schema(tenant_db_url: str) -> list[str]:
    """
    Validate that tenant DB has required tables and columns.

    Args:
        tenant_db_url: Async connection string (postgresql+asyncpg://...)

    Returns:
        List of error messages (empty = valid schema)

    Raises:
        SchemaValidationError: If validation cannot be performed
    """
    errors: list[str] = []

    # Convert async URL to sync for inspection
    if "postgresql+asyncpg://" in tenant_db_url:
        sync_url = tenant_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    else:
        sync_url = tenant_db_url

    try:
        engine = create_engine(sync_url, pool_pre_ping=True, pool_size=1, max_overflow=0)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names(schema="public"))

        # ---- Required tables ----
        required_tables = {
            "tenants",
            "people",
            "person_roles",
            "driver_profiles",
            "driver_onboarding_submissions",
        }
        missing_tables = required_tables - tables
        if missing_tables:
            errors.append(f"Missing required tables: {', '.join(sorted(missing_tables))}")

        # ---- Validate person_roles columns (common source of errors) ----
        if "person_roles" in tables:
            cols = {c["name"] for c in inspector.get_columns("person_roles", schema="public")}
            required_cols = {
                "id",
                "tenant_id",
                "person_id",
                "role_code",  # NOT "role"
                "is_primary",
                "is_active",
                "created_at",
                "updated_at",
            }
            missing_cols = required_cols - cols
            if missing_cols:
                errors.append(
                    f"person_roles table missing required columns: {', '.join(sorted(missing_cols))}"
                )

            # Check for legacy "role" column (should be "role_code")
            if "role" in cols and "role_code" not in cols:
                errors.append(
                    "person_roles has legacy 'role' column; expected 'role_code'. "
                    "Run: ALTER TABLE person_roles RENAME COLUMN role TO role_code;"
                )

        # ---- Validate people columns ----
        if "people" in tables:
            cols = {c["name"] for c in inspector.get_columns("people", schema="public")}
            required_cols = {
                "id",
                "tenant_id",
                "first_name",
                "last_name",
                "email",
                "is_active",
            }
            missing_cols = required_cols - cols
            if missing_cols:
                errors.append(f"people table missing required columns: {', '.join(sorted(missing_cols))}")

        # ---- Validate driver_profiles ----
        if "driver_profiles" in tables:
            cols = {c["name"] for c in inspector.get_columns("driver_profiles", schema="public")}
            required_cols = {"id", "tenant_id", "person_id", "is_active"}
            missing_cols = required_cols - cols
            if missing_cols:
                errors.append(
                    f"driver_profiles table missing required columns: {', '.join(sorted(missing_cols))}"
                )

        # ---- Check alembic_version exists ----
        if "alembic_version" not in tables:
            errors.append(
                "alembic_version table missing - tenant DB was not properly migrated with Alembic"
            )
        else:
            # Check that a version is set
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                row = result.fetchone()
                if not row:
                    errors.append("alembic_version table is empty - no migration version recorded")

        engine.dispose()

    except Exception as e:
        raise SchemaValidationError(f"Failed to validate tenant schema: {e}") from e

    return errors


def validate_tenant_schema_strict(tenant_db_url: str) -> None:
    """
    Validate tenant schema and raise exception if invalid.

    Use this in tenant provisioning to fail-closed.

    Raises:
        SchemaValidationError: If schema is invalid
    """
    errors = validate_tenant_schema(tenant_db_url)
    if errors:
        error_msg = "Tenant schema validation failed:\n  - " + "\n  - ".join(errors)
        error_msg += (
            "\n\nThis usually means migrations are out of sync or incomplete. "
            "Check for conflicting migrations with: ./scripts/check_migration_conflicts.sh"
        )
        raise SchemaValidationError(error_msg)
