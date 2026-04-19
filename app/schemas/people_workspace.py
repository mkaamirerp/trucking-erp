"""Admin People workspace: list/detail/patch maintained `people` rows (tenant DB)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.validators import normalize_phone_number as normalize_phone


class PersonRoleSummary(BaseModel):
    id: int
    role_code: str
    is_primary: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class DriverProfileSummary(BaseModel):
    license_number: Optional[str] = None
    license_region: Optional[str] = None
    license_expiry: Optional[date] = None
    is_active: bool = True


class DriverPersonExtensionSummary(BaseModel):
    employment_relationship_type: str
    driver_operating_subtype: str
    is_team_driver: bool
    provides_own_truck: bool
    provides_own_trailer: bool
    equipment_contribution_type: str
    insurance_commercial_approved: bool


class OperationalDriverSummary(BaseModel):
    driver_id: int
    is_active: bool
    first_name: str
    last_name: str
    payee_id: Optional[int] = None


class CompensationSummary(BaseModel):
    payee_id: Optional[int] = None
    worker_type: Optional[str] = None
    gross_calc_type: Optional[str] = None
    hourly_rate: Optional[str] = None
    cpm_loaded: Optional[str] = None
    cpm_empty: Optional[str] = None
    percent_rate: Optional[str] = None
    salary_amount: Optional[str] = None
    flat_amount: Optional[str] = None
    settlement_frequency: Optional[str] = None
    participates_in_fuel_discount_program: Optional[bool] = None
    dispatch_fee_enabled: Optional[bool] = None
    dispatch_fee_rate: Optional[str] = None
    dispatch_fee_basis: Optional[str] = None


class LinkedPersonApplicationSummary(BaseModel):
    """Most recent application linked to this person (for deep links to onboarding workspace)."""

    id: int
    status: str
    setup_status: Optional[str] = None
    #: Raw ``person_applications.current_workflow_lane`` (queue / ownership hint).
    current_workflow_lane: Optional[str] = None


class PeopleListItemOut(BaseModel):
    id: int
    tenant_id: int
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    #: Active `person_roles` only; read-only list hint (detail uses full `roles`).
    active_role_codes: list[str] = Field(default_factory=list)
    primary_role_code: Optional[str] = None
    #: Latest `person_applications` row for this person (same ordering as detail: updated_at, id).
    latest_application: Optional[LinkedPersonApplicationSummary] = None

    model_config = {"from_attributes": True}


class PeopleDetailOut(PeopleListItemOut):
    street_address: Optional[str] = None
    postal_code: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    platform_user_id: Optional[str] = None

    roles: list[PersonRoleSummary] = Field(default_factory=list)
    driver_profile: Optional[DriverProfileSummary] = None
    driver_person_extension: Optional[DriverPersonExtensionSummary] = None
    operational_drivers: list[OperationalDriverSummary] = Field(default_factory=list)
    compensation: CompensationSummary


class PeopleCorePatch(BaseModel):
    """PATCH body: only set fields are applied to `people`."""

    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    street_address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    zip_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=10)
    notes: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)

    model_config = {"extra": "forbid"}


class PeoplePatchResultOut(BaseModel):
    person: PeopleDetailOut
    synced_operational_driver_ids: list[int] = Field(default_factory=list)


class DriverProfilePatch(BaseModel):
    """PATCH `driver_profiles` for a person (People workspace; not onboarding workflow)."""

    license_number: Optional[str] = Field(None, max_length=100)
    license_region: Optional[str] = Field(None, max_length=100)
    license_expiry: Optional[date] = None
    is_active: Optional[bool] = None

    model_config = {"extra": "forbid"}

    @field_validator("license_number", "license_region")
    @classmethod
    def strip_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        t = v.strip()
        return t or None


class PeopleAuditLogEntryOut(BaseModel):
    """One tenant audit row for People workspace maintenance actions (read-only)."""

    id: int
    action: str
    created_at: datetime
    actor_user_id: Optional[int] = None
    actor_email: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    changed_keys: list[str] = Field(default_factory=list)
    snapshot: dict[str, Any] = Field(default_factory=dict)
