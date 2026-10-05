"""Toll FILE/CSV intake API schemas (Segment 2 + persistence hardening)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TollCsvIntakeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: int
    source_type: str
    file_format: str
    filename: str
    source_hash: str
    row_count: int
    headers: list[str]
    csv_raw_header_names: list[str] = Field(default_factory=list)
    csv_column_keys: list[str] = Field(default_factory=list)
    duplicate_match_count: int
    duplicate_batch_ids: list[int]
    status: str
    preview_rows: list[dict[str, str]] = Field(default_factory=list)


class TollFileBatchListItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: int
    source_type: str
    file_format: str | None = None
    filename: str | None = None
    source_hash: str | None = None
    status: str
    row_count: int
    imported_at: str | None = None
    csv_column_keys: list[str] = Field(default_factory=list)
    csv_raw_header_names: list[str] = Field(default_factory=list)


class TollFileSourceRowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_row_order: int
    source_line_number: int | None = None
    cells: dict[str, str]
    values: list[str]


class TollFileBatchDetailOut(TollFileBatchListItemOut):
    headers: list[str] = Field(default_factory=list)
    rows: list[TollFileSourceRowOut] = Field(default_factory=list)
    total_row_count: int = 0
    row_offset: int = 0
    row_limit: int = 0
