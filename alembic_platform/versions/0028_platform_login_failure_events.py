"""platform_login_failure_events for operator login diagnostics (platform DB only).

Revision ID: 0028_platform_login_failure_events
Revises: 0027_tenant_auth_mode
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0028_platform_login_failure_events"
down_revision: Union[str, Sequence[str], None] = "0027_tenant_auth_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "platform_login_failure_events"
_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ix_platform_login_failure_events_created_at", ("created_at",)),
    ("ix_platform_login_failure_events_tenant_id", ("tenant_id",)),
    ("ix_platform_login_failure_events_reason_code", ("reason_code",)),
    ("ix_platform_login_failure_events_email_fingerprint", ("email_fingerprint",)),
)


def _ensure_secondary_indexes(bind) -> None:
    insp = inspect(bind)
    if not insp.has_table(_TABLE):
        return
    existing = {idx["name"] for idx in insp.get_indexes(_TABLE)}
    for ix_name, columns in _INDEXES:
        if ix_name in existing:
            continue
        op.create_index(ix_name, _TABLE, list(columns), unique=False)


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_slug", sa.String(length=63), nullable=False),
            sa.Column("tenant_auth_mode", sa.String(length=20), nullable=False),
            sa.Column("reason_code", sa.String(length=64), nullable=False),
            sa.Column("email_fingerprint", sa.String(length=32), nullable=False),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("request_host", sa.String(length=255), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["platform_tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    _ensure_secondary_indexes(bind)


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(_TABLE):
        return
    existing = {idx["name"] for idx in insp.get_indexes(_TABLE)}
    for ix_name, _ in reversed(_INDEXES):
        if ix_name in existing:
            op.drop_index(ix_name, table_name=_TABLE)
    op.drop_table(_TABLE)
