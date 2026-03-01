"""person_application_requests + document_requirements (tenant-safe); request_id on person_application_files.

Revision ID: b9c8d7e6f5a4
Revises: f8e353bbc2b9
Create Date: 2026-02-26

Order: document_requirements first, then person_application_requests, then FK requests->requirements,
then add request_id to person_application_files + FK.
created_by_user_id / resolved_by_user_id: platform identity ids; no FK enforced at tenant DB.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b9c8d7e6f5a4"
down_revision = "f8e353bbc2b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) document_requirements (config table)
    op.create_table(
        "document_requirements",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=30), nullable=False),
        sa.Column("scope_key", sa.String(length=50), nullable=False),
        sa.Column("doc_type", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("applies_at_stage", sa.String(length=30), nullable=False, server_default=sa.text("'SUBMIT'")),
        sa.Column("visibility", sa.String(length=30), nullable=False, server_default=sa.text("'APPLICANT'")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_document_requirements_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id", "scope_type", "scope_key", "doc_type",
            name="uq_document_requirements_tenant_scope_doc",
        ),
    )
    op.create_index(
        "ix_document_requirements_tenant_scope",
        "document_requirements",
        ["tenant_id", "scope_type", "scope_key"],
    )
    op.create_index(
        "ix_document_requirements_tenant_active",
        "document_requirements",
        ["tenant_id", "is_active"],
    )
    op.create_index(
        "ix_document_requirements_tenant_doc_type",
        "document_requirements",
        ["tenant_id", "doc_type"],
    )
    op.create_check_constraint(
        "ck_document_requirements_scope_type",
        "document_requirements",
        "scope_type IN ('ROLE','FORM')",
    )
    op.create_check_constraint(
        "ck_document_requirements_stage",
        "document_requirements",
        "applies_at_stage IN ('SUBMIT','POST_SUBMIT')",
    )
    op.create_check_constraint(
        "ck_document_requirements_visibility",
        "document_requirements",
        "visibility IN ('APPLICANT','ADMIN_ONLY')",
    )

    # 2) person_application_requests
    op.create_table(
        "person_application_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.BigInteger(), nullable=False),
        sa.Column("doc_requirement_id", sa.BigInteger(), nullable=True),
        sa.Column("request_type", sa.String(length=50), nullable=False),
        sa.Column("message_to_applicant", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'OPEN'")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),  # platform identity; no FK
        sa.Column("resolved_by_user_id", sa.BigInteger(), nullable=True),  # platform identity; no FK
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_person_application_requests_tenant_id_id"),
    )
    op.create_foreign_key(
        "fk_person_application_requests_tenant_app_to_applications",
        "person_application_requests",
        "person_applications",
        ["tenant_id", "application_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_person_application_requests_tenant_application_id",
        "person_application_requests",
        ["tenant_id", "application_id"],
    )
    op.create_index(
        "ix_person_application_requests_tenant_status",
        "person_application_requests",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_person_application_requests_tenant_request_type",
        "person_application_requests",
        ["tenant_id", "request_type"],
    )
    op.create_check_constraint(
        "ck_person_application_requests_status",
        "person_application_requests",
        "status IN ('OPEN','UPLOADED','ACCEPTED','REJECTED','EXPIRED')",
    )
    op.create_check_constraint(
        "ck_person_application_requests_request_type",
        "person_application_requests",
        "request_type IN ('CRIMINAL_RECORD','DRUG_TEST','MVR','MEDICAL_CARD','EMPLOYMENT_VERIFICATION','OTHER')",
    )

    # 3) FK requests -> document_requirements
    op.create_index(
        "ix_person_application_requests_tenant_doc_requirement_id",
        "person_application_requests",
        ["tenant_id", "doc_requirement_id"],
    )
    op.create_foreign_key(
        "fk_person_application_requests_tenant_docreq_to_requirements",
        "person_application_requests",
        "document_requirements",
        ["tenant_id", "doc_requirement_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )

    # 4) request_id on person_application_files
    op.add_column(
        "person_application_files",
        sa.Column("request_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_person_application_files_tenant_request_to_requests",
        "person_application_files",
        "person_application_requests",
        ["tenant_id", "request_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_person_application_files_tenant_request_id",
        "person_application_files",
        ["tenant_id", "request_id"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Forward-only migration for onboarding workflow tables; restore from backup to roll back."
    )
