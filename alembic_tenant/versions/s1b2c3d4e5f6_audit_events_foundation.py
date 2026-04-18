"""Tenant-wide audit_events foundation (append-only).

Revision ID: s1b2c3d4e5f6
Revises: r8a9b0c1d2e3
Create Date: 2026-04-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s1b2c3d4e5f6"
down_revision = "r8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_label", sa.String(length=128), nullable=True),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("entity_label", sa.String(length=256), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("subaction", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("reason_note", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default="normal"),
        sa.Column("changed_fields", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("snapshot_before", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("snapshot_after", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("context_json", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Backfill-proof: allow idempotent migration from legacy tenant_audit_logs.
        sa.Column("legacy_tenant_audit_log_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "actor_type in ('user','system','api','webhook','job','import')",
            name="ck_audit_events_actor_type",
        ),
        sa.CheckConstraint(
            "source in ('ui','api','background_job','webhook','import','system_rule')",
            name="ck_audit_events_source",
        ),
        sa.CheckConstraint(
            "visibility in ('normal','sensitive','admin_sensitive','finance_sensitive')",
            name="ck_audit_events_visibility",
        ),
        sa.CheckConstraint("length(entity_id) > 0", name="ck_audit_events_entity_id_nonempty"),
        sa.CheckConstraint("length(entity_type) > 0", name="ck_audit_events_entity_type_nonempty"),
        sa.CheckConstraint("length(module) > 0", name="ck_audit_events_module_nonempty"),
        sa.CheckConstraint("length(action) > 0", name="ck_audit_events_action_nonempty"),
    )

    op.create_index(
        "ix_audit_events_tenant_entity_time",
        "audit_events",
        ["tenant_id", "entity_type", "entity_id", sa.text("event_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_audit_events_tenant_module_time",
        "audit_events",
        ["tenant_id", "module", sa.text("event_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_audit_events_tenant_actor_time",
        "audit_events",
        ["tenant_id", "actor_user_id", sa.text("event_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("actor_user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_audit_events_tenant_correlation_time",
        "audit_events",
        ["tenant_id", "correlation_id", sa.text("event_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("correlation_id IS NOT NULL"),
    )
    op.create_index(
        "ux_audit_events_legacy_tenant_audit_log_id",
        "audit_events",
        ["legacy_tenant_audit_log_id"],
        unique=True,
        postgresql_where=sa.text("legacy_tenant_audit_log_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_audit_events_legacy_tenant_audit_log_id", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_correlation_time", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_actor_time", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_module_time", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_entity_time", table_name="audit_events")
    op.drop_table("audit_events")

