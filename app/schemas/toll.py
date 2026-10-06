"""Toll FILE/CSV intake API schemas (Segment 2 + persistence hardening)."""

from __future__ import annotations

from typing import Any

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


class TollPdfIntakeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: int
    source_type: str
    file_format: str
    profile_code: str
    filename: str
    source_hash: str
    status: str
    review_status: str
    duplicate_match_count: int
    duplicate_batch_ids: list[int]
    statement_date: str | None = None
    account_number: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    start_balance: str | None = None
    end_balance: str | None = None
    total_payment_amount: str | None = None
    total_payment_count: int | None = None
    source_page_count: int | None = None
    source_total_trip_count: int | None = None
    source_total_trip_charge: str | None = None
    parsed_trip_count: int
    parsed_total_trip_charge: str
    trip_count_matches: bool
    trip_total_matches: bool
    reconciliation_ok: bool


class TollPdfReviewListItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: int
    source_type: str
    file_format: str | None = None
    profile_code: str
    filename: str | None = None
    source_hash: str | None = None
    status: str
    review_status: str
    imported_at: str | None = None
    statement_date: str | None = None
    account_number: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    source_total_trip_count: int | None = None
    source_total_trip_charge: str | None = None
    parsed_trip_count: int
    parsed_total_trip_charge: str | None = None
    trip_count_matches: bool
    trip_total_matches: bool
    reconciliation_ok: bool


class TollPdfReviewRowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_row_order: int
    source_page_number: int | None = None
    post_date: str | None = None
    entry_date: str | None = None
    entry_time: str | None = None
    exit_date: str | None = None
    exit_time: str | None = None
    agency_raw: str | None = None
    entry_location: str | None = None
    entry_lane: str | None = None
    exit_location: str | None = None
    exit_lane: str | None = None
    transponder_number: str | None = None
    plate_number: str | None = None
    trip_charge: str
    trip_charge_raw: str | None = None
    source_group_transponder: str | None = None
    source_group_plate: str | None = None
    provider_raw: dict[str, Any] = Field(default_factory=dict)


class TollPdfReviewDetailOut(TollPdfReviewListItemOut):
    start_balance: str | None = None
    end_balance: str | None = None
    total_payment_amount: str | None = None
    total_payment_count: int | None = None
    source_page_count: int | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    total_row_count: int = 0
    row_offset: int = 0
    row_limit: int = 0
    rows: list[TollPdfReviewRowOut] = Field(default_factory=list)


class TollManualStageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_date: str | None = None
    event_date: str | None = None
    event_time: str | None = None
    agency_raw: str | None = None
    entry_location: str | None = None
    entry_lane: str | None = None
    exit_location: str | None = None
    exit_lane: str | None = None
    transponder_number: str | None = None
    plate_number: str | None = None
    plate_state: str | None = None
    trip_charge: str | None = None
    currency: str | None = None
    notes: str | None = None
    unresolved_vehicle_identity: bool | None = None


class TollManualStageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: int
    source_type: str
    file_format: str | None = None
    status: str
    post_date: str | None = None
    event_date: str | None = None
    event_time: str | None = None
    agency_raw: str | None = None
    entry_location: str | None = None
    entry_lane: str | None = None
    exit_location: str | None = None
    exit_lane: str | None = None
    transponder_number: str | None = None
    plate_number: str | None = None
    plate_state: str | None = None
    trip_charge: str | None = None
    currency: str | None = None
    notes: str | None = None
    unresolved_vehicle_identity: bool = False
    vehicle_identity_status: str | None = None
    source_evidence_json: dict[str, Any] = Field(default_factory=dict)


class TollManualValidateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    errors: list[dict[str, str]] = Field(default_factory=list)
    stage: TollManualStageOut
