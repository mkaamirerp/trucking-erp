"""Revised rate confirmation history on the x5 branch.

Sibling of rc01_rate_con_revision_fmp. Never apply both.
"""

from alembic_tenant.load_rate_confirmation_revision_ddl import (
    downgrade_load_rate_confirmation_revisions,
    upgrade_load_rate_confirmation_revisions,
)

revision = "rc01_rate_con_revision_x5"
down_revision = "s1_load_approved_snapshot_x5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    upgrade_load_rate_confirmation_revisions()


def downgrade() -> None:
    downgrade_load_rate_confirmation_revisions()
