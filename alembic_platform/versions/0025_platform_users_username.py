"""Add platform_users.username with case-insensitive global uniqueness.

Revision ID: 0025_platform_users_username
Revises: 0024_user_invites
Create Date: 2026-03-15

- Add username column (nullable for safe rollout)
- Make first_name, last_name nullable (invite flow uses username only)
- Backfill: move first_name to username for invite-flow rows (last_name empty)
- Unique index: LOWER(username) WHERE username IS NOT NULL (case-insensitive global)
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025_platform_users_username"
down_revision: Union[str, Sequence[str], None] = "0024_user_invites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add username column (nullable)
    op.add_column(
        "platform_users",
        sa.Column("username", sa.String(255), nullable=True),
    )
    op.create_index("ix_platform_users_username", "platform_users", ["username"], unique=False)

    # 2. Make first_name, last_name nullable
    op.alter_column(
        "platform_users",
        "first_name",
        existing_type=sa.String(100),
        nullable=True,
    )
    op.alter_column(
        "platform_users",
        "last_name",
        existing_type=sa.String(100),
        nullable=True,
    )

    # 3. Backfill: invite-flow users have first_name=display_name, last_name=''
    #    Move first_name -> username, clear first_name/last_name. Do not touch signup users.
    op.execute(
        sa.text("""
            UPDATE platform_users
            SET username = TRIM(first_name),
                first_name = NULL,
                last_name = NULL
            WHERE (TRIM(COALESCE(last_name, '')) = '')
              AND first_name IS NOT NULL
              AND TRIM(first_name) != ''
              AND username IS NULL
        """)
    )

    # 4. Case-insensitive global uniqueness (allows multiple NULLs)
    op.execute(
        sa.text("""
            CREATE UNIQUE INDEX uq_platform_users_username_lower
            ON platform_users (LOWER(username))
            WHERE username IS NOT NULL
        """)
    )


def downgrade() -> None:
    # Restore first_name from username before dropping column
    op.execute(
        sa.text("""
            UPDATE platform_users
            SET first_name = COALESCE(TRIM(username), ''),
                last_name = COALESCE(NULLIF(TRIM(last_name), ''), '')
            WHERE first_name IS NULL AND username IS NOT NULL
        """)
    )
    op.execute(
        sa.text("""
            UPDATE platform_users
            SET first_name = COALESCE(first_name, ''),
                last_name = COALESCE(last_name, '')
            WHERE first_name IS NULL OR last_name IS NULL
        """)
    )

    op.execute("DROP INDEX IF EXISTS uq_platform_users_username_lower")
    op.drop_index("ix_platform_users_username", table_name="platform_users")
    op.drop_column("platform_users", "username")

    op.alter_column(
        "platform_users",
        "first_name",
        existing_type=sa.String(100),
        nullable=False,
    )
    op.alter_column(
        "platform_users",
        "last_name",
        existing_type=sa.String(100),
        nullable=False,
    )
