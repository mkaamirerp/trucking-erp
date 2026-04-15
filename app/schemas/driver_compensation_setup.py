"""Driver compensation setup (tenant payees + compensation_profiles) — combined-mode slice."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import GrossCalcType, SettlementFrequency


class DriverCompensationGrossModel(str, Enum):
    """UI-facing subset of GrossCalcType for onboarding card (HYBRID deferred)."""

    CPM = GrossCalcType.CPM.value
    PERCENT_REVENUE = GrossCalcType.PERCENT_REVENUE.value
    FLAT_PER_LOAD = GrossCalcType.FLAT_PER_LOAD.value
    HOURLY = GrossCalcType.HOURLY.value
    SALARY = GrossCalcType.SALARY.value


class DriverCompensationSetupOut(BaseModel):
    payee_id: int | None = None
    worker_type: str | None = Field(
        default=None,
        description="Tenant payees.worker_type; aligned with DriverPersonExtension when present.",
    )
    gross_calc_type: str | None = None
    percent_rate: Decimal | None = None
    cpm_loaded: Decimal | None = None
    cpm_empty: Decimal | None = None
    hourly_rate: Decimal | None = None
    salary_amount: Decimal | None = None
    flat_amount: Decimal | None = None
    settlement_frequency: str | None = None
    participates_in_fuel_discount_program: bool = False
    dispatch_fee_enabled: bool = False
    dispatch_fee_rate: Decimal = Field(default=Decimal("0"))
    dispatch_fee_basis: str = "GROSS"
    employment_relationship_type: str | None = Field(
        default=None,
        description="From driver_person_extensions when row exists (read-only context for UI).",
    )

    model_config = ConfigDict(from_attributes=True)


class DriverCompensationSetupWrite(BaseModel):
    gross_calc_type: DriverCompensationGrossModel
    percent_rate: Decimal | None = None
    cpm_loaded: Decimal | None = None
    cpm_empty: Decimal | None = None
    hourly_rate: Decimal | None = None
    salary_amount: Decimal | None = None
    flat_amount: Decimal | None = None
    settlement_frequency: SettlementFrequency = SettlementFrequency.BIWEEKLY
    participates_in_fuel_discount_program: bool = False
    dispatch_fee_enabled: bool = False
    dispatch_fee_rate: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("1"))
    dispatch_fee_basis: str = Field(default="GROSS", max_length=32)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _rates_match_model(self) -> DriverCompensationSetupWrite:
        g = GrossCalcType(self.gross_calc_type.value)
        if g == GrossCalcType.PERCENT_REVENUE:
            if self.percent_rate is None or self.percent_rate <= 0:
                raise ValueError("percent_rate is required and must be > 0 for PERCENT_REVENUE")
        elif g == GrossCalcType.CPM:
            if self.cpm_loaded is None or self.cpm_loaded < 0:
                raise ValueError("cpm_loaded is required and must be >= 0 for CPM")
        elif g == GrossCalcType.HOURLY:
            if self.hourly_rate is None or self.hourly_rate <= 0:
                raise ValueError("hourly_rate is required and must be > 0 for HOURLY")
        elif g == GrossCalcType.SALARY:
            if self.salary_amount is None or self.salary_amount <= 0:
                raise ValueError("salary_amount is required and must be > 0 for SALARY")
        elif g == GrossCalcType.FLAT_PER_LOAD:
            if self.flat_amount is None or self.flat_amount <= 0:
                raise ValueError("flat_amount is required and must be > 0 for FLAT_PER_LOAD")
        return self
