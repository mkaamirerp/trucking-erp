"""Response models for workspace PDF parse (hydration only — no persisted load)."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class LoadParseDocumentMeta(BaseModel):
    filename: str = Field(..., max_length=512)


class LoadParseReferenceItem(BaseModel):
    kind: str = Field(..., max_length=32)
    value: str = Field(..., max_length=120)
    # Optional provenance/selection metadata (Load Lab + workspace hydration safe).
    label: Optional[str] = Field(default=None, max_length=80)
    primary_candidate: Optional[bool] = None
    confidence: Optional[str] = Field(default=None, max_length=32)


class LoadParseStopItem(BaseModel):
    """Normalized stop for workspace DraftStop hydration (types align with LoadStopWrite)."""

    stop_type: str = Field(..., description="pickup | delivery | drop | other")
    sequence: int = Field(..., ge=0)
    facility_name: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state_or_province: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    reference_number: Optional[str] = None
    appointment_type: Optional[str] = None
    appointment_date: Optional[str] = Field(
        default=None, description="YYYY-MM-DD when parseable"
    )
    appointment_time_text: Optional[str] = None
    notes: Optional[str] = None


class LoadParseExtractedFields(BaseModel):
    broker_name_snapshot: Optional[str] = Field(
        default=None,
        description="Broker company/entity tendering the load, not the individual agent.",
    )
    broker_phone_snapshot: Optional[str] = Field(
        default=None,
        description=(
            "Broker company's main/corporate phone, not the named agent's direct phone. "
            "Not shipper, receiver, carrier/tenant, or tracking/claims/payment phone unless "
            "that number is actually the broker's normal corporate/main phone."
        ),
    )
    broker_contact_name_snapshot: Optional[str] = Field(
        default=None,
        description="Selected individual broker agent/contact handling this load.",
    )
    broker_contact_phone_snapshot: Optional[str] = Field(
        default=None,
        description=(
            "Direct phone belonging to the selected named broker contact. "
            "Do not use broker corporate/main/general phone. "
            "If no person-owned direct phone is supported, null."
        ),
    )
    broker_contact_email_snapshot: Optional[str] = Field(
        default=None,
        description=(
            "Email belonging to the selected named broker contact. "
            "Generic company mailboxes such as carriers@, dispatch@, info@, operations@, "
            "billing@, accounting@, support@ do not belong here. "
            "If no person-owned email is supported, null."
        ),
    )
    broker_load_reference: Optional[str] = Field(
        default=None,
        description=(
            "Bare principal broker identifier only; source field label is not part of the value."
        ),
    )
    broker_mc_number_snapshot: Optional[str] = None
    broker_dot_number_snapshot: Optional[str] = None
    mode: Optional[str] = Field(
        default=None,
        description=(
            "Explicit load-level transportation mode. Do not infer from equipment, trailer "
            "type/size, weight, stop count, or rate."
        ),
    )
    equipment_type: Optional[str] = Field(
        default=None,
        description=(
            "Full source-faithful load-level equipment description explicitly assigned by the "
            "broker/document. May include equipment code, size, body/type, or a combined "
            "description. Do not remove type or size merely because trailer_type and "
            "trailer_size are also populated."
        ),
    )
    trailer_type: Optional[str] = Field(
        default=None,
        description=(
            "Trailer body/type required for this load. A body type embedded in a broader "
            "equipment description is valid evidence. Do not copy the full equipment "
            "description or size here."
        ),
    )
    trailer_size: Optional[str] = Field(
        default=None,
        description=(
            "Explicit trailer length/size required for this load. A length embedded in a "
            "broader equipment description is valid evidence. Do not copy the full equipment "
            "description here."
        ),
    )
    commodity: Optional[str] = None
    estimated_weight: Optional[int] = None
    temperature_requirement: Optional[str] = None
    rate: Optional[float] = None
    customer_rate: Optional[float] = None
    miles: Optional[float] = None
    customs_broker_name: Optional[str] = None
    references: list[LoadParseReferenceItem] = Field(default_factory=list)
    stops: list[LoadParseStopItem] = Field(default_factory=list)


class LoadDocumentParseResponse(BaseModel):
    document: LoadParseDocumentMeta
    extracted: LoadParseExtractedFields
    raw_text: str
    warnings: list[str] = Field(default_factory=list)
    field_confidence: dict[str, str] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class ParseDocumentSemanticModelOutput(BaseModel):
    """OpenAI ``json_schema`` output contract for the product guarded PDF parser.

    Excludes ``raw_text`` and ``context`` — the server attaches PDF text and allowlisted context.
    Extra root keys from the model are ignored (forward tolerance).
    """

    model_config = ConfigDict(extra="ignore")

    document: LoadParseDocumentMeta
    document_type: Optional[
        Literal[
            "rate_confirmation",
            "driver_information_sheet",
            "invoice",
            "bol",
            "other",
        ]
    ] = Field(
        default=None,
        description="Classify the PDF before filling extracted fields.",
    )
    classification_reasoning: Optional[str] = Field(
        default=None,
        max_length=1500,
        description="Brief justification for document_type and how stops/contacts were interpreted.",
    )
    extracted: LoadParseExtractedFields = Field(default_factory=LoadParseExtractedFields)
    warnings: list[str] = Field(default_factory=list)
    field_confidence: dict[str, str] = Field(default_factory=dict)
