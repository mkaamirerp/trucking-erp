from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PersonApplicationFile(Base):
    __tablename__ = "person_application_files"
    __table_args__ = (
        Index("ix_person_application_files_tenant_id", "tenant_id"),
        Index("ix_person_application_files_tenant_app", "tenant_id", "application_id"),
        Index("ix_person_application_files_tenant_doctype", "tenant_id", "doc_type"),
        Index("ix_person_application_files_tenant_request_id", "tenant_id", "request_id"),
        ForeignKeyConstraint(
            ["tenant_id", "request_id"],
            ["person_application_requests.tenant_id", "person_application_requests.id"],
            name="fk_person_application_files_tenant_request_to_requests",
            ondelete="SET NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    application_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("person_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    doc_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)

    original_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    extract_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    request_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    application: Mapped["PersonApplication"] = relationship(
        "PersonApplication",
        back_populates="files",
    )
    request: Mapped["PersonApplicationRequest | None"] = relationship(
        "PersonApplicationRequest",
        back_populates="files",
        foreign_keys="[PersonApplicationFile.request_id]",
    )
