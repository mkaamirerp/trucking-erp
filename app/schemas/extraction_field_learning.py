"""API for tenant-private extraction field learning (generic origin)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, model_validator


class ExtractionFieldLearningEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    origin_type: str
    origin_id: int
    created_at: datetime
    field_path: str
    event_kind: str
    proposed_value_json: Any | None = None
    final_value_json: Any | None = None
    previous_value_json: Any | None = None
    source_label: str | None = None
    source_section: str | None = None
    source_text: str | None = None
    source_page: int | None = None
    response_contract: str | None = None
    parser_version: str | None = None
    correction_type: str | None = None
    event_meta: dict[str, Any] | None = None
    actor_user_id: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def run_id(self) -> int | None:
        return self.origin_id if self.origin_type == "load_lab_run" else None


class ExtractionFieldLearningWriteIn(BaseModel):
    field_path: str = Field(..., min_length=1, max_length=512)
    final_value_json: Any | None = None
    previous_value_json: Any | None = None
    proposed_value_json: Any | None = None
    source_text: Optional[str] = Field(default=None, max_length=20000)
    source_page: int | None = None
    source_label: Optional[str] = Field(default=None, max_length=256)
    source_section: Optional[str] = Field(default=None, max_length=256)
    correction_type: str = Field(default="operator_override", max_length=32)
    value_json: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("value_json"),
        description="Backward compat: same as final_value_json when final_value_json omitted.",
    )

    @model_validator(mode="after")
    def _require_final(self) -> ExtractionFieldLearningWriteIn:
        fv = self.final_value_json if self.final_value_json is not None else self.value_json
        object.__setattr__(self, "final_value_json", fv)
        if self.final_value_json is None and str(self.correction_type).strip().casefold() not in (
            "operator_clear",
            "clear",
        ):
            raise ValueError("final_value_json or value_json is required unless correction_type is a clear op")
        return self
