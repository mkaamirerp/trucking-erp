"""person_applications: current_workflow_lane (queue routing vs historical status).

Revision ID: r8a9b0c1d2e3
Revises: q2w3e4r5t6y7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r8a9b0c1d2e3"
down_revision = "q2w3e4r5t6y7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "person_applications",
        sa.Column("current_workflow_lane", sa.String(length=32), nullable=True),
    )
    # Terminal / truth-derived rows first
    op.execute(
        """
        UPDATE person_applications
        SET current_workflow_lane = 'rejected'
        WHERE status = 'REJECTED'
        """
    )
    op.execute(
        """
        UPDATE person_applications
        SET current_workflow_lane = 'complete'
        WHERE setup_status = 'complete' OR onboarded_at IS NOT NULL
        """
    )
    # APPROVED but not fully onboarded: default to manager-owned processing (combined-default).
    # Segmented tenants get hr_payroll on next list load or person_setup_ui_mode patch reconcile.
    op.execute(
        """
        UPDATE person_applications
        SET current_workflow_lane = 'processing'
        WHERE current_workflow_lane IS NULL
          AND status = 'APPROVED'
        """
    )
    op.execute(
        """
        UPDATE person_applications
        SET current_workflow_lane = 'submitted'
        WHERE current_workflow_lane IS NULL
          AND status = 'SUBMITTED'
          AND reviewed_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE person_applications
        SET current_workflow_lane = 'processing'
        WHERE current_workflow_lane IS NULL
          AND status = 'SUBMITTED'
          AND reviewed_at IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE person_applications
        SET current_workflow_lane = 'processing'
        WHERE current_workflow_lane IS NULL
          AND status = 'DRAFT'
        """
    )
    op.execute(
        """
        UPDATE person_applications
        SET current_workflow_lane = 'processing'
        WHERE current_workflow_lane IS NULL
        """
    )
    op.alter_column(
        "person_applications",
        "current_workflow_lane",
        nullable=False,
        server_default=sa.text("'processing'"),
    )


def downgrade() -> None:
    op.drop_column("person_applications", "current_workflow_lane")
