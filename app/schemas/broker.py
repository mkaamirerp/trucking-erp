from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class BrokerBase(BaseModel):
    name: str = Field(..., max_length=255)
    mc_number: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[EmailStr] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class BrokerCreate(BrokerBase):
    pass


class BrokerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    mc_number: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[EmailStr] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class BrokerResponse(BrokerBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
