"""Add tenants + RBAC tables and seed defaults

Revision ID: c8a3d0b9c777
Revises: b2c8a2b3bd7a
Create Date: 2025-12-31 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8a3d0b9c777"
down_revision: Union[str, Sequence[str], None] = "b2c8a2b3bd7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---- Seed data (canonical permissions + role maps) ----
PERMISSIONS: dict[str, str] = {
    # Auth
    "auth.login": "Log in",
    "auth.logout": "Log out",
    "auth.password.change": "Change password",
    "auth.password.reset.request": "Request password reset",
    "auth.password.reset.perform": "Perform password reset",
    # Users / roles / perms
    "users.read": "View users",
    "users.create": "Create users",
    "users.update": "Update users",
    "users.deactivate": "Deactivate users",
    "users.roles.assign": "Assign roles",
    "roles.read": "Read roles",
    "roles.create": "Create roles",
    "roles.update": "Update roles",
    "roles.delete": "Delete roles",
    "permissions.read": "Read permissions",
    # Tenant settings / integrations
    "tenant.read": "View tenant settings",
    "tenant.update": "Update tenant settings",
    "integrations.read": "View integrations",
    "integrations.manage": "Manage integrations",
    "webhooks.read": "View webhooks",
    "webhooks.manage": "Manage webhooks",
    # Drivers & compliance docs
    "drivers.read": "View drivers",
    "drivers.create": "Create drivers",
    "drivers.update": "Update drivers",
    "drivers.deactivate": "Deactivate drivers",
    "driver_docs.read": "View driver documents",
    "driver_docs.upload": "Upload driver documents",
    "driver_docs.delete": "Delete driver documents",
    "compliance.read": "View compliance",
    "compliance.manage": "Manage compliance",
    # Trucks / trailers / assets
    "trucks.read": "View trucks",
    "trucks.create": "Create trucks",
    "trucks.update": "Update trucks",
    "trucks.deactivate": "Deactivate trucks",
    "trailers.read": "View trailers",
    "trailers.create": "Create trailers",
    "trailers.update": "Update trailers",
    "trailers.deactivate": "Deactivate trailers",
    # Loads / dispatch
    "loads.read": "View loads",
    "loads.create": "Create loads",
    "loads.update": "Update loads",
    "loads.cancel": "Cancel loads",
    "loads.assign": "Assign loads",
    "loads.rate.view": "View load rates",
    "loads.rate.edit": "Edit load rates",
    "dispatch.board.view": "View dispatch board",
    "dispatch.board.edit": "Edit dispatch board",
    # Maintenance
    "maintenance.read": "View maintenance",
    "maintenance.create": "Create maintenance items",
    "maintenance.update": "Update maintenance items",
    "maintenance.close": "Close maintenance items",
    "maintenance.cost.view": "View maintenance costs",
    "maintenance.cost.edit": "Edit maintenance costs",
    # Payroll
    "payroll.read": "View payroll",
    "payroll.run": "Run payroll",
    "payroll.adjust": "Adjust payroll",
    "payroll.export": "Export payroll",
    # Accounting / invoicing
    "accounting.read": "View accounting",
    "accounting.manage": "Manage accounting",
    "invoices.read": "View invoices",
    "invoices.create": "Create invoices",
    "invoices.update": "Update invoices",
    "invoices.send": "Send invoices",
    "payments.read": "View payments",
    "payments.record": "Record payments",
    "expenses.read": "View expenses",
    "expenses.create": "Create expenses",
    "expenses.update": "Update expenses",
    "expenses.approve": "Approve expenses",
    # Reporting / exports
    "reports.read": "Read reports",
    "reports.export": "Export reports",
    # Platform-only
    "platform.tenants.create": "Create tenants (platform)",
    "platform.tenants.update": "Update tenants (platform)",
    "platform.tenants.delete": "Delete tenants (platform)",
    "platform.users.manage": "Manage platform users",
    "platform.billing.manage": "Manage platform billing",
    "platform.domains.manage": "Manage platform domains",
    "platform.infra.manage": "Manage platform infrastructure",
    "platform.impersonate": "Impersonate tenant users",
}

PLATFORM_ONLY_KEYS = {
    "platform.tenants.create",
    "platform.tenants.update",
    "platform.tenants.delete",
    "platform.users.manage",
    "platform.billing.manage",
    "platform.domains.manage",
    "platform.infra.manage",
    "platform.impersonate",
}

TENANT_PERMISSION_KEYS = [k for k in PERMISSIONS.keys() if k not in PLATFORM_ONLY_KEYS]

ROLE_DEFS = [
    # Platform scope
    {"name": "PLATFORM_OWNER", "scope": "platform", "perms": ["*"], "tenant_id": None, "is_system": True},
    {
        "name": "PLATFORM_ADMIN",
        "scope": "platform",
        "perms": ["platform.tenants.create", "platform.tenants.update", "platform.users.manage", "platform.impersonate"],
        "tenant_id": None,
        "is_system": True,
    },
    {
        "name": "PLATFORM_SUPPORT",
        "scope": "platform",
        "perms": ["platform.impersonate"],
        "tenant_id": None,
        "is_system": True,
    },
    # Tenant scope templates (tenant_id=None acts as templates that will be cloned per-tenant)
    {"name": "TENANT_SUPER_ADMIN", "scope": "tenant", "perms": ["TENANT_ALL"], "tenant_id": None, "is_system": True},
    {
        "name": "TENANT_ADMIN",
        "scope": "tenant",
        "perms": [
            "users.read",
            "users.create",
            "users.update",
            "users.deactivate",
            "users.roles.assign",
            "roles.read",
            "tenant.read",
            "tenant.update",
            "drivers.read",
            "loads.read",
            "reports.read",
        ],
        "tenant_id": None,
        "is_system": True,
    },
    {
        "name": "DISPATCH",
        "scope": "tenant",
        "perms": [
            "drivers.read",
            "loads.read",
            "loads.create",
            "loads.update",
            "loads.cancel",
            "loads.assign",
            "dispatch.board.view",
            "dispatch.board.edit",
            "loads.rate.view",
        ],
        "tenant_id": None,
        "is_system": True,
    },
    {
        "name": "PAYROLL",
        "scope": "tenant",
        "perms": [
            "drivers.read",
            "payroll.read",
            "payroll.run",
            "payroll.adjust",
            "payroll.export",
            "reports.read",
            "reports.export",
        ],
        "tenant_id": None,
        "is_system": True,
    },
    {
        "name": "SAFETY_COMPLIANCE",
        "scope": "tenant",
        "perms": [
            "drivers.read",
            "driver_docs.read",
            "driver_docs.upload",
            "compliance.read",
            "compliance.manage",
            "reports.read",
            "reports.export",
        ],
        "tenant_id": None,
        "is_system": True,
    },
    {
        "name": "MAINTENANCE",
        "scope": "tenant",
        "perms": [
            "trucks.read",
            "trucks.update",
            "trailers.read",
            "trailers.update",
            "maintenance.read",
            "maintenance.create",
            "maintenance.update",
            "maintenance.close",
            "maintenance.cost.view",
        ],
        "tenant_id": None,
        "is_system": True,
    },
    {
        "name": "ACCOUNTING",
        "scope": "tenant",
        "perms": [
            "accounting.read",
            "accounting.manage",
            "invoices.read",
            "invoices.create",
            "invoices.update",
            "invoices.send",
            "payments.read",
            "payments.record",
            "expenses.read",
            "expenses.create",
            "expenses.update",
            "expenses.approve",
            "reports.read",
            "reports.export",
        ],
        "tenant_id": None,
        "is_system": True,
    },
    {
        "name": "PORTAL_ADMIN",
        "scope": "tenant",
        "perms": ["users.read", "users.create", "users.update", "users.deactivate"],
        "tenant_id": None,
        "is_system": True,
    },
    {
        "name": "PORTAL_VIEWER",
        "scope": "tenant",
        "perms": ["reports.read"],
        "tenant_id": None,
        "is_system": True,
    },
]


def seed_permissions(conn) -> dict[str, int]:
    for key, desc in PERMISSIONS.items():
        conn.execute(
            sa.text(
                "INSERT INTO permissions (key, description) VALUES (:key, :desc) "
                "ON CONFLICT (key) DO UPDATE SET description = EXCLUDED.description"
            ),
            {"key": key, "desc": desc},
        )
    rows = conn.execute(sa.text("SELECT id, key FROM permissions"))
    return {row.key: row.id for row in rows}


def resolve_permission_ids(permission_lookup: dict[str, int], requested: list[str]) -> list[int]:
    if "*" in requested:
        return list(permission_lookup.values())
    ids: list[int] = []
    expanded = requested
    if "TENANT_ALL" in requested:
        expanded = [k for k in TENANT_PERMISSION_KEYS if k in permission_lookup]
    for key in expanded:
        pid = permission_lookup.get(key)
        if pid:
            ids.append(pid)
    return ids


def seed_role(conn, permission_lookup: dict[str, int], role_def: dict) -> int:
    perm_ids = resolve_permission_ids(permission_lookup, role_def["perms"])
    result = conn.execute(
        sa.text(
            "INSERT INTO roles (name, scope, tenant_id, is_system, description) "
            "VALUES (:name, :scope, :tenant_id, :is_system, :description) "
            "ON CONFLICT (tenant_id, name) DO UPDATE SET description = EXCLUDED.description "
            "RETURNING id"
        ),
        {
            "name": role_def["name"],
            "scope": role_def["scope"],
            "tenant_id": role_def.get("tenant_id"),
            "is_system": role_def.get("is_system", False),
            "description": role_def.get("description"),
        },
    )
    role_id = result.scalar_one()
    for pid in perm_ids:
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id) "
                "ON CONFLICT DO NOTHING"
            ),
            {"role_id": role_id, "permission_id": pid},
        )
    return role_id


def clone_tenant_roles_from_templates(conn, tenant_id: int) -> None:
    templates = conn.execute(
        sa.text("SELECT id, name, description FROM roles WHERE scope = 'tenant' AND tenant_id IS NULL")
    ).fetchall()
    for template in templates:
        res = conn.execute(
            sa.text(
                "INSERT INTO roles (name, scope, tenant_id, is_system, description) "
                "VALUES (:name, 'tenant', :tenant_id, true, :description) "
                "ON CONFLICT (tenant_id, name) DO UPDATE SET description = EXCLUDED.description "
                "RETURNING id"
            ),
            {"name": template.name, "tenant_id": tenant_id, "description": template.description},
        )
        new_role_id = res.scalar_one()
        perm_rows = conn.execute(
            sa.text("SELECT permission_id FROM role_permissions WHERE role_id = :rid"), {"rid": template.id}
        ).fetchall()
        for row in perm_rows:
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"role_id": new_role_id, "permission_id": row.permission_id},
            )


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=False)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_permissions_key"),
    )
    op.create_index("ix_permissions_key", "permissions", ["key"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_perm"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"], unique=False)
    op.create_index("ix_role_permissions_perm_id", "role_permissions", ["permission_id"], unique=False)

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"], unique=False)
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=120), nullable=False),
        sa.Column("target_id", sa.String(length=120), nullable=True),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"], unique=False)
    op.create_index("ix_audit_log_actor_user_id", "audit_log", ["actor_user_id"], unique=False)

    # Users: scope + tenant_id + constraint
    op.add_column("users", sa.Column("scope", sa.String(length=20), nullable=True, server_default=sa.text("'tenant'")))
    op.add_column("users", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"], unique=False)
    op.create_foreign_key(
        "fk_users_tenant_id",
        "users",
        "tenants",
        local_cols=["tenant_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    # Tenant-owned tables: add tenant_id (nullable for now, tightened after backfill)
    op.add_column(
        "driver_document_files",
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "driver_document_files",
        sa.Column("deactivated_reason", sa.String(length=255), nullable=True),
    )
    for table_name in ("drivers", "driver_phones", "driver_documents", "driver_document_files", "trucks"):
        op.add_column(table_name, sa.Column("tenant_id", sa.Integer(), nullable=True))
        op.create_index(f"ix_{table_name}_tenant_id", table_name, ["tenant_id"], unique=False)
        op.create_foreign_key(
            f"fk_{table_name}_tenant_id", table_name, "tenants", local_cols=["tenant_id"], remote_cols=["id"], ondelete="CASCADE"
        )

    # ---- Data backfill + seeds ----
    conn = op.get_bind()

    permission_lookup = seed_permissions(conn)
    for role_def in ROLE_DEFS:
        seed_role(conn, permission_lookup, role_def)

    tenant_id = conn.execute(
        sa.text(
            "INSERT INTO tenants (name, slug, status) VALUES (:name, :slug, 'active') "
            "ON CONFLICT (slug) DO UPDATE SET status = EXCLUDED.status, name = EXCLUDED.name "
            "RETURNING id"
        ),
        {"name": "Demo Fleet", "slug": "demo-fleet"},
    ).scalar_one()

    clone_tenant_roles_from_templates(conn, tenant_id)

    # Backfill existing data into the default tenant
    conn.execute(sa.text("UPDATE users SET scope = 'tenant' WHERE scope IS NULL"))
    conn.execute(sa.text("UPDATE users SET tenant_id = :tid WHERE tenant_id IS NULL"), {"tid": tenant_id})

    for table in ("drivers", "driver_phones", "driver_documents", "driver_document_files", "trucks"):
        conn.execute(sa.text(f"UPDATE {table} SET tenant_id = :tid WHERE tenant_id IS NULL"), {"tid": tenant_id})

    # Ensure at least one tenant super admin
    super_admin_role_id = conn.execute(
        sa.text("SELECT id FROM roles WHERE tenant_id = :tid AND name = 'TENANT_SUPER_ADMIN'"), {"tid": tenant_id}
    ).scalar_one()
    user_ids = [row.id for row in conn.execute(sa.text("SELECT id FROM users WHERE tenant_id = :tid"), {"tid": tenant_id})]
    for uid in user_ids:
        conn.execute(
            sa.text(
                "INSERT INTO user_roles (user_id, role_id) VALUES (:uid, :rid) "
                "ON CONFLICT (user_id, role_id) DO NOTHING"
            ),
            {"uid": uid, "rid": super_admin_role_id},
        )

    # Tighten nullability for tenant-owned tables
    for table_name in ("drivers", "driver_phones", "driver_documents", "driver_document_files", "trucks"):
        op.alter_column(table_name, "tenant_id", existing_type=sa.Integer(), nullable=False)

    op.create_check_constraint(
        "ck_users_scope_tenant_match",
        "users",
        "(scope = 'platform' AND tenant_id IS NULL) OR (scope = 'tenant' AND tenant_id IS NOT NULL)",
    )
    op.alter_column("users", "scope", existing_type=sa.String(length=20), nullable=False, server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_users_scope_tenant_match", "users", type_="check")
    op.drop_constraint("fk_users_tenant_id", "users", type_="foreignkey")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_column("users", "tenant_id")
    op.drop_column("users", "scope")

    for table_name in ("driver_document_files", "driver_documents", "driver_phones", "drivers", "trucks"):
        op.drop_constraint(f"fk_{table_name}_tenant_id", table_name, type_="foreignkey")
        op.drop_index(f"ix_{table_name}_tenant_id", table_name=table_name)
        op.drop_column(table_name, "tenant_id")

    op.drop_column("driver_document_files", "deactivated_reason")
    op.drop_column("driver_document_files", "deactivated_at")

    op.drop_index("ix_audit_log_actor_user_id", table_name="audit_log")
    op.drop_index("ix_audit_log_tenant_id", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_index("ix_role_permissions_perm_id", table_name="role_permissions")
    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_table("role_permissions")

    op.drop_table("roles")
    op.drop_index("ix_permissions_key", table_name="permissions")
    op.drop_table("permissions")

    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
