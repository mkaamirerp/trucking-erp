from datetime import datetime
from pydantic import BaseModel, Field

class DriverPhoneBase(BaseModel):
    label: str | None = Field(None, examples=["mobile", "home", "dispatch"])
    phone: str = Field(..., examples=["4165550102"])
    extension: str | None = None
    is_primary: bool = False
    notes: str | None = None


class DriverPhoneCreate(DriverPhoneBase):
    pass


class DriverPhoneUpdate(BaseModel):
    label: str | None = None
    phone: str | None = None
    extension: str | None = None
    is_primary: bool | None = None
    notes: str | None = None


class DriverPhoneRead(DriverPhoneBase):
    id: int
    driver_id: int
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
