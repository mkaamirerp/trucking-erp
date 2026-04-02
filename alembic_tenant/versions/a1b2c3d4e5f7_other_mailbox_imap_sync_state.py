"""Other IMAP mailbox: reply-to, security modes, sync cursor, test/sync timestamps.

Revision ID: a1b2c3d4e5f7
Revises: z1a2b3c4d5e6
Create Date: 2026-03-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "z1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenant_email_mailboxes", sa.Column("reply_to", sa.String(255), nullable=True))
    op.add_column("tenant_email_mailboxes", sa.Column("imap_security", sa.String(16), nullable=True))
    op.add_column("tenant_email_mailboxes", sa.Column("smtp_security", sa.String(16), nullable=True))
    op.add_column("tenant_email_mailboxes", sa.Column("connection_status", sa.String(32), nullable=True))
    op.add_column(
        "tenant_email_mailboxes",
        sa.Column("last_inbound_test_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenant_email_mailboxes",
        sa.Column("last_outbound_test_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("tenant_email_mailboxes", sa.Column("last_sync_status", sa.String(32), nullable=True))
    op.add_column("tenant_email_mailboxes", sa.Column("last_sync_error", sa.Text(), nullable=True))
    op.add_column("tenant_email_mailboxes", sa.Column("imap_uidvalidity", sa.BigInteger(), nullable=True))
    op.add_column("tenant_email_mailboxes", sa.Column("imap_last_seen_uid", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenant_email_mailboxes", "imap_last_seen_uid")
    op.drop_column("tenant_email_mailboxes", "imap_uidvalidity")
    op.drop_column("tenant_email_mailboxes", "last_sync_error")
    op.drop_column("tenant_email_mailboxes", "last_sync_status")
    op.drop_column("tenant_email_mailboxes", "last_outbound_test_at")
    op.drop_column("tenant_email_mailboxes", "last_inbound_test_at")
    op.drop_column("tenant_email_mailboxes", "connection_status")
    op.drop_column("tenant_email_mailboxes", "smtp_security")
    op.drop_column("tenant_email_mailboxes", "imap_security")
    op.drop_column("tenant_email_mailboxes", "reply_to")
