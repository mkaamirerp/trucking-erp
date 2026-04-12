"""Broker and related entity schemas (freight / booking broker master data)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class BrokerBase(BaseModel):
    """Fields for create/update; legacy `name` fills display/legal when omitted."""

    name: Optional[str] = Field(default=None, max_length=255)
    legal_name: Optional[str] = Field(default=None, max_length=500)
    display_name: Optional[str] = Field(default=None, max_length=255)
    mc_number: Optional[str] = Field(default=None, max_length=100)
    dot_number: Optional[str] = Field(default=None, max_length=32)
    scac: Optional[str] = Field(default=None, max_length=16)
    phone: Optional[str] = Field(default=None, max_length=50)
    phone_secondary: Optional[str] = Field(default=None, max_length=50)
    email: Optional[EmailStr] = None
    email_secondary: Optional[EmailStr] = None
    website: Optional[str] = Field(default=None, max_length=512)
    address_line1: Optional[str] = Field(default=None, max_length=255)
    address_line2: Optional[str] = Field(default=None, max_length=255)
    address_city: Optional[str] = Field(default=None, max_length=120)
    address_region: Optional[str] = Field(default=None, max_length=120)
    address_postal: Optional[str] = Field(default=None, max_length=32)
    address_country: Optional[str] = Field(default=None, max_length=2)
    classification_notes: Optional[str] = Field(default=None, max_length=8000)
    internal_notes: Optional[str] = Field(default=None, max_length=8000)
    notes: Optional[str] = Field(default=None, max_length=2000)


class BrokerCreate(BrokerBase):
    @model_validator(mode="after")
    def _require_at_least_one_label(self) -> BrokerCreate:
        if not (self.name or "").strip() and not (self.display_name or "").strip() and not (self.legal_name or "").strip():
            raise ValueError("Provide name, display_name, or legal_name")
        return self


class BrokerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    legal_name: Optional[str] = Field(default=None, max_length=500)
    display_name: Optional[str] = Field(default=None, max_length=255)
    mc_number: Optional[str] = Field(default=None, max_length=100)
    dot_number: Optional[str] = Field(default=None, max_length=32)
    scac: Optional[str] = Field(default=None, max_length=16)
    phone: Optional[str] = Field(default=None, max_length=50)
    phone_secondary: Optional[str] = Field(default=None, max_length=50)
    email: Optional[EmailStr] = None
    email_secondary: Optional[EmailStr] = None
    website: Optional[str] = Field(default=None, max_length=512)
    address_line1: Optional[str] = Field(default=None, max_length=255)
    address_line2: Optional[str] = Field(default=None, max_length=255)
    address_city: Optional[str] = Field(default=None, max_length=120)
    address_region: Optional[str] = Field(default=None, max_length=120)
    address_postal: Optional[str] = Field(default=None, max_length=32)
    address_country: Optional[str] = Field(default=None, max_length=2)
    classification_notes: Optional[str] = Field(default=None, max_length=8000)
    internal_notes: Optional[str] = Field(default=None, max_length=8000)
    notes: Optional[str] = Field(default=None, max_length=2000)


class BrokerResponse(BrokerBase):
    id: int
    is_active: bool
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BrokerResolveIdentityOut(BaseModel):
    """Tenant broker row matched by MC or USDOT digits from a rate confirmation / PDF."""

    broker_id: Optional[int] = None
    matched_by: Optional[Literal["mc", "dot"]] = None
    broker: Optional[BrokerResponse] = None


# --- BrokerContact ---


class BrokerContactBase(BaseModel):
    name: str = Field(..., max_length=255)
    first_name: Optional[str] = Field(default=None, max_length=120)
    last_name: Optional[str] = Field(default=None, max_length=120)
    role: Optional[str] = Field(default=None, max_length=120)
    department: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=50)
    extension: Optional[str] = Field(default=None, max_length=20)
    fax: Optional[str] = Field(default=None, max_length=50)
    email: Optional[EmailStr] = None
    is_primary: bool = False
    notes: Optional[str] = Field(default=None, max_length=4000)


class BrokerContactCreateBody(BrokerContactBase):
    pass


class BrokerContactUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    first_name: Optional[str] = Field(default=None, max_length=120)
    last_name: Optional[str] = Field(default=None, max_length=120)
    role: Optional[str] = Field(default=None, max_length=120)
    department: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=50)
    extension: Optional[str] = Field(default=None, max_length=20)
    fax: Optional[str] = Field(default=None, max_length=50)
    email: Optional[EmailStr] = None
    is_primary: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=4000)


class BrokerContactOut(BrokerContactBase):
    id: int
    broker_id: int
    is_active: bool
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Domains / aliases ---


class BrokerDomainCreate(BaseModel):
    domain: str = Field(..., max_length=255)
    is_primary: bool = False
    notes: Optional[str] = Field(default=None, max_length=2000)


class BrokerDomainUpdate(BaseModel):
    domain: Optional[str] = Field(default=None, max_length=255)
    is_primary: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class BrokerDomainOut(BaseModel):
    id: int
    tenant_id: int
    broker_id: int
    domain: str
    is_primary: bool
    notes: Optional[str] = None
    is_active: bool
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BrokerAliasCreate(BaseModel):
    alias: str = Field(..., max_length=255)
    alias_type: str = Field(default="display", max_length=32)


class BrokerAliasUpdate(BaseModel):
    alias: Optional[str] = Field(default=None, max_length=255)
    alias_type: Optional[str] = Field(default=None, max_length=32)


class BrokerAliasOut(BaseModel):
    id: int
    tenant_id: int
    broker_id: int
    alias: str
    alias_type: str
    is_active: bool
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Known senders (exact email) ---


class BrokerKnownSenderCreate(BaseModel):
    email: EmailStr = Field(..., description="Full sender address; stored normalized")
    notes: Optional[str] = Field(default=None, max_length=2000)


class BrokerKnownSenderUpdate(BaseModel):
    email: Optional[EmailStr] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class BrokerKnownSenderOut(BaseModel):
    id: int
    tenant_id: int
    broker_id: int
    email_normalized: str
    notes: Optional[str] = None
    is_active: bool
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BrokerWorkspaceOut(BaseModel):
    broker: BrokerResponse
    contacts: list[BrokerContactOut]
    domains: list[BrokerDomainOut]
    aliases: list[BrokerAliasOut]
    known_senders: list[BrokerKnownSenderOut]


BrokerSort = Literal["name_asc", "name_desc", "id_desc"]

# Legacy: some code imports BrokerContactCreate with broker_id
class BrokerContactCreate(BrokerContactBase):
    broker_id: int = Field(...)
