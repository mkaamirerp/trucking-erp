"""Role-attached driver configuration DTOs (`driver_person_extensions`) — no compensation, no payee.

Validation is shared by onboarding workflow and the People workspace correction path.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --- Locked enums (string values match DB) ---

EMPLOYMENT_RELATIONSHIP_TYPES = frozenset({"company_driver", "owner_operator"})
DRIVER_OPERATING_SUBTYPES = frozenset({"long_haul", "city_local", "shunt_yard"})
TEAM_ROLE_TYPES = frozenset({"primary", "co_driver"})
EQUIPMENT_CONTRIBUTION_TYPES = frozenset(
    {"company_equipment", "driver_truck_only", "driver_truck_and_trailer", "unspecified"}
)


class DriverPersonExtensionBase(BaseModel):
    employment_relationship_type: str = Field(..., max_length=50)
    driver_operating_subtype: str = Field(..., max_length=50)
    is_team_driver: bool = False
    team_role_type: str | None = Field(None, max_length=50)
    provides_own_truck: bool = False
    provides_own_trailer: bool = False
    equipment_contribution_type: str = Field(..., max_length=50)
    insurance_commercial_approved: bool = False

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_phase3a_rules(self) -> DriverPersonExtensionBase:
        ert = self.employment_relationship_type.strip()
        if ert not in EMPLOYMENT_RELATIONSHIP_TYPES:
            raise ValueError(
                f"employment_relationship_type must be one of {sorted(EMPLOYMENT_RELATIONSHIP_TYPES)}"
            )
        self.employment_relationship_type = ert

        st = self.driver_operating_subtype.strip()
        if st == "owner_operator":
            raise ValueError(
                "owner_operator is not allowed as driver_operating_subtype; use employment_relationship_type=owner_operator instead"
            )
        if st not in DRIVER_OPERATING_SUBTYPES:
            raise ValueError(
                f"driver_operating_subtype must be one of {sorted(DRIVER_OPERATING_SUBTYPES)}"
            )
        self.driver_operating_subtype = st

        if self.is_team_driver:
            if not self.team_role_type or not str(self.team_role_type).strip():
                raise ValueError("team_role_type is required when is_team_driver is true")
            tr = self.team_role_type.strip()
            if tr not in TEAM_ROLE_TYPES:
                raise ValueError(f"team_role_type must be one of {sorted(TEAM_ROLE_TYPES)}")
            self.team_role_type = tr
        else:
            if self.team_role_type is not None and str(self.team_role_type).strip() != "":
                raise ValueError("team_role_type must be null when is_team_driver is false")
            self.team_role_type = None

        ect = self.equipment_contribution_type.strip()
        if ect not in EQUIPMENT_CONTRIBUTION_TYPES:
            raise ValueError(
                f"equipment_contribution_type must be one of {sorted(EQUIPMENT_CONTRIBUTION_TYPES)}"
            )
        self.equipment_contribution_type = ect

        if ect == "company_equipment":
            if self.provides_own_truck or self.provides_own_trailer:
                raise ValueError(
                    "equipment_contribution_type=company_equipment requires provides_own_truck=false and provides_own_trailer=false"
                )
        elif ect == "driver_truck_only":
            if not self.provides_own_truck or self.provides_own_trailer:
                raise ValueError(
                    "equipment_contribution_type=driver_truck_only requires provides_own_truck=true and provides_own_trailer=false"
                )
        elif ect == "driver_truck_and_trailer":
            if not self.provides_own_truck or not self.provides_own_trailer:
                raise ValueError(
                    "equipment_contribution_type=driver_truck_and_trailer requires provides_own_truck=true and provides_own_trailer=true"
                )
        # unspecified: no extra boolean constraint

        return self


class DriverPersonExtensionWrite(DriverPersonExtensionBase):
    """Payload for PUT (replace / upsert)."""


class DriverPersonExtensionOut(BaseModel):
    """Row returned from API."""

    id: int
    tenant_id: int
    person_id: int
    employment_relationship_type: str
    driver_operating_subtype: str
    is_team_driver: bool
    team_role_type: str | None
    provides_own_truck: bool
    provides_own_trailer: bool
    equipment_contribution_type: str
    insurance_commercial_approved: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
