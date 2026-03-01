"""Add tenant_forbidden_tables guardrail view (read-only list of platform-only table names)

Revision ID: d7e8f9a0b1c2
Revises: b5c6d7e8f9a0
Create Date: 2026-02-23

Tenant-only. Creates a view that lists table names that must NOT exist in tenant DB.
No data changes. Safe for all existing tenants.
"""

from __future__ import annotations

from alembic import op

revision = "d7e8f9a0b1c2"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None

VIEW_SQL = """
CREATE OR REPLACE VIEW public.tenant_forbidden_tables AS
SELECT tablename
FROM pg_catalog.pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
    -- Platform-only tables (must NOT exist in tenant DB)
    'platform_tenants',
    'platform_users',
    'platform_subscriptions',
    'platform_company_profiles',
    'platform_onboarding_payloads',
    'platform_otp_tokens',
    'platform_security_events',
    'platform_workspace_claims',
    'reserved_slugs',
    'slug_reservations',
    'signup_attempts',
    'signup_otp_tokens',
    'tenant_memberships'
  )
"""


def upgrade() -> None:
    op.execute(VIEW_SQL.strip())


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public.tenant_forbidden_tables")
