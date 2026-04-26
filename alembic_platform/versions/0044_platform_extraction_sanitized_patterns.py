"""Platform extraction: sanitized cross-tenant learning patterns (no PII values).

Revision ID: 0044_platform_extraction_sanitized_patterns
Revises: 0043_platform_users_theme
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0044_platform_extraction_sanitized_patterns"
down_revision: Union[str, Sequence[str], None] = "0043_platform_users_theme"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_extraction_sanitized_patterns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("broker_family_key", sa.String(length=128), nullable=False),
        sa.Column("field_path", sa.String(length=256), nullable=False),
        sa.Column("source_label_pattern", sa.String(length=256), nullable=False),
        sa.Column("source_section_pattern", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("value_shape_class", sa.String(length=64), nullable=False),
        sa.Column("section_role", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("positive_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("maturity", sa.String(length=32), nullable=False, server_default="observation"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pesp_active", "platform_extraction_sanitized_patterns", ["is_active"])
    op.create_index("ix_pesp_broker_family", "platform_extraction_sanitized_patterns", ["broker_family_key"])
    op.create_index("ix_pesp_field_path", "platform_extraction_sanitized_patterns", ["field_path"])
    op.create_index("ix_pesp_value_shape", "platform_extraction_sanitized_patterns", ["value_shape_class"])
    op.create_index("ix_pesp_section_role", "platform_extraction_sanitized_patterns", ["section_role"])
    op.create_index("ix_pesp_maturity", "platform_extraction_sanitized_patterns", ["maturity"])
    op.create_index(
        "ix_pesp_unique_tuples",
        "platform_extraction_sanitized_patterns",
        [
            "broker_family_key",
            "field_path",
            "source_label_pattern",
            "source_section_pattern",
            "value_shape_class",
        ],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_pesp_unique_tuples", table_name="platform_extraction_sanitized_patterns")
    op.drop_index("ix_pesp_maturity", table_name="platform_extraction_sanitized_patterns")
    op.drop_index("ix_pesp_section_role", table_name="platform_extraction_sanitized_patterns")
    op.drop_index("ix_pesp_value_shape", table_name="platform_extraction_sanitized_patterns")
    op.drop_index("ix_pesp_field_path", table_name="platform_extraction_sanitized_patterns")
    op.drop_index("ix_pesp_broker_family", table_name="platform_extraction_sanitized_patterns")
    op.drop_index("ix_pesp_active", table_name="platform_extraction_sanitized_patterns")
    op.drop_table("platform_extraction_sanitized_patterns")
