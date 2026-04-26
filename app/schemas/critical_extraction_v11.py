"""Dispatch-critical extraction contract v1.1 (Pydantic) — OpenAI `json_schema` target.

Paired with field-instruction text in the prompt; structure is enforced here.
See docs/CRITICAL_EXTRACTION_CONTRACT_v1.1.json.md and docs/critical_extraction_output.v1.1.json.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CriticalReferenceNumberItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Optional[str] = None
    value: Optional[str] = None


class CriticalEvidenceString(BaseModel):
    """Single-value field with provenance (broker_name, commodity)."""

    model_config = ConfigDict(extra="forbid")
    value: Optional[str] = None
    confidence: Optional[str] = Field(default=None, max_length=32)
    source_text: Optional[str] = None
    page_number: Optional[int] = None
    needs_review: bool = True
    reason: Optional[str] = None


class CriticalBrokerLoadReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Optional[str] = None
    label: Optional[str] = None
    confidence: Optional[str] = Field(default=None, max_length=32)
    source_text: Optional[str] = None
    page_number: Optional[int] = None
    needs_review: bool = True
    reason: Optional[str] = None


class CriticalCarrierRateTotal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Optional[float] = None
    currency: Optional[str] = Field(default=None, max_length=8)
    confidence: Optional[str] = Field(default=None, max_length=32)
    source_text: Optional[str] = None
    page_number: Optional[int] = None
    needs_review: bool = True
    reason: Optional[str] = None


class CriticalStopV11(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stop_sequence: Optional[int] = None
    stop_type: Optional[str] = Field(
        default=None,
        max_length=16,
        description="pickup, delivery, or unknown",
    )
    facility_name: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state_province: Optional[str] = None
    postal_zip: Optional[str] = None
    country: Optional[str] = None
    date: Optional[str] = None
    time_window: Optional[str] = None
    reference_numbers: list[CriticalReferenceNumberItem] = Field(default_factory=list)
    address_quality: Optional[str] = Field(default=None, max_length=32)
    confidence: Optional[str] = Field(default=None, max_length=32)
    source_section: Optional[str] = None
    source_text: Optional[str] = None
    page_number: Optional[int] = None
    needs_review: bool = True
    reason: Optional[str] = None


class CriticalEquipment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_type: Optional[str] = None
    trailer_size: Optional[str] = None
    confidence: Optional[str] = Field(default=None, max_length=32)
    source_text: Optional[str] = None
    page_number: Optional[int] = None
    needs_review: bool = True
    reason: Optional[str] = None


class CriticalTemperatureRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temperature_required: Optional[bool] = None
    temperature_min: Optional[float] = None
    temperature_max: Optional[float] = None
    temperature_unit: Optional[str] = Field(default=None, max_length=16)
    run_type: Optional[str] = None
    confidence: Optional[str] = Field(default=None, max_length=32)
    source_text: Optional[str] = None
    page_number: Optional[int] = None
    needs_review: bool = True
    reason: Optional[str] = None


class CriticalWeight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weight_lbs: Optional[float] = None
    confidence: Optional[str] = Field(default=None, max_length=32)
    source_text: Optional[str] = None
    page_number: Optional[int] = None
    needs_review: bool = True
    reason: Optional[str] = None


class CriticalExtractionV11Root(BaseModel):
    """OpenAI return payload: matches docs/critical_extraction_output.v1.1.json (+ contract version)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    critical_extraction_contract_version: str = Field(
        default="1.1",
        max_length=16,
    )
    broker_name: CriticalEvidenceString
    broker_load_reference: CriticalBrokerLoadReference
    carrier_rate_total: CriticalCarrierRateTotal
    stops: list[CriticalStopV11] = Field(default_factory=list)
    equipment: CriticalEquipment
    temperature_requirement: CriticalTemperatureRequirement
    commodity: CriticalEvidenceString
    weight: CriticalWeight
