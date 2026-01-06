"""add driver documents tables

Revision ID: 9d4695445bae
Revises: 7de1d90c39eb
Create Date: 2025-12-24 15:38:05.837927

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d4695445bae"
down_revision: Union[str, Sequence[str], None] = "7de1d90c39eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- driver_documents (logical doc record) ----
    op.create_table(
        "driver_documents",
        sa.Column("id", sa.Integer(), primary_key=True),

        sa.Column("driver_id", sa.Integer(), nullable=False),

        # e.g. 'CDL', 'MEDICAL_CARD', 'PASSPORT', 'FAST_CARD', 'PROOF_OF_CITIZENSHIP'
        sa.Column("doc_type", sa.String(length=50), nullable=False),

        # Optional: helps UI ("CDL - Ontario", "Medical Card - Dr. Smith")
        sa.Column("title", sa.String(length=255), nullable=True),

        # Compliance tracking
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),

        # Status: ACTIVE, EXPIRED, MISSING, REJECTED, PENDING_REVIEW
        sa.Column("status", sa.String(length=30), nullable=False, server_default="ACTIVE"),

        # Free notes ("Needs renewal", "Uploaded blurry copy", etc.)
        sa.Column("notes", sa.Text(), nullable=True),

        # Whether this document is currently the one used for compliance checks
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # FK + indexes
    op.create_foreign_key(
        "fk_driver_documents_driver_id",
        "driver_documents",
        "drivers",
        ["driver_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_driver_documents_driver_id", "driver_documents", ["driver_id"])
    op.create_index("ix_driver_documents_doc_type", "driver_documents", ["doc_type"])
    op.create_index("ix_driver_documents_expiry_date", "driver_documents", ["expiry_date"])
    op.create_index("ix_driver_documents_is_current", "driver_documents", ["is_current"])

    # One "current" document per (driver, doc_type)
    # Partial unique indexes are best, but cross-db gets tricky.
    # We'll enforce via application logic for now.

    # ---- driver_document_files (physical file versions) ----
    op.create_table(
        "driver_document_files",
        sa.Column("id", sa.Integer(), primary_key=True),

        sa.Column("driver_document_id", sa.Integer(), nullable=False),

        # Where file is stored (local path or S3 key later)
        sa.Column("storage_key", sa.String(length=1024), nullable=False),

        # Original filename as uploaded by user
        sa.Column("original_filename", sa.String(length=255), nullable=True),

        # MIME type: application/pdf, image/jpeg, etc.
        sa.Column("content_type", sa.String(length=100), nullable=True),

        # Optional: store file size and checksum later
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),

        # Track which upload is the active one
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),

        # Audit
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_foreign_key(
        "fk_driver_document_files_driver_document_id",
        "driver_document_files",
        "driver_documents",
        ["driver_document_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_driver_document_files_driver_document_id", "driver_document_files", ["driver_document_id"])
    op.create_index("ix_driver_document_files_is_active", "driver_document_files", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_driver_document_files_is_active", table_name="driver_document_files")
    op.drop_index("ix_driver_document_files_driver_document_id", table_name="driver_document_files")
    op.drop_constraint("fk_driver_document_files_driver_document_id", "driver_document_files", type_="foreignkey")
    op.drop_table("driver_document_files")

    op.drop_index("ix_driver_documents_is_current", table_name="driver_documents")
    op.drop_index("ix_driver_documents_expiry_date", table_name="driver_documents")
    op.drop_index("ix_driver_documents_doc_type", table_name="driver_documents")
    op.drop_index("ix_driver_documents_driver_id", table_name="driver_documents")
    op.drop_constraint("fk_driver_documents_driver_id", "driver_documents", type_="foreignkey")
    op.drop_table("driver_documents")
