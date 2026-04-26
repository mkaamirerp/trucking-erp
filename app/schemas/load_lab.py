"""API schemas for Load Lab (extraction runs + promote)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LoadLabRunOut(BaseModel):
    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime
    source_route: str
    created_by_platform_user_id: str | None
    file_sha256: str
    filename: str
    mime_type: str
    file_size_bytes: int
    status: str
    extraction_path: str | None
    dedupe_prior_run_id: int | None
    parser_version: str
    schema_version: str
    prompt_version: str
    model_name: str
    ocr_engine_version: str | None
    normalizer_version: str
    classification_label: str | None
    relevance: str | None
    normalized_package: dict[str, Any] | None
    # v2: validated TruckERP-shaped candidate (`LoadDocumentParseResponse` geometry) when semantic extraction succeeds.
    parse_response: dict[str, Any] | None = None
    ai_model_output: dict[str, Any] | None = None
    warnings: list[Any] | None
    pipeline_error: str | None
    semantic_model_name: str | None = None
    semantic_prompt_version: str | None = None
    semantic_schema_version: str | None = None
    semantic_extract_status: str | None = None
    semantic_validation_result: dict[str, Any] | None = None
    # v3: lab-only review (no promote / operational writes).
    lab_confidence: dict[str, Any] | None = None
    contradictions: list[Any] | None = None
    lab_review_status: str | None = None
    lab_review_summary: str | None = None

    model_config = {"from_attributes": True}


class LoadLabRunUploadResponse(BaseModel):
    run: LoadLabRunOut
    reused_existing_run: bool = False


class LoadLabSemanticExtractIn(BaseModel):
    """Body for POST /load-lab/runs/{id}/semantic-extract."""

    force: bool = Field(default=False, description="Re-run OpenAI even if a successful candidate is already stored.")


class LoadLabOpenaiSmokeOut(BaseModel):
    """Result of a connectivity-only OpenAI check (no extraction)."""

    ok: bool
    http_status: int | None = None
    sample_model_id: str | None = None
    detail: str | None = None
