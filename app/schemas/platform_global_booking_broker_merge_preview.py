"""Platform merge-preview / merge-execute (global booking brokers)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GlobalBookingBrokerMergePreviewIn(BaseModel):
    model_config = {"extra": "forbid"}

    source_global_broker_id: int = Field(..., ge=1)
    survivor_global_broker_id: int = Field(..., ge=1)
    duplicate_candidate_id: int | None = Field(
        default=None,
        description="Optional duplicate-candidate row id; must reference the same broker pair when set.",
    )


class GlobalBookingBrokerMergePreviewOut(BaseModel):
    preview_id: int | None = Field(
        default=None,
        description="Set when preview is persisted for later execute (no blockers, no regulatory blocking conflicts).",
    )
    preview_hash: str = Field(..., min_length=64, max_length=64)
    preview: dict[str, Any]


class GlobalBookingBrokerMergeExecuteIn(BaseModel):
    model_config = {"extra": "forbid"}

    preview_id: int = Field(..., ge=1)
    preview_hash: str = Field(..., min_length=64, max_length=64)
    name_resolution: Literal["source", "survivor"] | None = None
    legal_name_resolution: Literal["source", "survivor"] | None = None
    display_name_resolution: Literal["source", "survivor"] | None = None


class GlobalBookingBrokerMergeExecuteOut(BaseModel):
    status: Literal["completed", "already_completed"]
    preview_id: int
    preview_hash: str
    source_global_broker_id: int
    survivor_global_broker_id: int
    duplicate_candidate_id: int | None = None
    child_stats: dict[str, int] | None = None
