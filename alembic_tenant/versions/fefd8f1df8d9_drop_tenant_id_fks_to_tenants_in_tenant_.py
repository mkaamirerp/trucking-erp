"""Drop tenant_id FKs to tenants in tenant DB

Revision ID: fefd8f1df8d9
Revises: 168cb4699baf
Create Date: 2026-02-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "fefd8f1df8d9"
down_revision: Union[str, Sequence[str], None] = "168cb4699baf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fk_if_exists(table: str, constraint: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    tables = set(inspector.get_table_names())
    if table not in tables:
        return

    existing = {fk.get("name") for fk in inspector.get_foreign_keys(table)}
    if constraint in existing:
        op.drop_constraint(constraint, table, type_="foreignkey")


def upgrade() -> None:
    _drop_fk_if_exists("audit_log", "audit_log_tenant_id_fkey")
    _drop_fk_if_exists("brokers", "brokers_tenant_id_fkey")
    _drop_fk_if_exists("driver_document_files", "fk_driver_document_files_tenant_id")
    _drop_fk_if_exists("driver_documents", "fk_driver_documents_tenant_id")
    _drop_fk_if_exists("driver_onboarding_submissions", "driver_onboarding_submissions_tenant_id_fkey")
    _drop_fk_if_exists("driver_phones", "fk_driver_phones_tenant_id")
    _drop_fk_if_exists("drivers", "fk_drivers_tenant_id")
    _drop_fk_if_exists("loads", "loads_tenant_id_fkey")
    _drop_fk_if_exists("roles", "roles_tenant_id_fkey")
    _drop_fk_if_exists("trucks", "fk_trucks_tenant_id")
    _drop_fk_if_exists("users", "fk_users_tenant_id")


def downgrade() -> None:
    pass
