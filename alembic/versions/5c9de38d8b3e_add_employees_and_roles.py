"""Add employees and employee_roles

Revision ID: 5c9de38d8b3e
Revises: 4b5c1a9c1d5f
Create Date: 2025-12-31 06:52:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "5c9de38d8b3e"
down_revision: Union[str, Sequence[str], None] = "4b5c1a9c1d5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("employee_code", sa.String(length=50), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_employees_tenant_code", "employees", ["tenant_id", "employee_code"], unique=True)
    op.create_index("ix_employees_email", "employees", ["email"], unique=False)
    op.create_index("ix_employees_tenant_id", "employees", ["tenant_id"], unique=False)

    op.create_table(
        "employee_roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_employee_roles_tenant_employee", "employee_roles", ["tenant_id", "employee_id"], unique=False)
    op.create_index("ix_employee_roles_role", "employee_roles", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_employee_roles_role", table_name="employee_roles")
    op.drop_index("ix_employee_roles_tenant_employee", table_name="employee_roles")
    op.drop_table("employee_roles")

    op.drop_index("ix_employees_tenant_id", table_name="employees")
    op.drop_index("ix_employees_email", table_name="employees")
    op.drop_index("ix_employees_tenant_code", table_name="employees")
    op.drop_table("employees")
