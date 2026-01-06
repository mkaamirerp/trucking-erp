"""Add unique constraint per tenant/employee/role

Revision ID: 7f8e2b1e7e7f
Revises: 5c9de38d8b3e
Create Date: 2025-12-31 07:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f8e2b1e7e7f"
down_revision: Union[str, Sequence[str], None] = "5c9de38d8b3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_employee_roles_tenant_employee_role",
        "employee_roles",
        ["tenant_id", "employee_id", "role"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_employee_roles_tenant_employee_role", table_name="employee_roles")
