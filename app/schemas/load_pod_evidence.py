"""POD evidence list/upload responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LoadPodEvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    load_id: int
    file_sha256: str
    original_filename: str | None
    content_type: str | None
    file_size_bytes: int
    uploaded_at: datetime
    actor_user_id: int | None
    actor_label: str | None


class LoadPodEvidenceListResponse(BaseModel):
    items: list[LoadPodEvidenceOut]
