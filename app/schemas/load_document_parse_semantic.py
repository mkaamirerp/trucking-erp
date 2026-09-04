"""OpenAI-only semantic extraction contract for Rate Confirmation parse.

Not the public LoadDocumentParseResponse / LoadParseExtractedFields product shape.
Backend maps this onto existing product fields after the model returns.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.load_document_parse import (
    LoadParseDocumentMeta,
    LoadParseReferenceItem,
    LoadParseStopItem,
)


class BrokerCompany(BaseModel):
    """Freight broker company that tendered this load."""

    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = Field(
        default=None,
        title="Name",
        description="Freight broker company/entity that tendered this load, not the individual agent.",
    )
    main_phone: Optional[str] = Field(
        default=None,
        title="Main Phone",
        description=(
            "Broker company's main/corporate phone, not the named agent's direct phone. "
            "Not shipper, receiver, carrier/tenant, or tracking/claims/payment phone unless "
            "that number is actually the broker's normal corporate/main phone."
        ),
    )
    mc_number: Optional[str] = Field(
        default=None,
        title="MC Number",
        description="MC authority number belonging to the selected broker company.",
    )
    dot_number: Optional[str] = Field(
        default=None,
        title="DOT Number",
        description="USDOT authority number belonging to the selected broker company.",
    )


class BrokerAgent(BaseModel):
    """Named individual broker agent handling this load."""

    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = Field(
        default=None,
        title="Name",
        description="Selected individual broker agent handling this load.",
    )
    direct_phone: Optional[str] = Field(
        default=None,
        title="Direct Phone",
        description=(
            "Direct phone belonging to the selected named broker agent. "
            "Do not use the broker company's main/corporate/general phone. "
            "If no person-owned direct phone is supported, null."
        ),
    )
    email: Optional[str] = Field(
        default=None,
        title="Email",
        description=(
            "Email belonging to the selected named broker agent. "
            "Generic company mailboxes such as carriers@, dispatch@, info@, operations@, "
            "billing@, accounting@, support@ do not belong here. "
            "If no person-owned email is supported, null."
        ),
    )


class EquipmentAssignment(BaseModel):
    """Load-level equipment description plus trailer body/length facets."""

    model_config = ConfigDict(extra="ignore")

    description: Optional[str] = Field(
        default=None,
        title="Description",
        description=(
            "Full source-faithful load-level equipment description explicitly assigned by the "
            "broker/document. May include equipment code, size, body/type, or a combined "
            "description. Do not remove type or size merely because trailer_body_type and "
            "trailer_length are also populated."
        ),
    )
    trailer_body_type: Optional[str] = Field(
        default=None,
        title="Trailer Body Type",
        description=(
            "Trailer body/type required for this load. A body type embedded in a broader "
            "equipment description is valid evidence. Do not copy the full equipment "
            "description or length here."
        ),
    )
    trailer_length: Optional[str] = Field(
        default=None,
        title="Trailer Length",
        description=(
            "Explicit trailer length/size required for this load. A length embedded in a "
            "broader equipment description is valid evidence. Do not copy the full equipment "
            "description here."
        ),
    )


def empty_semantic_extracted() -> SemanticExtractedFields:
    """Required structural containers with nullable children (no invented values)."""
    return SemanticExtractedFields(
        broker_company=BrokerCompany(),
        broker_agent=BrokerAgent(),
        equipment=EquipmentAssignment(),
    )


class SemanticExtractedFields(BaseModel):
    """AI-facing extracted object. Structural company/agent/equipment containers are required."""

    model_config = ConfigDict(extra="ignore")

    broker_company: BrokerCompany
    broker_agent: BrokerAgent
    equipment: EquipmentAssignment
    principal_load_identifier: Optional[str] = Field(
        default=None,
        title="Principal Load Identifier",
        description=(
            "The broker's principal identifier for this shipment/load. "
            "Return the identifier value only; source field label is not part of the value."
        ),
    )
    freight_mode: Optional[str] = Field(
        default=None,
        title="Freight Mode",
        description=(
            "Explicit load-level transportation mode. Do not infer from equipment, trailer "
            "body type/length, weight, stop count, or rate."
        ),
    )
    commodity: Optional[str] = Field(default=None, title="Commodity")
    estimated_weight: Optional[int] = Field(default=None, title="Estimated Weight")
    temperature_requirement: Optional[str] = Field(
        default=None, title="Temperature Requirement"
    )
    rate: Optional[float] = Field(default=None, title="Rate")
    customer_rate: Optional[float] = Field(default=None, title="Customer Rate")
    miles: Optional[float] = Field(default=None, title="Miles")
    customs_broker_name: Optional[str] = Field(default=None, title="Customs Broker Name")
    references: list[LoadParseReferenceItem] = Field(default_factory=list, title="References")
    stops: list[LoadParseStopItem] = Field(default_factory=list, title="Stops")


class ParseDocumentSemanticModelOutput(BaseModel):
    """OpenAI json_schema output contract for rate-confirmation extraction.

    Excludes raw_text and context — the server attaches PDF text and allowlisted context.
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
        title="Document Type",
        description="Classify the PDF before filling extracted fields.",
    )
    classification_reasoning: Optional[str] = Field(
        default=None,
        max_length=1500,
        title="Classification Reasoning",
        description="Brief justification for document_type and how stops and parties were interpreted.",
    )
    extracted: SemanticExtractedFields = Field(default_factory=empty_semantic_extracted)
    warnings: list[str] = Field(default_factory=list, title="Warnings")
    field_confidence: dict[str, str] = Field(default_factory=dict, title="Field Confidence")


def coerce_semantic_extracted(raw: Any) -> SemanticExtractedFields:
    """Parse model output into required containers; missing containers become null children.

    OpenAI json_schema is non-strict, so required objects may still be omitted on the wire.
    Missing containers are empty objects (all children null), never invented values.
    """
    data = dict(raw) if isinstance(raw, dict) else {}
    if not isinstance(data.get("broker_company"), dict):
        data["broker_company"] = {}
    if not isinstance(data.get("broker_agent"), dict):
        data["broker_agent"] = {}
    if not isinstance(data.get("equipment"), dict):
        data["equipment"] = {}
    return SemanticExtractedFields.model_validate(data)
