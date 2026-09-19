"""Fuel AI handoff envelope builder and source routing (Segment 5).

DIGITAL PDF: original PDF bytes + Fuel contract → OpenAI.
  Do NOT substitute native PDF text extraction as the digital AI input.

SCANNED/IMAGE PDF: acquisition/OCR → OCR text + Fuel contract → OpenAI.

STRUCTURED FILE: deterministic adapter; bypass AI.

Does not call OpenAI. Does not implement BVD/Nationwide provider parsers.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Final, Literal, Mapping, Sequence

from app.services.fuel_ai_contract import (
    HANDOFF_VERSION,
    PROFILE,
    load_fuel_ai_handoff_contract,
    parser_rule_version_for_persistence,
)
from app.services.fuel_canonical import SOURCE_TYPE_STRUCTURED_FILE
from app.services.fuel_provider_profile import (
    combined_parser_rule_version,
    get_provider_profile_for_code,
    load_provider_profile,
)

AiInputMode = Literal[
    "original_pdf_bytes_plus_contract",
    "ocr_text_plus_contract",
    "structured_adapter_bypass_ai",
]

SourceClass = Literal[
    "digital_pdf",
    "scanned_image_pdf",
    "structured_file",
    "unknown",
]

ROUTE_DIGITAL_PDF: Final[str] = "DIGITAL_PDF_ORIGINAL_BYTES"
ROUTE_SCANNED_OCR: Final[str] = "SCANNED_OCR_TEXT"
ROUTE_STRUCTURED_BYPASS: Final[str] = "STRUCTURED_ADAPTER_BYPASS_AI"
ROUTE_REVIEW: Final[str] = "REVIEW_SOURCE_CLASS_UNKNOWN"


@dataclass(frozen=True)
class FuelAiRoute:
    route: str
    source_class: SourceClass
    ai_input_mode: AiInputMode | None
    bypass_ai: bool
    reason: str | None = None


def route_fuel_source_for_ai(
    *,
    source_type: str | None = None,
    pdf_source_class: str | None = None,
) -> FuelAiRoute:
    """Decide AI input mode. Explicit source class wins; no RateCon threshold copy."""
    st = (source_type or "").strip().upper()
    if st == SOURCE_TYPE_STRUCTURED_FILE or st in {"STRUCTURED", "CSV", "DAT", "EXPORT"}:
        return FuelAiRoute(
            route=ROUTE_STRUCTURED_BYPASS,
            source_class="structured_file",
            ai_input_mode="structured_adapter_bypass_ai",
            bypass_ai=True,
        )

    klass = (pdf_source_class or "").strip().lower()
    if klass in {"digital_pdf", "digital_text", "digital"}:
        return FuelAiRoute(
            route=ROUTE_DIGITAL_PDF,
            source_class="digital_pdf",
            ai_input_mode="original_pdf_bytes_plus_contract",
            bypass_ai=False,
        )
    if klass in {"scanned_image_pdf", "scanned_image", "scanned", "ocr"}:
        return FuelAiRoute(
            route=ROUTE_SCANNED_OCR,
            source_class="scanned_image_pdf",
            ai_input_mode="ocr_text_plus_contract",
            bypass_ai=False,
        )
    return FuelAiRoute(
        route=ROUTE_REVIEW,
        source_class="unknown",
        ai_input_mode=None,
        bypass_ai=True,
        reason="SOURCE_CLASS_UNKNOWN",
    )


def _normalize_ocr_pages(page_texts: Sequence[Any]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for idx, item in enumerate(page_texts):
        if isinstance(item, Mapping):
            text = str(item.get("text") or "")
            raw_num = item.get("page_number", item.get("page"))
            try:
                page_number = int(raw_num) if raw_num is not None else idx + 1
            except (TypeError, ValueError):
                page_number = idx + 1
        else:
            text = str(item or "")
            page_number = idx + 1
        pages.append({"page_number": page_number, "text": text})
    return pages


def build_fuel_ai_handoff_payload(
    *,
    route: FuelAiRoute,
    filename: str,
    content_type: str = "application/pdf",
    size_bytes: int | None = None,
    pdf_bytes_ref: str | None = None,
    ocr_pages: Sequence[Any] | None = None,
    expected_provider: str | None = None,
    provider_profile_code: str | None = None,
    # Defense: callers must not pass digital native text as AI input.
    digital_embedded_text: str | None = None,
) -> dict[str, Any]:
    """Build the Fuel OpenAI handoff envelope (no HTTP).

    For digital PDF, ``document.ai_input`` is the original PDF reference only.
    Passing ``digital_embedded_text`` raises — native text must not substitute.

    ``provider_profile_code`` is the provider key (``BVD`` / ``NATIONWIDE``) used
    to attach the current profile section from the master profiles JSON.
    Profiles are data — not a separate parser engine.
    """
    profile_doc: dict[str, Any] | None = None
    if provider_profile_code:
        profile_doc = copy.deepcopy(load_provider_profile(provider_profile_code))
    elif expected_provider:
        found = get_provider_profile_for_code(expected_provider)
        if found is not None:
            profile_doc = found

    if route.source_class == "digital_pdf" and digital_embedded_text is not None:
        raise ValueError(
            "Fuel digital PDF AI input must be original PDF bytes + contract; "
            "do not substitute native PDF text extraction."
        )
    if route.bypass_ai and route.route == ROUTE_STRUCTURED_BYPASS:
        contract = load_fuel_ai_handoff_contract()
        rule_version = combined_parser_rule_version(
            handoff_version=parser_rule_version_for_persistence(contract),
            profile=profile_doc,
        )
        return {
            "handoff_version": HANDOFF_VERSION,
            "profile": PROFILE,
            "parser_rule_version": rule_version,
            "bypass_ai": True,
            "route": route.route,
            "acquisition": {
                "filename": (filename or "upload.bin")[:512],
                "content_type": content_type,
                "source_class": route.source_class,
                "ai_input_mode": route.ai_input_mode,
                "size_bytes": size_bytes,
            },
            "contract": copy.deepcopy(contract),
            "provider_profile": profile_doc,
            "document": None,
        }

    if route.ai_input_mode is None:
        raise ValueError(f"Cannot build Fuel AI handoff for route={route.route}")

    contract = load_fuel_ai_handoff_contract()
    contract = copy.deepcopy(contract)
    if expected_provider:
        contract.setdefault("provider_context", {})
        contract["provider_context"]["expected_provider"] = expected_provider
    if profile_doc is not None:
        contract.setdefault("provider_context", {})
        contract["provider_context"]["provider_code"] = profile_doc.get("provider_code")
        contract["provider_context"]["provider_profile_version"] = profile_doc.get(
            "profile_version"
        )
        contract["provider_context"].pop("provider_profile_code", None)

    acquisition: dict[str, Any] = {
        "filename": (filename or "upload.pdf")[:512],
        "content_type": content_type,
        "source_class": route.source_class,
        "ai_input_mode": route.ai_input_mode,
        "embedded_text_substituted": False,
    }
    if size_bytes is not None:
        acquisition["size_bytes"] = int(size_bytes)

    document: dict[str, Any]
    if route.ai_input_mode == "original_pdf_bytes_plus_contract":
        if not pdf_bytes_ref:
            raise ValueError("digital PDF handoff requires pdf_bytes_ref")
        document = {
            "ai_input": "original_pdf_bytes",
            "pdf_bytes_ref": pdf_bytes_ref,
            # Explicitly absent: pages / full_text must not be used as digital AI input.
            "pages": None,
            "full_text": None,
        }
    else:
        pages = _normalize_ocr_pages(ocr_pages or [])
        document = {
            "ai_input": "ocr_text",
            "pdf_bytes_ref": pdf_bytes_ref,
            "pages": pages,
            "full_text": "\n".join(p["text"] for p in pages),
        }

    rule_version = combined_parser_rule_version(
        handoff_version=parser_rule_version_for_persistence(contract),
        profile=profile_doc,
    )
    return {
        "handoff_version": HANDOFF_VERSION,
        "profile": PROFILE,
        "parser_rule_version": rule_version,
        "bypass_ai": False,
        "route": route.route,
        "acquisition": acquisition,
        "contract": contract,
        "provider_profile": profile_doc,
        "document": document,
    }


def persist_parser_rule_version_on_batch(batch: Any, *, handoff: Mapping[str, Any] | None = None) -> str:
    """Write parser_rule_version onto a fuel_source_batches-like object."""
    version = (
        str(handoff.get("parser_rule_version"))
        if handoff and handoff.get("parser_rule_version")
        else parser_rule_version_for_persistence()
    )
    batch.parser_rule_version = version
    return version
