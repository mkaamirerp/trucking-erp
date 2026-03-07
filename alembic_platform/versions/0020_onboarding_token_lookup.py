"""Backfill missing revision id for existing onboarding_token_lookup.

Dev drift fix: platform DB `alembic_version` points at `0020_onboarding_token_lookup`,
but the corresponding revision file was removed/renamed. This revision is a no-op
to restore a resolvable revision graph without changing schema/data.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401

revision: str = "0020_onboarding_token_lookup"
down_revision: Union[str, Sequence[str], None] = "0019_onboarding_token_lookup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op: schema already exists in platform DB in dev.
    pass


def downgrade() -> None:
    # No-op (avoid destructive drops during dev rollback).
    pass

