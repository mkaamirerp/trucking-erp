"""Customs broker (master) and contact schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CustomsBrokerBase(BaseModel):
    legal_name: str = Field(..., max_length=255)
    address_line1: Optional[str] = Field(default=None, max_length=255)
    address_line2: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    admin_area: Optional[str] = Field(default=None, max_length=50)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    country_code: Optional[str] = Field(default=None, max_length=2)
    phone_primary: Optional[str] = Field(default=None, max_length=50)
    phone_secondary: Optional[str] = Field(default=None, max_length=50)
    fax: Optional[str] = Field(default=None, max_length=50)
    generic_email: Optional[str] = Field(default=None, max_length=255)
    website_url: Optional[str] = Field(default=None, max_length=512)
    notes: Optional[str] = Field(default=None, max_length=8000)
    is_active: bool = True


class CustomsBrokerCreate(CustomsBrokerBase):
    pass


class CustomsBrokerUpdate(BaseModel):
    legal_name: Optional[str] = Field(default=None, max_length=255)
    address_line1: Optional[str] = Field(default=None, max_length=255)
    address_line2: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    admin_area: Optional[str] = Field(default=None, max_length=50)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    country_code: Optional[str] = Field(default=None, max_length=2)
    phone_primary: Optional[str] = Field(default=None, max_length=50)
    phone_secondary: Optional[str] = Field(default=None, max_length=50)
    fax: Optional[str] = Field(default=None, max_length=50)
    generic_email: Optional[str] = Field(default=None, max_length=255)
    website_url: Optional[str] = Field(default=None, max_length=512)
    notes: Optional[str] = Field(default=None, max_length=8000)
    is_active: Optional[bool] = None


class CustomsBrokerResponse(CustomsBrokerBase):
    id: int
    tenant_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class CustomsBrokerSummary(BaseModel):
    id: int
    legal_name: str
    is_active: bool
    phone_primary: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class CustomsBrokerContactBase(BaseModel):
    full_name: str = Field(..., max_length=255)
    role_label: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    fax: Optional[str] = Field(default=None, max_length=50)
    is_active: bool = True


class CustomsBrokerContactCreate(CustomsBrokerContactBase):
    pass


class CustomsBrokerContactUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    role_label: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    fax: Optional[str] = Field(default=None, max_length=50)
    is_active: Optional[bool] = None


class CustomsBrokerContactOut(CustomsBrokerContactBase):
    id: int
    tenant_id: int
    customs_broker_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class LoadCustomsSnapshotOut(BaseModel):
    load_id: int
    tenant_id: int
    legal_name_snapshot: Optional[str] = None
    address_line1_snapshot: Optional[str] = None
    address_line2_snapshot: Optional[str] = None
    city_snapshot: Optional[str] = None
    admin_area_snapshot: Optional[str] = None
    postal_code_snapshot: Optional[str] = None
    country_code_snapshot: Optional[str] = None
    phone_primary_snapshot: Optional[str] = None
    phone_secondary_snapshot: Optional[str] = None
    fax_snapshot: Optional[str] = None
    generic_email_snapshot: Optional[str] = None
    website_url_snapshot: Optional[str] = None
    customs_broker_id_at_confirm: Optional[int] = None
    confirmed_at: datetime
    model_config = ConfigDict(from_attributes=True)
