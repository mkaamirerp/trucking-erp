"""Shared DDL for the two S1 commercial-snapshot revisions.

Apply exactly one sibling: s1_load_approved_snapshot_fmp or s1_load_approved_snapshot_x5.
Do not run alembic upgrade head on the split graph. No historical backfill.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade_load_approved_commercial_snapshots() -> None:
    # Commercial evidence exists on the DW-1/FMP line only. The x5 line has no
    # load_commercial_evidence table, so that sibling cannot take this FK.
    evidence_present = _has_table("load_commercial_evidence")
    if evidence_present:
        op.create_unique_constraint(
            "uq_load_commercial_evidence_tenant_id",
            "load_commercial_evidence",
            ["tenant_id", "id"],
        )
    evidence_fk = (
        sa.ForeignKeyConstraint(
            ["tenant_id", "commercial_evidence_id"],
            ["load_commercial_evidence.tenant_id", "load_commercial_evidence.id"],
            name="fk_load_approved_snapshots_evidence_tenant",
            ondelete="RESTRICT",
        )
        if evidence_present
        else None
    )
    op.create_table(
        "load_approved_commercial_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("load_id", sa.Integer(), nullable=False),
        sa.Column("milestone", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("load_concurrency_version", sa.Integer(), nullable=False),
        sa.Column("creation_source", sa.String(length=32), nullable=False),
        sa.Column("load_status_at_snapshot", sa.String(length=32), nullable=False),
        sa.Column("dispatcher_review_claim", sa.String(length=32), nullable=False),
        sa.Column("commercial_evidence_id", sa.BigInteger(), nullable=True),
        sa.Column("workspace_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_platform_user_id", sa.String(length=36), nullable=True),
        sa.Column("snapshot_taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "load_id",
            "milestone",
            "revision",
            name="uq_load_approved_snapshots_tenant_load_milestone_rev",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_load_approved_snapshots_load_tenant",
            ondelete="RESTRICT",
        ),
        *([evidence_fk] if evidence_fk is not None else []),
        sa.CheckConstraint(
            "milestone IN ('creation')",
            name="ck_load_approved_snapshots_milestone_creation",
        ),
        sa.CheckConstraint(
            "creation_source IN ('workspace_promotion', 'direct_create')",
            name="ck_load_approved_snapshots_creation_source",
        ),
        sa.CheckConstraint(
            "dispatcher_review_claim IN ('none', 'workspace_promotion_reviewed')",
            name="ck_load_approved_snapshots_review_claim",
        ),
        sa.CheckConstraint(
            "("
            "creation_source = 'direct_create' AND dispatcher_review_claim = 'none'"
            ") OR ("
            "creation_source = 'workspace_promotion' "
            "AND dispatcher_review_claim = 'workspace_promotion_reviewed'"
            ")",
            name="ck_load_approved_snapshots_claim_matches_source",
        ),
        sa.CheckConstraint(
            "(commercial_evidence_id IS NULL AND workspace_draft_id IS NULL) "
            "OR (creation_source = 'workspace_promotion')",
            name="ck_load_approved_snapshots_evidence_on_promotion",
        ),
    )
    op.create_index(
        "ix_load_approved_snapshots_tenant_load",
        "load_approved_commercial_snapshots",
        ["tenant_id", "load_id"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION load_approved_commercial_snapshots_deny_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'append_only:load_approved_commercial_snapshots';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER load_approved_commercial_snapshots_append_only
        BEFORE UPDATE OR DELETE ON load_approved_commercial_snapshots
        FOR EACH ROW
        EXECUTE PROCEDURE load_approved_commercial_snapshots_deny_mutation();
        """
    )


def downgrade_load_approved_commercial_snapshots() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS load_approved_commercial_snapshots_append_only "
        "ON load_approved_commercial_snapshots"
    )
    op.execute("DROP FUNCTION IF EXISTS load_approved_commercial_snapshots_deny_mutation()")
    op.drop_index(
        "ix_load_approved_snapshots_tenant_load",
        table_name="load_approved_commercial_snapshots",
    )
    op.drop_table("load_approved_commercial_snapshots")
    if _has_table("load_commercial_evidence"):
        names = {
            item["name"]
            for item in sa.inspect(op.get_bind()).get_unique_constraints("load_commercial_evidence")
        }
        if "uq_load_commercial_evidence_tenant_id" in names:
            op.drop_constraint(
                "uq_load_commercial_evidence_tenant_id",
                "load_commercial_evidence",
                type_="unique",
            )
