"""Retire LOAD_PAY and ALLOWANCE from assignable fuel charge catalog.

Revision ID: e3f4a5b6c7d8
Revises: d1e2f3a4b5c6

Segment B migration d1e2f3a4b5c6 seeded LOAD_PAY and ALLOWANCE for early Segment B/C work.
Application catalog is locked to 10 charge types + UNMAPPED; picker and validation exclude
LOAD_PAY/ALLOWANCE for new assignments.

This forward-only data migration:
- Deactivates category rows (does not DELETE — FK from fuel_provider_category_mapping).
- Deactivates active tenant mappings targeting those codes (no rewrite of txn classification strings).
- Does not change fuel_transactions.classification or classification_event history.

NOT applied on production until operator runs tenant_upgrade_head.sh.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e3f4a5b6c7d8"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

_RETIRED_CODES = ("LOAD_PAY", "ALLOWANCE")


def upgrade() -> None:
    bind = op.get_bind()
    codes_sql = ", ".join(f"'{c}'" for c in _RETIRED_CODES)
    bind.execute(
        sa.text(
            f"""
            UPDATE fuel_charge_category
            SET active = false, updated_at = now()
            WHERE code IN ({codes_sql})
            """
        )
    )
    bind.execute(
        sa.text(
            f"""
            UPDATE fuel_provider_category_mapping
            SET active = false, updated_at = now()
            WHERE canonical_category_code IN ({codes_sql})
              AND active IS TRUE
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    codes_sql = ", ".join(f"'{c}'" for c in _RETIRED_CODES)
    bind.execute(
        sa.text(
            f"""
            UPDATE fuel_charge_category
            SET active = true, updated_at = now()
            WHERE code IN ({codes_sql})
            """
        )
    )
    # Mapping rows are not auto-reactivated on downgrade (operator must review).
