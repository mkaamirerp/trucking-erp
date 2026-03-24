"""Platform-side integration secret storage. Control-plane only."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TenantIntegrationSecret(Base):
    """Encrypted credentials for tenant integrations (email mailbox, etc).
    Tenant DB holds metadata + credential_ref_id; actual secrets live here.
    """
    __tablename__ = "tenant_integration_secrets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="email_mailbox")
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
