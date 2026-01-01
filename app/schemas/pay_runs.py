from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PayRunCreate(BaseModel):
    pay_period_id: int


class PayRunGenerateResponse(BaseModel):
    pay_run_id: int
    item_count: int


class PayRunFinalizeResponse(BaseModel):
    pay_run_id: int
    status: str
    totals_snapshot: dict


class PayRunItemOut(BaseModel):
    id: int
    driver_id: int
    entry_type: str
    amount: Decimal
    source_entry_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PayRunOut(BaseModel):
    id: int
    pay_period_id: int
    status: str
    totals_snapshot: Optional[dict] = None
    finalized_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    items: list[PayRunItemOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
