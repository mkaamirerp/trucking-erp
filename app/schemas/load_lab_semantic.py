"""Strict Pydantic contract for Load Lab OpenAI structured extraction (v2).

Maps to the same field geometry as workspace parse (`LoadParseExtractedFields` /
`LoadParseDocumentMeta`) but with extra=\"forbid\" for JSON-schema style outputs.

The model returns document + extracted + warnings only; the service attaches
`raw_full_text` from the stored normalized package when building
`LoadDocumentParseResponse`.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.load_document_parse import (
    LoadParseDocumentMeta,
    LoadParseExtractedFields,
    LoadParseReferenceItem,
    LoadParseStopItem,
)


class StrictDoc(LoadParseDocumentMeta):
    model_config = ConfigDict(extra="forbid")


class StrictRef(LoadParseReferenceItem):
    model_config = ConfigDict(extra="forbid")


class StrictStop(LoadParseStopItem):
    model_config = ConfigDict(extra="forbid")


class StrictExtracted(LoadParseExtractedFields):
    """Extracted block: forbid unknown keys; nested list items use strict refs/stops."""

    model_config = ConfigDict(extra="forbid")
    references: list[StrictRef] = Field(default_factory=list)
    stops: list[StrictStop] = Field(default_factory=list)


class LoadLabSemanticModelOutput(BaseModel):
    """Payload returned by the model (JSON). Not the full TruckERP parse response."""

    model_config = ConfigDict(extra="forbid")
    document: StrictDoc
    extracted: StrictExtracted
    extraction_warnings: list[str] = Field(default_factory=list)
