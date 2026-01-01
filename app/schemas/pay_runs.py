from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PayRunCreate(BaseModel):
    pay_period_id: int
    pay_document_type: str = "PAYSTUB"
    worker_type_snapshot: str = "EMPLOYEE_DRIVER"
    pay_date: Optional[date] = None
    base_currency_snapshot: str = Field(default="USD", min_length=3, max_length=3, description="Currency snapshot")


class PayRunGenerateResponse(BaseModel):
    pay_run_id: int
    item_count: int


class PayRunFinalizeResponse(BaseModel):
    pay_run_id: int
    status: str
    totals_snapshot: dict | None = None


class PayRunItemOut(BaseModel):
    id: int
    payee_id: int
    source_type: str
    description: str
    amount_signed: Decimal
    currency: str
    quantity: Decimal | None = None
    unit_rate: Decimal | None = None
    charge_category_id: int | None = None
    charge_category_code: str | None = None
    metadata_json: dict | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PayRunSummary(BaseModel):
    id: int
    pay_period_id: int
    pay_document_type: str
    worker_type_snapshot: str
    base_currency_snapshot: str
    pay_date: date
    status: str
    payout_status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PayRunDetail(BaseModel):
    id: int
    pay_period_id: int
    pay_document_type: str
    worker_type_snapshot: str
    base_currency_snapshot: str
    pay_date: date
    status: str
    payout_status: str
    calculation_snapshot_json: dict | None = None
    totals_snapshot: Optional[dict] = None
    finalized_at: Optional[datetime] = None
    finalized_by: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PayRunPayeeRow(BaseModel):
    payee_id: int
    display_name: str
    net_amount: Decimal
    flags: dict

    model_config = ConfigDict(from_attributes=True)
