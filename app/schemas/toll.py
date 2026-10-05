"""Toll FILE/CSV intake API schemas (Segment 2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TollCsvIntakeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: int
    source_type: str
    file_format: str
    filename: str
    source_hash: str
    source_storage_ref: str
    row_count: int
    headers: list[str]
    duplicate_match_count: int
    duplicate_batch_ids: list[int]
    status: str
    preview_rows: list[dict[str, str]] = Field(default_factory=list)
