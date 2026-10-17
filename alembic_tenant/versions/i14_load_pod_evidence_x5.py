"""I14 V1: append-only Proof of Delivery evidence for tenants still at x5.

Same table as i14_load_pod_evidence. This revision is the x5 branch only.
Do not run it on a database that already applied i14_load_pod_evidence.

Revision ID: i14_load_pod_evidence_x5
Revises: x5y6z7a8b9c0
Create Date: 2026-10-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i14_load_pod_evidence_x5"
down_revision: Union[str, Sequence[str], None] = "x5y6z7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "load_pod_evidence",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("load_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_label", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_load_pod_evidence_load_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_load_pod_evidence_tenant_load",
        "load_pod_evidence",
        ["tenant_id", "load_id"],
        unique=False,
    )
    op.create_index(
        "ix_load_pod_evidence_tenant_id",
        "load_pod_evidence",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_load_pod_evidence_tenant_id", table_name="load_pod_evidence")
    op.drop_index("ix_load_pod_evidence_tenant_load", table_name="load_pod_evidence")
    op.drop_table("load_pod_evidence")
