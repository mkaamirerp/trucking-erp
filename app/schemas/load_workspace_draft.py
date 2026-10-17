"""Load workspace draft (pre-promotion commercial workspace) API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.load_workspace_draft import LOAD_WORKSPACE_DRAFT_STATUSES

MAX_DRAFT_JSON_BYTES = 512_000
ALLOWED_SOURCE_CHANNELS = frozenset({"manual", "email_intake", "document_parse"})


def _validate_draft_json_object(value: dict[str, Any]) -> dict[str, Any]:
    import json

    if not isinstance(value, dict):
        raise ValueError("draft_json must be a JSON object")
    encoded = json.dumps(value, separators=(",", ":"), default=str)
    if len(encoded.encode("utf-8")) > MAX_DRAFT_JSON_BYTES:
        raise ValueError(f"draft_json exceeds {MAX_DRAFT_JSON_BYTES} bytes")
    return value


class LoadWorkspaceDraftCreate(BaseModel):
    source_channel: str = Field(default="manual", max_length=32)
    draft_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_channel")
    @classmethod
    def _source_channel_allowed(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_SOURCE_CHANNELS:
            allowed = ", ".join(sorted(ALLOWED_SOURCE_CHANNELS))
            raise ValueError(f"source_channel must be one of: {allowed}")
        return normalized

    @field_validator("draft_json")
    @classmethod
    def _draft_json_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_draft_json_object(value)


class LoadWorkspaceDraftUpdate(BaseModel):
    expected_concurrency_version: int = Field(..., ge=1)
    draft_json: dict[str, Any]

    @field_validator("draft_json")
    @classmethod
    def _draft_json_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_draft_json_object(value)


class LoadWorkspaceDraftPromote(BaseModel):
    expected_concurrency_version: int = Field(..., ge=1)
    promotion_idempotency_key: str = Field(..., min_length=1, max_length=128)


class LoadWorkspaceDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: int
    concurrency_version: int
    status: str
    draft_schema_version: int
    draft_json: dict[str, Any]
    source_channel: str
    expires_at: datetime
    created_by_platform_user_id: str | None = None
    updated_by_platform_user_id: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("status")
    @classmethod
    def _status_known(cls, value: str) -> str:
        if value not in LOAD_WORKSPACE_DRAFT_STATUSES:
            raise ValueError("unexpected draft status")
        return value


class LoadWorkspaceDraftPromoteOut(BaseModel):
    draft: LoadWorkspaceDraftOut
    load_id: int
    idempotent_replay: bool = False
