"""Shared DDL for the revised rate-confirmation history.

The two sibling revisions import these helpers. Apply exactly one sibling on a
database. The original rate confirmation stays in load_commercial_evidence as
revision 0 and is not a row in this table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade_load_rate_confirmation_revisions() -> None:
    if _has_table("load_rate_confirmation_revisions"):
        return
    op.create_table(
        "load_rate_confirmation_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("load_id", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("new_parse_json", postgresql.JSONB(), nullable=False),
        sa.Column("accepted_changes_json", postgresql.JSONB(), nullable=False),
        sa.Column("compare_notices_json", postgresql.JSONB(), nullable=False),
        sa.Column("accepted_by_platform_user_id", sa.String(length=36), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_load_rc_revisions_number_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_load_rc_revisions_load",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "load_id",
            "revision_number",
            name="uq_load_rc_revisions_tenant_load_number",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "load_id",
            "file_sha256",
            name="uq_load_rc_revisions_tenant_load_sha",
        ),
    )
    op.create_index(
        "uq_load_rc_revisions_one_current",
        "load_rate_confirmation_revisions",
        ["tenant_id", "load_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_load_rate_confirmation_revision_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'append_only:load_rate_confirmation_revisions';
            END IF;
            IF OLD.is_current IS TRUE
               AND NEW.is_current IS FALSE
               AND NEW.id IS NOT DISTINCT FROM OLD.id
               AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
               AND NEW.load_id IS NOT DISTINCT FROM OLD.load_id
               AND NEW.revision_number IS NOT DISTINCT FROM OLD.revision_number
               AND NEW.file_sha256 IS NOT DISTINCT FROM OLD.file_sha256
               AND NEW.storage_key IS NOT DISTINCT FROM OLD.storage_key
               AND NEW.filename IS NOT DISTINCT FROM OLD.filename
               AND NEW.new_parse_json IS NOT DISTINCT FROM OLD.new_parse_json
               AND NEW.accepted_changes_json IS NOT DISTINCT FROM OLD.accepted_changes_json
               AND NEW.compare_notices_json IS NOT DISTINCT FROM OLD.compare_notices_json
               AND NEW.accepted_by_platform_user_id IS NOT DISTINCT FROM OLD.accepted_by_platform_user_id
               AND NEW.accepted_at IS NOT DISTINCT FROM OLD.accepted_at
            THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'append_only:load_rate_confirmation_revisions';
        END;
        $$;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS load_rate_confirmation_revisions_append_only
            ON load_rate_confirmation_revisions;
        CREATE TRIGGER load_rate_confirmation_revisions_append_only
            BEFORE UPDATE OR DELETE ON load_rate_confirmation_revisions
            FOR EACH ROW
            EXECUTE PROCEDURE reject_load_rate_confirmation_revision_mutation();
        """
    )


def downgrade_load_rate_confirmation_revisions() -> None:
    if not _has_table("load_rate_confirmation_revisions"):
        return
    op.execute(
        "DROP TRIGGER IF EXISTS load_rate_confirmation_revisions_append_only "
        "ON load_rate_confirmation_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_load_rate_confirmation_revision_mutation()")
    op.drop_index(
        "uq_load_rc_revisions_one_current",
        table_name="load_rate_confirmation_revisions",
    )
    op.drop_table("load_rate_confirmation_revisions")
