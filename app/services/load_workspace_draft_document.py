"""Persist rate-confirmation PDF + accepted parse on a load workspace draft."""

from __future__ import annotations

import copy
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency.draft_conflicts import workspace_draft_version_conflict_exception
from app.core.storage import get_storage
from app.models.load_workspace_draft import LoadWorkspaceDraft
from app.schemas.load_document_parse import (
    LoadDocumentParseResponse,
    strip_nul_bytes_from_json_tree,
)
from app.services.load_document_parse_orchestrator import parse_load_workspace_document_orchestrated
from app.services.load_parser_pdf_safety import UnsafeLoadPdfError, validate_load_parser_pdf
from app.services.load_workspace_draft_lifecycle import require_workspace_draft_open_for_mutation
from app.services.load_workspace_draft_mapper import normalize_load_miles_value

LOAD_WORKSPACE_DRAFT_PDF_MODULE = "load_workspace_draft"
WORKSPACE_DRAFT_ACCEPTED_PARSE_SCHEMA_VERSION = "load_document_parse_response_v1"
MAX_PDF_BYTES = 20 * 1024 * 1024
EDITABLE_STATUS = "draft"


async def _read_bounded_pdf(file: UploadFile) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = await file.read(1024 * 1024)
        if not piece:
            break
        total += len(piece)
        if total > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="PDF too large",
            )
        chunks.append(piece)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    filename = (file.filename or "upload.pdf")[:512]
    return data, filename


def accepted_parse_from_response(parse: LoadDocumentParseResponse) -> dict:
    return strip_nul_bytes_from_json_tree(parse.model_dump(mode="json"))


_REVISED_PDF_KEY = "_revised_pdf"
_REVISED_PDFS_KEY = "_revised_pdfs"
_MISSING = object()
_INDEXED_FIELD = re.compile(r"^([A-Za-z0-9_]+)\[(\d+)\](?:\.([A-Za-z0-9_]+))?$")

_SCALAR_FIELDS = (
    "broker_name_snapshot",
    "broker_contact_name_snapshot",
    "broker_contact_phone_snapshot",
    "broker_contact_extension_snapshot",
    "broker_contact_email_snapshot",
    "broker_load_reference",
    "mode",
    "equipment_type",
    "trailer_type",
    "trailer_size",
    "commodity",
    "estimated_weight",
    "hazmat_flag",
    "temperature_requirement",
    "pallet_case_count",
    "rate",
    "customer_rate",
    "miles",
)

# Scalars compared during Re-parse (customer_rate is stored but never suggested).
_REPARSE_COMPARABLE_SCALARS = tuple(name for name in _SCALAR_FIELDS if name != "customer_rate")

# Load row fields kept in verified JSON for a complete baseline (not PDF-suggested).
_LOAD_FORM_PERSISTED_KEYS = (
    "load_number",
    "status",
    "driver_id",
    "truck_id",
    "trailer_id",
    "customs_broker_id",
    "broker_id",
    "broker_contact_id",
)

_STOP_FIELDS = (
    "stop_type",
    "facility_name",
    "street",
    "city",
    "state_or_province",
    "postal_code",
    "country",
    "reference_number",
    "appointment_type",
    "appointment_date",
    "appointment_time_text",
    "notes",
)

_DRAFT_KEYS_TO_EXTRACTED = (
    (("brokerNameSnapshot", "broker_name_snapshot"), "broker_name_snapshot"),
    (("brokerContactNameSnapshot", "broker_contact_name_snapshot"), "broker_contact_name_snapshot"),
    (("brokerContactPhoneSnapshot", "broker_contact_phone_snapshot"), "broker_contact_phone_snapshot"),
    (("brokerContactExtensionSnapshot", "broker_contact_extension_snapshot"), "broker_contact_extension_snapshot"),
    (("brokerContactEmailSnapshot", "broker_contact_email_snapshot"), "broker_contact_email_snapshot"),
    (("brokerLoadReference", "broker_load_reference"), "broker_load_reference"),
    (("freightMode", "mode"), "mode"),
    (("equipmentType", "equipment_type"), "equipment_type"),
    (("trailerType", "trailer_type"), "trailer_type"),
    (("trailerSize", "trailer_size"), "trailer_size"),
    (("commodity",), "commodity"),
    (("estimatedWeight", "estimated_weight"), "estimated_weight"),
    (("hazmat", "hazmat_flag"), "hazmat_flag"),
    (("temperatureRequirement", "temperature_requirement"), "temperature_requirement"),
    (("palletCaseCount", "pallet_case_count"), "pallet_case_count"),
    (("rate",), "rate"),
    (("customerRate", "customer_rate"), "customer_rate"),
    (("miles",), "miles"),
    (("draftStops", "stops"), "stops"),
    (("loadReferences", "references"), "references"),
)


def extracted_fields_in_draft(draft_json: dict | None) -> set[str]:
    """Mapped parser fields the dispatcher form actually sent."""
    if not isinstance(draft_json, dict):
        return set()
    found: set[str] = set()
    for keys, extracted in _DRAFT_KEYS_TO_EXTRACTED:
        if any(key in draft_json for key in keys):
            found.add(extracted)
    return found


def _read(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _decimal_or_none(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.replace("$", "").replace(",", "").strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


def _miles_values_equivalent(left: Any, right: Any) -> bool | None:
    """None when neither side is mileage-like (caller uses generic rules)."""
    left_blank = _blank(left)
    right_blank = _blank(right)
    if left_blank and right_blank:
        return True
    try:
        left_m = normalize_load_miles_value(left) if not left_blank else None
        right_m = normalize_load_miles_value(right) if not right_blank else None
    except ValueError:
        return None
    if left_m is None or right_m is None:
        return False
    return left_m == right_m


def values_equivalent(left: Any, right: Any) -> bool:
    """True when the saved JSON already says what the form says."""
    if left is None and (right is None or right == ""):
        return True
    if right is None and (left is None or left == ""):
        return True
    miles_eq = _miles_values_equivalent(left, right)
    if miles_eq is not None:
        return miles_eq
    left_num = _decimal_or_none(left)
    right_num = _decimal_or_none(right)
    if left_num is not None and right_num is not None:
        return left_num == right_num
    if isinstance(left, date) and not isinstance(left, datetime):
        left = left.isoformat()
    if isinstance(right, date) and not isinstance(right, datetime):
        right = right.isoformat()
    return str(left).strip() == str(right).strip()


def _json_ready(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return format(Decimal(str(value)), "f")
    return str(value).strip() or None


def _patch_key(target: dict, key: str, form_value: Any) -> None:
    current = target.get(key, _MISSING)
    ready = _json_ready(form_value)
    if current is not _MISSING and values_equivalent(current, ready):
        return
    target[key] = ready


def _reference_pairs(value: Any) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        return []
    pairs: list[tuple[str, str]] = []
    for item in value:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if not isinstance(item, dict):
            continue
        pairs.append((str(item.get("kind") or "").strip(), str(item.get("value") or "").strip()))
    return pairs


def reconcile_accepted_parse_json(
    accepted: dict | None,
    form: Any,
    *,
    only_fields: set[str] | None = None,
) -> dict:
    """Copy the parser JSON and make mapped fields match the final form.

    Fields the form does not map are left as the parser returned them.
    A mapped field that already matches is left unchanged.
    """
    out = copy.deepcopy(accepted) if isinstance(accepted, dict) else {}
    extracted = out.get("extracted")
    if not isinstance(extracted, dict):
        extracted = {}
        out["extracted"] = extracted
    selected = set(_SCALAR_FIELDS) | {"stops", "references"} if only_fields is None else set(only_fields)

    for key in _SCALAR_FIELDS:
        if key not in selected:
            continue
        _patch_key(extracted, key, _read(form, key))

    if "references" in selected:
        form_refs = _read(form, "references")
        if _reference_pairs(extracted.get("references")) != _reference_pairs(form_refs):
            dumped: list[dict] = []
            for item in form_refs or []:
                if hasattr(item, "model_dump"):
                    dumped.append(item.model_dump(mode="json"))
                elif isinstance(item, dict):
                    dumped.append(dict(item))
            extracted["references"] = dumped

    if "stops" in selected:
        form_stops = _read(form, "stops")
        if form_stops is not None:
            json_stops = extracted.get("stops")
            if not isinstance(json_stops, list):
                json_stops = []
            rebuilt: list[dict] = []
            for index, stop in enumerate(form_stops):
                base = json_stops[index] if index < len(json_stops) and isinstance(json_stops[index], dict) else {}
                base = copy.deepcopy(base)
                for key in _STOP_FIELDS:
                    _patch_key(base, key, _read(stop, key))
                rebuilt.append(base)
            extracted["stops"] = rebuilt

    if only_fields is None:
        for key in _LOAD_FORM_PERSISTED_KEYS:
            _patch_key(extracted, key, _read(form, key))
    return strip_nul_bytes_from_json_tree(out)


def parse_json_for_compare(accepted: dict | None) -> dict:
    """Verified JSON sent to the comparison call, without stored file pointers."""
    out = copy.deepcopy(accepted) if isinstance(accepted, dict) else {}
    out.pop(_REVISED_PDF_KEY, None)
    out.pop(_REVISED_PDFS_KEY, None)
    out.pop("raw_text", None)
    return out


def revised_pdf_records(accepted: dict | None) -> list[dict]:
    """Accepted revised PDFs, oldest first. The original file is not in this list."""
    if not isinstance(accepted, dict):
        return []
    records = accepted.get(_REVISED_PDFS_KEY)
    if isinstance(records, list):
        return [dict(item) for item in records if isinstance(item, dict) and str(item.get("storage_key") or "").strip()]
    single = accepted.get(_REVISED_PDF_KEY)
    if isinstance(single, dict) and str(single.get("storage_key") or "").strip():
        return [dict(single)]
    return []


def without_client_pdf_pointers(accepted: dict | None) -> dict:
    """Drop file pointers a client might submit inside a parse JSON."""
    out = copy.deepcopy(accepted) if isinstance(accepted, dict) else {}
    out.pop(_REVISED_PDF_KEY, None)
    out.pop(_REVISED_PDFS_KEY, None)
    return out


def append_revised_pdf(verified: dict, prior: dict | None, pointer: dict) -> dict:
    """Keep every previously accepted revised PDF and add the new one."""
    records = revised_pdf_records(prior)
    records.append(dict(pointer))
    verified[_REVISED_PDFS_KEY] = records
    verified.pop(_REVISED_PDF_KEY, None)
    return verified


def _normalize_field_path(field: str) -> str:
    text = field.strip()
    if text.startswith("extracted."):
        text = text[len("extracted.") :]
    return text


def _resolve_extracted(extracted: Any, field: str) -> Any:
    if not isinstance(extracted, dict):
        return _MISSING
    indexed = _INDEXED_FIELD.match(field)
    if indexed:
        name, index_text, child = indexed.group(1), indexed.group(2), indexed.group(3)
        sequence = extracted.get(name, _MISSING)
        if sequence is _MISSING or not isinstance(sequence, list):
            return _MISSING
        index = int(index_text)
        if index >= len(sequence) or not isinstance(sequence[index], dict):
            return _MISSING
        if child is None:
            return sequence[index]
        if child not in sequence[index]:
            return _MISSING
        return sequence[index][child]
    if field not in extracted:
        return _MISSING
    return extracted[field]


def field_is_editable(field: str) -> bool:
    """True when Change can write this path onto the load form."""
    if field in _SCALAR_FIELDS:
        return True
    indexed = _INDEXED_FIELD.match(field)
    if not indexed:
        return False
    name, child = indexed.group(1), indexed.group(3)
    if name == "stops" and child in _STOP_FIELDS:
        return True
    if name == "references" and child in {"kind", "value"}:
        return True
    return False


def extract_reparse_pdf_plain_text(pdf_bytes: bytes) -> str:
    """Local text only for re-parse. Never sends PDF bytes to the semantic LLM."""
    from app.services.load_parser_pdf_acquisition import PDF_SCANNED, acquire_load_parser_pdf_pages
    from app.services.load_parser_pdf_ocr import ocr_load_parser_pdf_pages

    validate_load_parser_pdf(pdf_bytes)
    acquisition = acquire_load_parser_pdf_pages(pdf_bytes)
    page_objs = list(acquisition.get("pages") or [])
    if acquisition.get("requires_ocr") and acquisition.get("pdf_type") != PDF_SCANNED:
        raise ValueError(
            "ocr_required: mixed digital/scanned PDF; OCR fallback applies only to "
            "image-only PDFs with no usable embedded text — re-parse was not attempted."
        )
    if acquisition.get("pdf_type") == PDF_SCANNED:
        ocr_pages, _warnings = ocr_load_parser_pdf_pages(pdf_bytes)
        if not ocr_pages:
            raise ValueError("ocr_failed: image-only PDF could not be OCR'd — re-parse was not attempted.")
        return "\n".join(str(p.get("text") or "") for p in ocr_pages).strip()
    usable = [
        str(p.get("text") or "")
        for p in page_objs
        if isinstance(p, dict) and not p.get("requires_ocr")
    ]
    return "\n".join(usable).strip()


def reparse_text_document_block_reason(pdf_text: str) -> str | None:
    """Hard stop when local text is not a usable rate confirmation (no second classifier)."""
    text = (pdf_text or "").strip()
    if len(text) < 80:
        return "This PDF could not be read clearly enough to re-parse. No Load information has changed."
    lowered = text.casefold()
    if any(token in lowered for token in ("fuel invoice", "bvd invoice", "comdata", "efs llc")):
        return "This appears to be a fuel invoice, not a carrier rate confirmation. No Load information has changed."
    if "bill of lading" in lowered and "rate confirmation" not in lowered:
        return "This appears to be a bill of lading, not a carrier rate confirmation. No Load information has changed."
    if "driver information" in lowered and "rate confirmation" not in lowered:
        return "This appears to be a driver information sheet, not a carrier rate confirmation. No Load information has changed."
    if any(
        token in lowered
        for token in (
            "rate confirmation",
            "rate con",
            "load confirmation",
            "linehaul",
            "line haul",
            "broker load",
        )
    ):
        return None
    if "pickup" in lowered and "delivery" in lowered:
        return None
    return "This PDF could not be classified as a carrier rate confirmation. No Load information has changed."


def reparse_document_block_reason(revised: dict | None) -> str | None:
    """Block a re-parse when the existing parser did not accept a usable rate confirmation.

    ``document_type`` and ``classification_reasoning`` come from that parser. This does
    not start another classifier.
    """
    document = revised if isinstance(revised, dict) else {}
    context = document.get("context") if isinstance(document.get("context"), dict) else {}
    doc_type = str(context.get("document_type") or "").strip().casefold()
    reasoning = str(context.get("classification_reasoning") or "")
    if doc_type == "rate_confirmation":
        if _has_commercial_shipment_evidence(document.get("extracted")):
            return None
        return "This PDF does not contain enough shipment information to re-parse. No Load information has changed."
    if doc_type == "invoice":
        kind = "a fuel invoice" if any(word in reasoning.casefold() for word in ("fuel", "bvd")) else "an invoice"
        return f"This appears to be {kind}, not a carrier rate confirmation. No Load information has changed."
    if doc_type == "bol":
        return "This appears to be a bill of lading, not a carrier rate confirmation. No Load information has changed."
    if doc_type == "driver_information_sheet":
        return "This appears to be a driver information sheet, not a carrier rate confirmation. No Load information has changed."
    if not doc_type:
        return "This PDF could not be classified as a carrier rate confirmation. No Load information has changed."
    return "This PDF is not a carrier rate confirmation. No Load information has changed."


def classify_load_pdf_reuse(evidence: Any, pdf_bytes: bytes) -> str:
    """Determine provenance only; re-reading the same PDF is not a duplicate write.

    Save must independently recompute this from trusted evidence. Reusing a PDF
    never authorizes appending the same bytes to the evidence history.
    """
    import hashlib

    digest = hashlib.sha256(pdf_bytes).hexdigest()
    original = str(getattr(evidence, "file_sha256", "") or "").strip().lower()
    records = revised_pdf_records(getattr(evidence, "accepted_parse_json", None))
    history = [str(item.get("sha256") or "").strip().lower() for item in records]
    history = [value for value in history if value]
    if original and digest == original:
        return "existing_prior_original" if history else "existing_original"
    if history and digest == history[-1]:
        return "existing_latest_revision"
    if digest in history:
        return "existing_prior_revision"
    return "new_revision"


def known_pdf_reuse_message(evidence: Any, pdf_bytes: bytes) -> str | None:
    """Compatibility with the existing duplicate-attachment detection API."""
    status = classify_load_pdf_reuse(evidence, pdf_bytes)
    if status in {"existing_original", "existing_latest_revision", "existing_prior_original"}:
        return "This PDF is already on the Load."
    if status == "existing_prior_revision":
        return "This is a previously accepted version, not a new revision."
    return None


def _has_commercial_shipment_evidence(extracted: Any) -> bool:
    if not isinstance(extracted, dict):
        return False
    if str(extracted.get("broker_name_snapshot") or "").strip():
        return True
    if str(extracted.get("broker_load_reference") or "").strip():
        return True
    pickups = [stop for stop in _stop_dicts(extracted) if _stop_type(stop) == "pickup" and _norm_place(_read(stop, "city"))]
    deliveries = [stop for stop in _stop_dicts(extracted) if _stop_type(stop) == "delivery" and _norm_place(_read(stop, "city"))]
    return bool(pickups and deliveries)


def _stop_dicts(extracted: Any) -> list[dict]:
    if not isinstance(extracted, dict):
        return []
    stops = extracted.get("stops")
    if not isinstance(stops, list):
        return []
    return [stop for stop in stops if isinstance(stop, dict)]


def _stop_type(stop: Any) -> str:
    return str(_read(stop, "stop_type") or "").strip().casefold()


def _norm_place(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _norm_ref(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).casefold()


def _norm_labeled_ref(value: Any) -> str:
    """Drop a leading PO/REF/BOL label. The remaining digits, including leading zeros, stay."""
    text = str(value or "").strip()
    text = re.sub(
        r"^(?:p\.?\s*o\.?|purchase\s+order|ref(?:erence)?|bol|order)\s*[#:]\s*",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    return _norm_ref(text)


def _norm_temperature(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("º", "°")
    text = text.replace("degrees", "").replace("degree", "")
    text = re.sub(r"\s+", "", text).replace("°", "")
    return text.replace("fahrenheit", "f").replace("celsius", "c")


def _norm_equipment(value: Any) -> str:
    text = _norm_place(value)
    return {
        "ftl": "full truckload",
        "full truck load": "full truckload",
        "ltl": "less than truckload",
        "less than truck load": "less than truckload",
    }.get(text, text)


def _norm_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text.casefold()


def _norm_time(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip().casefold()).replace(".", "")
    matched = re.match(r"^0*(\d{1,2}):(\d{2})(?::\d{2})?(am|pm)?$", text)
    if not matched:
        return text
    return f"{int(matched.group(1))}:{matched.group(2)}{matched.group(3) or ''}"


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _omitted_default(value: Any) -> bool:
    """False, blank, or unset was not a value the PDF stated."""
    return value is False or _blank(value)


def _revised_reference_repeats_changed_broker_load(_saved_extracted: dict, revised_extracted: dict, value: Any) -> bool:
    """The broker load number already has its own row. Do not list that same value again."""
    revised_ref = revised_extracted.get("broker_load_reference")
    if _blank(revised_ref):
        return False
    return reparse_values_equivalent("broker_load_reference", value, revised_ref)


def reparse_values_equivalent(field: str, left: Any, right: Any) -> bool:
    """Field-aware equality for re-parse differences. Leading zeros in references stay significant."""
    if _blank(left) and _blank(right):
        return True
    if _blank(left) or _blank(right):
        return False
    leaf = field.rsplit(".", 1)[-1]
    if field == "broker_load_reference" or leaf in {"value", "broker_load_reference", "reference_number"}:
        return _norm_labeled_ref(left) == _norm_labeled_ref(right)
    if leaf == "appointment_date":
        return _norm_date(left) == _norm_date(right)
    if leaf == "appointment_time_text":
        return _norm_time(left) == _norm_time(right)
    if field == "temperature_requirement" or leaf == "temperature_requirement":
        return _norm_temperature(left) == _norm_temperature(right)
    if leaf in {"stop_type", "appointment_type"} or field in {"mode", "equipment_type", "trailer_type"}:
        return _norm_equipment(left) == _norm_equipment(right)
    if leaf in {"street", "city", "state_or_province", "facility_name", "country"}:
        return _norm_place(left) == _norm_place(right)
    if field == "miles" or leaf == "miles":
        miles_eq = _miles_values_equivalent(left, right)
        if miles_eq is not None:
            return miles_eq
        return False
    if field in {"rate", "customer_rate"} or leaf in {"rate", "customer_rate", "estimated_weight", "pallet_case_count"}:
        left_num = _decimal_or_none(left)
        right_num = _decimal_or_none(right)
        if left_num is not None and right_num is not None:
            return left_num == right_num
    return str(left).strip() == str(right).strip()


def _money_text(value: Any) -> str:
    number = _decimal_or_none(value)
    if number is None:
        return str(value)
    if number == number.to_integral():
        return f"${int(number):,}"
    return f"${number:,.2f}"


def _party_name(value: Any) -> str:
    parts = [part for part in _norm_place(value).split() if part not in {"inc", "llc", "ltd", "co", "company", "corp", "corporation"}]
    return " ".join(parts)


def _names_match(left: Any, right: Any, aliases: list[str] | None = None) -> bool:
    a, b = _party_name(left), _party_name(right)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 5 and (longer == shorter or longer.startswith(shorter + " ")):
        return True
    known = {_party_name(alias) for alias in aliases or []}
    known.discard("")
    return bool(known) and a in known and b in known


def _first_stop(extracted: Any, stop_type: str) -> dict | None:
    for stop in _stop_dicts(extracted):
        if _stop_type(stop) == stop_type:
            return stop
    return None


def _document_dates(document: dict) -> str:
    extracted = document.get("extracted") if isinstance(document.get("extracted"), dict) else {}
    context = document.get("context") if isinstance(document.get("context"), dict) else {}
    for source in (extracted, context):
        for key in ("issue_date", "document_date", "revised_date", "confirmation_date", "rate_confirmation_date"):
            found = _norm_date(source.get(key))
            if found:
                return found
    return ""


def _stop_token(stop: Any, key: str) -> str:
    if key == "reference_number":
        return _norm_ref(_read(stop, key))
    return _norm_place(_read(stop, key))


_GENERIC_FACILITY_WORDS = {
    "warehouse",
    "distribution",
    "center",
    "centre",
    "dc",
    "dock",
    "terminal",
    "yard",
    "facility",
    "plant",
    "location",
    "shipper",
    "receiver",
    "consignee",
    "customer",
    "stop",
    "pickup",
    "delivery",
    "origin",
    "destination",
    "site",
    "building",
    "crossdock",
}


def _generic_facility(value: Any) -> bool:
    """A facility label with no distinctive name is not a stop identity."""
    words = [word for word in _stop_token({"facility_name": value}, "facility_name").split() if word]
    if not words:
        return True
    return not any(word not in _GENERIC_FACILITY_WORDS and not word.isdigit() for word in words)


def _stops_conflict(saved: Any, revised: Any) -> bool:
    """Conflicting street, reference, or location evidence blocks a confident match.

    A matching street still allows a city, facility, ZIP, or appointment amendment.
    It does not override a different stop reference. A generic facility name does
    not override a different street. City alone is not an identity.
    """
    if _stop_type(saved) != _stop_type(revised):
        return True
    street_left, street_right = _stop_token(saved, "street"), _stop_token(revised, "street")
    if street_left and street_right and street_left != street_right:
        return True
    reference_left, reference_right = _stop_token(saved, "reference_number"), _stop_token(revised, "reference_number")
    if reference_left and reference_right and reference_left != reference_right:
        return True
    if street_left and street_right and street_left == street_right:
        return False
    facility_left, facility_right = _stop_token(saved, "facility_name"), _stop_token(revised, "facility_name")
    if (
        facility_left
        and facility_right
        and facility_left != facility_right
        and not _generic_facility(facility_left)
        and not _generic_facility(facility_right)
    ):
        return True
    reference_left, reference_right = _stop_token(saved, "reference_number"), _stop_token(revised, "reference_number")
    if reference_left and reference_right and reference_left != reference_right:
        return True
    if _stops_share_specific_id(saved, revised):
        return False
    for key in ("city", "state_or_province"):
        left, right = _stop_token(saved, key), _stop_token(revised, key)
        if left and right and left != right:
            return True
    return False


def _stops_share_specific_id(saved: Any, revised: Any) -> bool:
    street_left, street_right = _stop_token(saved, "street"), _stop_token(revised, "street")
    if street_left and street_right and street_left == street_right:
        return True
    reference_left, reference_right = _stop_token(saved, "reference_number"), _stop_token(revised, "reference_number")
    if reference_left and reference_right and reference_left == reference_right:
        return True
    facility_left, facility_right = _stop_token(saved, "facility_name"), _stop_token(revised, "facility_name")
    return bool(
        facility_left
        and facility_right
        and facility_left == facility_right
        and not _generic_facility(facility_left)
    )


def _stops_share_city(saved: Any, revised: Any) -> bool:
    if _stop_type(saved) != _stop_type(revised):
        return False
    city_left, city_right = _stop_token(saved, "city"), _stop_token(revised, "city")
    state_left, state_right = _stop_token(saved, "state_or_province"), _stop_token(revised, "state_or_province")
    return bool(city_left and city_right and city_left == city_right and state_left == state_right)


def _pair_stops(saved_stops: list[dict], revised_stops: list[dict]) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Pair stops only when the same candidate is unique from both sides.

    A unique matching reference wins when the street and other evidence agree.
    A shared street without a distinguishing reference stays unpaired. A city
    pair is only a candidate. Field changes require `_stop_pair_is_confident`.
    """
    pairs: list[tuple[int, int]] = []
    used_saved: set[int] = set()
    used_revised: set[int] = set()

    def claim(saved_index: int, revised_index: int) -> None:
        used_saved.add(saved_index)
        used_revised.add(revised_index)
        pairs.append((saved_index, revised_index))

    def claim_unique(predicate) -> None:
        candidates: list[tuple[int, int]] = []
        for saved_index, saved in enumerate(saved_stops):
            if saved_index in used_saved:
                continue
            for revised_index, revised in enumerate(revised_stops):
                if revised_index in used_revised:
                    continue
                if predicate(saved, revised):
                    candidates.append((saved_index, revised_index))
        saved_hits: dict[int, list[int]] = {}
        revised_hits: dict[int, list[int]] = {}
        for saved_index, revised_index in candidates:
            saved_hits.setdefault(saved_index, []).append(revised_index)
            revised_hits.setdefault(revised_index, []).append(saved_index)
        for saved_index, revised_indexes in saved_hits.items():
            if len(revised_indexes) != 1:
                continue
            revised_index = revised_indexes[0]
            if len(revised_hits[revised_index]) == 1:
                claim(saved_index, revised_index)

    def reference_compatible(saved: Any, revised: Any) -> bool:
        left, right = _stop_token(saved, "reference_number"), _stop_token(revised, "reference_number")
        return bool(left and right and left == right and not _stops_conflict(saved, revised))

    claim_unique(reference_compatible)
    claim_unique(lambda saved, revised: _stops_share_specific_id(saved, revised) and not _stops_conflict(saved, revised))
    claim_unique(lambda saved, revised: _stops_share_city(saved, revised) and not _stops_conflict(saved, revised))
    return pairs, [index for index in range(len(saved_stops)) if index not in used_saved], [
        index for index in range(len(revised_stops)) if index not in used_revised
    ]


def _stop_pair_is_confident(saved: Any, revised: Any) -> bool:
    """A field Change needs a unique reliable identifier and no contradictory reference."""
    return _stops_share_specific_id(saved, revised) and not _stops_conflict(saved, revised)


def _stops_share_weak_signal(saved: Any, revised: Any) -> bool:
    if _stop_type(saved) != _stop_type(revised):
        return False
    if _stops_share_city(saved, revised) or _stops_share_specific_id(saved, revised):
        return True
    facility_left, facility_right = _stop_token(saved, "facility_name"), _stop_token(revised, "facility_name")
    return bool(facility_left and facility_left == facility_right)


def _classify_stop_matches(
    saved_stops: list[dict], revised_stops: list[dict]
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[int], list[int]]:
    """Split pairs into confident edits, review-only candidates, and unmatched stops."""
    pairs, unmatched_saved, unmatched_revised = _pair_stops(saved_stops, revised_stops)
    confident: list[tuple[int, int]] = []
    review: list[tuple[int, int]] = []
    for saved_index, revised_index in pairs:
        if _stop_pair_is_confident(saved_stops[saved_index], revised_stops[revised_index]):
            confident.append((saved_index, revised_index))
        else:
            review.append((saved_index, revised_index))
    used_saved = {saved_index for saved_index, _revised_index in pairs}
    used_revised = {revised_index for _saved_index, revised_index in pairs}
    open_saved = [index for index in unmatched_saved if index not in used_saved]
    open_revised = [index for index in unmatched_revised if index not in used_revised]
    for saved_index in list(open_saved):
        hits = [
            index
            for index in open_revised
            if _stops_share_weak_signal(saved_stops[saved_index], revised_stops[index])
        ]
        if len(hits) != 1:
            continue
        revised_index = hits[0]
        others = [
            index
            for index in open_saved
            if index != saved_index and _stops_share_weak_signal(saved_stops[index], revised_stops[revised_index])
        ]
        if others:
            continue
        review.append((saved_index, revised_index))
        open_saved.remove(saved_index)
        open_revised.remove(revised_index)
    return confident, review, open_saved, open_revised


_WEAK_STOP_IDENTITY = "This stop is not identified confidently enough to change a field. Review the PDF before editing it."


def _stop_label(stop: dict) -> str:
    city = str(_read(stop, "city") or "").strip()
    state = str(_read(stop, "state_or_province") or "").strip()
    street = str(_read(stop, "street") or "").strip()
    facility = str(_read(stop, "facility_name") or "").strip()
    place = ", ".join(part for part in (facility, street, city, state) if part)
    kind = str(_read(stop, "stop_type") or "stop").strip()
    return f"{kind} {place}".strip()


def deterministic_reparse_changes(saved: dict | None, revised: dict | None) -> list[dict]:
    """Differences between the two extracted JSON documents, independent of the comparison model."""
    saved_extracted = saved.get("extracted") if isinstance(saved, dict) and isinstance(saved.get("extracted"), dict) else {}
    revised_extracted = revised.get("extracted") if isinstance(revised, dict) and isinstance(revised.get("extracted"), dict) else {}
    changes: list[dict] = []
    labels = {
        "rate": "Linehaul rate",
        "customer_rate": "Customer rate",
        "broker_load_reference": "Broker load number",
        "broker_name_snapshot": "Broker",
        "temperature_requirement": "Temperature",
        "equipment_type": "Equipment",
        "commodity": "Commodity",
    }
    for field in _REPARSE_COMPARABLE_SCALARS:
        current = saved_extracted.get(field) if field in saved_extracted else None
        updated = revised_extracted.get(field)
        if field not in saved_extracted and field not in revised_extracted:
            continue
        if (field not in revised_extracted or _blank(updated)) and _omitted_default(current):
            continue
        if reparse_values_equivalent(field, current, updated):
            continue
        changes.append(
            {
                "field": field,
                "label": labels.get(field, field.replace("_", " ")),
                "current_value": None if field not in saved_extracted else current,
                "revised_value": None if field not in revised_extracted else updated,
                "editable": True,
            }
        )
    saved_stops = _stop_dicts(saved_extracted)
    revised_stops = _stop_dicts(revised_extracted)
    confident, review_pairs, unmatched_saved, unmatched_revised = _classify_stop_matches(saved_stops, revised_stops)
    for saved_index, revised_index in [*confident, *review_pairs]:
        for leaf in _STOP_FIELDS:
            field = f"stops[{saved_index}].{leaf}"
            current = saved_stops[saved_index].get(leaf)
            updated = revised_stops[revised_index].get(leaf)
            if leaf not in saved_stops[saved_index] and leaf not in revised_stops[revised_index]:
                continue
            if reparse_values_equivalent(field, current, updated):
                continue
            changes.append(
                {
                    "field": field,
                    "label": f"Stop {saved_index + 1} {leaf.replace('_', ' ')}",
                    "current_value": current,
                    "revised_value": updated,
                    "editable": (saved_index, revised_index) in confident,
                }
            )
    for index in unmatched_saved:
        changes.append(
            {
                "field": f"stops.review.saved.{index}",
                "label": "Stop",
                "current_value": _stop_label(saved_stops[index]),
                "revised_value": None,
                "editable": False,
            }
        )
    for index in unmatched_revised:
        changes.append(
            {
                "field": f"stops.review.revised.{index}",
                "label": "Stop",
                "current_value": None,
                "revised_value": _stop_label(revised_stops[index]),
                "editable": False,
            }
        )
    saved_refs = [item for item in (saved_extracted.get("references") or []) if isinstance(item, dict)]
    revised_refs = [item for item in (revised_extracted.get("references") or []) if isinstance(item, dict)]
    pairs_refs, open_saved, open_revised = _pair_references(saved_refs, revised_refs)
    for saved_index, revised_index in pairs_refs:
        if reparse_values_equivalent("references.value", saved_refs[saved_index].get("value"), revised_refs[revised_index].get("value")):
            continue
        changes.append(
            {
                "field": f"references[{saved_index}].value",
                "label": "Reference",
                "current_value": saved_refs[saved_index].get("value"),
                "revised_value": revised_refs[revised_index].get("value"),
                "editable": True,
            }
        )
    for index in open_saved:
        changes.append(
            {
                "field": f"references.review.saved.{index}",
                "label": "Reference",
                "current_value": saved_refs[index].get("value"),
                "revised_value": None,
                "editable": False,
            }
        )
    for index in open_revised:
        if _revised_reference_repeats_changed_broker_load(saved_extracted, revised_extracted, revised_refs[index].get("value")):
            continue
        changes.append(
            {
                "field": f"references.review.revised.{index}",
                "label": "Reference",
                "current_value": None,
                "revised_value": revised_refs[index].get("value"),
                "editable": False,
            }
        )
    return changes


def _pair_references(saved_refs: list[dict], revised_refs: list[dict]) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    pairs: list[tuple[int, int]] = []
    used_saved: set[int] = set()
    used_revised: set[int] = set()
    for saved_index, saved in enumerate(saved_refs):
        hits = [
            index
            for index, revised in enumerate(revised_refs)
            if index not in used_revised and _norm_ref(saved.get("kind")) == _norm_ref(revised.get("kind")) and _norm_ref(saved.get("value")) == _norm_ref(revised.get("value"))
        ]
        if len(hits) == 1:
            used_saved.add(saved_index)
            used_revised.add(hits[0])
            pairs.append((saved_index, hits[0]))
    saved_left = [index for index in range(len(saved_refs)) if index not in used_saved]
    revised_left = [index for index in range(len(revised_refs)) if index not in used_revised]
    for kind in {str(saved_refs[index].get("kind") or "") for index in saved_left}:
        saved_kind = [index for index in saved_left if str(saved_refs[index].get("kind") or "") == kind]
        revised_kind = [index for index in revised_left if str(revised_refs[index].get("kind") or "") == kind]
        if len(saved_kind) == 1 and len(revised_kind) == 1:
            pairs.append((saved_kind[0], revised_kind[0]))
            used_saved.add(saved_kind[0])
            used_revised.add(revised_kind[0])
    return (
        pairs,
        [index for index in range(len(saved_refs)) if index not in used_saved],
        [index for index in range(len(revised_refs)) if index not in used_revised],
    )


def align_replacement_to_form(replacement: dict, form: Any) -> dict:
    """Line revised stops up with the form before reconcile, so hidden stop data stays with that stop."""
    out = copy.deepcopy(replacement) if isinstance(replacement, dict) else {}
    extracted = out.get("extracted")
    if not isinstance(extracted, dict):
        return out
    form_stops = list(_read(form, "stops") or [])
    revised_stops = _stop_dicts(extracted)
    pairs, _unmatched_saved, unmatched_revised = _pair_stops(
        [
            {
                "stop_type": _read(stop, "stop_type"),
                "city": _read(stop, "city"),
                "state_or_province": _read(stop, "state_or_province"),
                "street": _read(stop, "street"),
                "facility_name": _read(stop, "facility_name"),
                "reference_number": _read(stop, "reference_number"),
            }
            for stop in form_stops
        ],
        revised_stops,
    )
    by_form = {saved_index: revised_stops[revised_index] for saved_index, revised_index in pairs}
    extracted["stops"] = [copy.deepcopy(by_form.get(index, {})) for index in range(len(form_stops))]
    if unmatched_revised:
        extracted["unmatched_revised_stops"] = [copy.deepcopy(revised_stops[index]) for index in unmatched_revised]
    else:
        extracted.pop("unmatched_revised_stops", None)
    return out


def preserve_matched_reference_extras(verified: dict, revised: dict) -> None:
    """Keep unmapped reference keys when a revised reference safely matches one on the form."""
    verified_extracted = verified.get("extracted") if isinstance(verified.get("extracted"), dict) else None
    revised_extracted = revised.get("extracted") if isinstance(revised.get("extracted"), dict) else None
    if verified_extracted is None or revised_extracted is None:
        return
    current = [item for item in (verified_extracted.get("references") or []) if isinstance(item, dict)]
    previous = [item for item in (revised_extracted.get("references") or []) if isinstance(item, dict)]
    pairs, _open_saved, _open_revised = _pair_references(current, previous)
    for current_index, previous_index in pairs:
        for key, value in previous[previous_index].items():
            if key in {"kind", "value"} or key in current[current_index]:
                continue
            current[current_index][key] = value
    if current:
        verified_extracted["references"] = current


def assess_same_load(saved: dict | None, revised: dict | None, broker_aliases: list[str] | None = None) -> dict:
    """Explain whether the revised extraction is the same shipment. No numeric score."""
    saved_extracted = saved.get("extracted") if isinstance(saved, dict) and isinstance(saved.get("extracted"), dict) else {}
    revised_extracted = revised.get("extracted") if isinstance(revised, dict) and isinstance(revised.get("extracted"), dict) else {}
    saved_broker = saved_extracted.get("broker_name_snapshot")
    revised_broker = revised_extracted.get("broker_name_snapshot")
    broker_match = _names_match(saved_broker, revised_broker, broker_aliases)
    broker_conflict = bool(_party_name(saved_broker) and _party_name(revised_broker) and not broker_match)
    saved_ref = saved_extracted.get("broker_load_reference")
    revised_ref = revised_extracted.get("broker_load_reference")
    reference_match = not _blank(saved_ref) and reparse_values_equivalent("broker_load_reference", saved_ref, revised_ref)
    reference_conflict = not _blank(saved_ref) and not _blank(revised_ref) and not reference_match
    pickup_match, pickup_conflict = _place_relation(saved_extracted, revised_extracted, "pickup")
    delivery_match, delivery_conflict = _place_relation(saved_extracted, revised_extracted, "delivery")
    date_conflict = _date_conflict(saved_extracted, revised_extracted)
    time_conflict = _time_conflict(saved_extracted, revised_extracted)
    address_conflict = _address_conflict(saved_extracted, revised_extracted)
    match_count = sum((broker_match, reference_match, pickup_match, delivery_match))
    wrong_broker = "Wrong document — the broker does not match this Load."
    if broker_conflict:
        return _identity_result("blocked", wrong_broker, [wrong_broker], False)
    if broker_match and pickup_conflict and delivery_conflict:
        if reference_match:
            # Broker and *same shipment reference* identify a plausible amendment,
            # but both locations changed; never silently accept it.
            caution = "Needs confirmation — broker and load number match, but both pickup and delivery locations changed."
            return _identity_result("needs_confirmation", caution, [caution], True)
        blocked = "Wrong document — broker and shipment details do not match this Load."
        return _identity_result("blocked", blocked, [blocked], False)
    if not broker_match and not (pickup_match and delivery_match) and match_count < 2:
        insufficient = "Cannot confirm this PDF belongs to this Load. No Load information has changed."
        return _identity_result("blocked", insufficient, [insufficient], False)
    reasons: list[str] = []
    summary = ""
    if reference_conflict and broker_match and pickup_match and delivery_match:
        summary = "Needs confirmation — PO changed, but broker, addresses and pickup dates match."
        reasons.append(summary)
    elif reference_conflict and broker_match:
        summary = "Needs confirmation — the broker load number changed and other shipment evidence is limited."
        reasons.append(summary)
    if (date_conflict or time_conflict) and broker_match and not pickup_conflict and not delivery_conflict:
        text = "Needs confirmation — the pickup appointment changed, but the broker and stops match."
        summary = summary or text
        reasons.append(text)
    if address_conflict and broker_match:
        text = "Needs confirmation — a stop address changed, but the broker and cities match."
        summary = summary or text
        reasons.append(text)
    if (pickup_conflict or delivery_conflict) and not (pickup_conflict and delivery_conflict) and broker_match:
        text = "Needs confirmation — a stop address changed, but other shipment details match."
        summary = summary or text
        reasons.append(text)
    if not broker_match and pickup_match and delivery_match:
        text = "Needs confirmation — the broker name is missing, but the shipment details match."
        summary = summary or text
        reasons.append(text)
    order = _revision_order(saved or {}, revised or {})
    if order == "older":
        text = "Cannot confirm revision order — this may be an older rate confirmation."
        summary = summary or text
        reasons.append(text)
    rate_note = _rate_change_note(saved_extracted, revised_extracted)
    accounting = ""
    if rate_note or reference_conflict:
        accounting = "If this rate or broker load number was already invoiced or paid, accounting may need a separate review."
        reasons.append(accounting)
    if summary:
        return _identity_result("needs_confirmation", summary, [item for item in reasons if item != summary], True)
    if not broker_match:
        insufficient = "Cannot confirm this PDF belongs to this Load. No Load information has changed."
        return _identity_result("blocked", insufficient, [insufficient], False)
    broker_text = str(saved_broker or revised_broker or "The broker").strip()
    ref_text = str(revised_ref or saved_ref or "").strip()
    ref_bit = f", Load #{ref_text}" if ref_text else ""
    strong = f"Strong match — {broker_text}{ref_bit}, pickup and delivery match."
    if rate_note:
        strong = f"{strong} {rate_note}"
    extra = [accounting] if accounting else []
    return _identity_result("strong", strong, extra, False)


def _identity_result(verdict: str, summary: str, reasons: list[str], acknowledgement: bool) -> dict:
    return {
        "verdict": verdict,
        "summary": summary,
        "reasons": reasons,
        "acknowledgement_required": acknowledgement,
    }


def _place_relation(saved: dict, revised: dict, stop_type: str) -> tuple[bool, bool]:
    left = _first_stop(saved, stop_type)
    right = _first_stop(revised, stop_type)
    if left is None or right is None:
        return False, False
    same = _norm_place(_read(left, "city")) == _norm_place(_read(right, "city")) and _norm_place(
        _read(left, "state_or_province")
    ) == _norm_place(_read(right, "state_or_province"))
    both_present = bool(_norm_place(_read(left, "city")) and _norm_place(_read(right, "city")))
    return (same and both_present, both_present and not same)


def _date_conflict(saved: dict, revised: dict) -> bool:
    left = _first_stop(saved, "pickup")
    right = _first_stop(revised, "pickup")
    if left is None or right is None:
        return False
    saved_date = _norm_date(left.get("appointment_date"))
    revised_date = _norm_date(right.get("appointment_date"))
    if not saved_date or not revised_date:
        return False
    return saved_date != revised_date


def _address_conflict(saved: dict, revised: dict) -> bool:
    for left in _stop_dicts(saved):
        for right in _stop_dicts(revised):
            if not _stops_share_city(left, right):
                continue
            for key in ("street", "facility_name"):
                saved_value, revised_value = _stop_token(left, key), _stop_token(right, key)
                if saved_value and revised_value and saved_value != revised_value:
                    return True
    return False


def _time_conflict(saved: dict, revised: dict) -> bool:
    for left in _stop_dicts(saved):
        for right in _stop_dicts(revised):
            if _stop_type(left) != "pickup" or not _stops_share_city(left, right):
                continue
            if _stops_conflict(left, right):
                continue
            saved_time, revised_time = _norm_time(left.get("appointment_time_text")), _norm_time(right.get("appointment_time_text"))
            if saved_time and revised_time and saved_time != revised_time:
                return True
    return False


def _revision_order(saved: dict, revised: dict) -> str:
    """Equal or missing dates do not prove which PDF was issued later."""
    saved_date = _document_dates(saved)
    revised_date = _document_dates(revised)
    if not saved_date or not revised_date or saved_date == revised_date:
        return "unknown"
    if revised_date < saved_date:
        return "older"
    return "newer"


def comparison_baseline(saved: dict | None) -> dict:
    """Field paths and values from the last saved verified JSON for the comparison model.

    Empty saved values are sent as null. Customer rate is stored on the load but omitted here.
    """
    document = saved if isinstance(saved, dict) else {}
    extracted = document.get("extracted") if isinstance(document.get("extracted"), dict) else {}
    fields: list[dict] = []
    for name in _REPARSE_COMPARABLE_SCALARS:
        if name in extracted:
            fields.append({"path": name, "value": extracted.get(name)})
        else:
            fields.append({"path": name, "value": None})
    for index, stop in enumerate(_stop_dicts(extracted)):
        for leaf in _STOP_FIELDS:
            fields.append({"path": f"stops[{index}].{leaf}", "value": stop.get(leaf) if leaf in stop else None})
    references = [item for item in (extracted.get("references") or []) if isinstance(item, dict)]
    for index, reference in enumerate(references):
        for leaf in ("kind", "value"):
            fields.append(
                {
                    "path": f"references[{index}].{leaf}",
                    "value": reference.get(leaf) if leaf in reference else None,
                }
            )
    return {"fields": fields}


def _comparable_reparse_field(field: str) -> bool:
    if field in _SCALAR_FIELDS:
        return True
    indexed = _INDEXED_FIELD.match(field)
    if not indexed or indexed.group(3) is None:
        return False
    name, child = indexed.group(1), indexed.group(3)
    if name == "stops" and child in _STOP_FIELDS:
        return True
    return name == "references" and child in {"kind", "value"}


def _comparison_label(item: dict, fallback: str) -> str | None:
    label = str(item.get("label") or "").strip()
    if not label or label == fallback or len(label) > 160 or "\n" in label:
        return None
    return label


def _valid_money_change(current: Any, updated: Any) -> bool:
    """Both document amounts must be finite numbers before Change is offered."""
    old_amount, new_amount = _decimal_or_none(current), _decimal_or_none(updated)
    return (
        old_amount is not None
        and new_amount is not None
        and old_amount.is_finite()
        and new_amount.is_finite()
        and old_amount != new_amount
    )


def _money_review(field: str, current: Any, updated: Any) -> dict:
    """A verified numeric discrepancy remains actionable even if AI omitted or misstated it."""
    label = "Linehaul rate" if field == "rate" else "Customer rate"
    actionable = _valid_money_change(current, updated)
    return {
        "field": field,
        "label": label,
        "explanation": (
            "Both JSON documents contain different valid amounts. Verify the revised PDF before applying."
            if actionable
            else "The amounts could not be validated. Review the PDF; no automatic change is available."
        ),
        "current_value": current,
        "revised_value": updated,
        "editable": actionable,
    }


_INCOMPLETE_EXTRACTION = "The revised extraction did not include this value. It was not treated as a deletion."


def _reparse_field_label(field: str) -> str:
    labels = {
        "rate": "Linehaul rate",
        "broker_load_reference": "Broker load number",
        "broker_name_snapshot": "Broker",
        "broker_contact_name_snapshot": "Contact name",
        "broker_contact_phone_snapshot": "Contact phone",
        "broker_contact_email_snapshot": "Contact email",
        "temperature_requirement": "Temperature",
        "equipment_type": "Equipment",
        "commodity": "Commodity",
    }
    if field in labels:
        return labels[field]
    indexed = _INDEXED_FIELD.match(field)
    if indexed and indexed.group(1) == "stops" and indexed.group(3):
        return f"Stop {int(indexed.group(2)) + 1} {indexed.group(3).replace('_', ' ')}"
    if indexed and indexed.group(1) == "references":
        return "Reference"
    return field.replace("_", " ")


def _reparse_revised_display_value(field: str, updated: Any) -> Any:
    if field != "miles" or _blank(updated):
        return updated
    try:
        normalized = normalize_load_miles_value(updated)
        return normalized if normalized is not None else updated
    except ValueError:
        return updated


def _supported_difference_row(field: str, current: Any, updated: Any, *, revised_present: bool) -> dict | None:
    """One verified difference. A blank revised value is review-only, never a cleared field."""
    if field == "customer_rate":
        return None
    if _blank(current):
        # An empty load field is still a suggestion when the revised PDF states a value.
        if not revised_present or _blank(updated) or _omitted_default(updated):
            return None
        return {
            "field": field,
            "label": _reparse_field_label(field),
            "current_value": None,
            "revised_value": _reparse_revised_display_value(field, updated),
            "editable": field_is_editable(field),
            "explanation": "The load does not have this value. The revised PDF does.",
        }
    if not revised_present or _blank(updated):
        if _omitted_default(current):
            return None
        return {
            "field": field,
            "label": _reparse_field_label(field),
            "current_value": current,
            "revised_value": None,
            "editable": False,
            "explanation": _INCOMPLETE_EXTRACTION,
        }
    if reparse_values_equivalent(field, current, updated):
        return None
    if field == "rate":
        return _money_review(field, current, updated)
    return {
        "field": field,
        "label": _reparse_field_label(field),
        "current_value": current,
        "revised_value": _reparse_revised_display_value(field, updated),
        "editable": field_is_editable(field),
    }


def _supported_reparse_differences(saved: dict | None, revised: dict | None) -> list[dict]:
    """Every supported difference between the two verified JSON documents."""
    saved_extracted = saved.get("extracted") if isinstance(saved, dict) and isinstance(saved.get("extracted"), dict) else {}
    revised_extracted = revised.get("extracted") if isinstance(revised, dict) and isinstance(revised.get("extracted"), dict) else {}
    rows: list[dict] = []
    for field in _REPARSE_COMPARABLE_SCALARS:
        row = _supported_difference_row(
            field,
            saved_extracted.get(field) if field in saved_extracted else None,
            revised_extracted.get(field),
            revised_present=field in revised_extracted,
        )
        if row is not None:
            rows.append(row)
    saved_stops = _stop_dicts(saved_extracted)
    revised_stops = _stop_dicts(revised_extracted)
    confident, review_pairs, unmatched_saved, unmatched_revised = _classify_stop_matches(saved_stops, revised_stops)
    confident_pairs = set(confident)
    for saved_index, revised_index in [*confident, *review_pairs]:
        saved_stop = saved_stops[saved_index]
        revised_stop = revised_stops[revised_index]
        for leaf in _STOP_FIELDS:
            row = _supported_difference_row(
                f"stops[{saved_index}].{leaf}",
                saved_stop.get(leaf) if leaf in saved_stop else None,
                revised_stop.get(leaf),
                revised_present=leaf in revised_stop,
            )
            if row is None:
                continue
            if (saved_index, revised_index) not in confident_pairs:
                row["editable"] = False
                row.setdefault("explanation", _WEAK_STOP_IDENTITY)
            rows.append(row)
    for index in unmatched_saved:
        rows.append(
            {
                "field": f"stops.review.saved.{index}",
                "label": "Stop",
                "current_value": _stop_label(saved_stops[index]),
                "revised_value": None,
                "editable": False,
                "explanation": "This stop could not be matched safely. No stop was changed.",
            }
        )
    for index in unmatched_revised:
        rows.append(
            {
                "field": f"stops.review.revised.{index}",
                "label": "Stop",
                "current_value": None,
                "revised_value": _stop_label(revised_stops[index]),
                "editable": False,
                "explanation": "This stop could not be matched safely. No stop was changed.",
            }
        )
    saved_refs = [item for item in (saved_extracted.get("references") or []) if isinstance(item, dict)]
    revised_refs = [item for item in (revised_extracted.get("references") or []) if isinstance(item, dict)]
    ref_pairs, open_saved, open_revised = _pair_references(saved_refs, revised_refs)
    for saved_index, revised_index in ref_pairs:
        row = _supported_difference_row(
            f"references[{saved_index}].value",
            saved_refs[saved_index].get("value"),
            revised_refs[revised_index].get("value"),
            revised_present="value" in revised_refs[revised_index],
        )
        if row is not None:
            rows.append(row)
    for index in open_saved:
        rows.append(
            {
                "field": f"references.review.saved.{index}",
                "label": "Reference",
                "current_value": saved_refs[index].get("value"),
                "revised_value": None,
                "editable": False,
                "explanation": "This reference could not be matched safely. No reference was changed.",
            }
        )
    for index in open_revised:
        if _revised_reference_repeats_changed_broker_load(saved_extracted, revised_extracted, revised_refs[index].get("value")):
            continue
        rows.append(
            {
                "field": f"references.review.revised.{index}",
                "label": "Reference",
                "current_value": None,
                "revised_value": revised_refs[index].get("value"),
                "editable": False,
                "explanation": "This reference could not be matched safely. No reference was changed.",
            }
        )
    return rows


def _apply_reparse_change_to_extracted(extracted: dict, field: str, value: Any) -> None:
    indexed = _INDEXED_FIELD.match(field)
    ready = _json_ready(value)
    if indexed:
        name, index_text, child = indexed.group(1), indexed.group(2), indexed.group(3)
        index = int(index_text)
        if name == "stops" and child:
            stops = extracted.setdefault("stops", [])
            while len(stops) <= index:
                stops.append({})
            if not isinstance(stops[index], dict):
                stops[index] = {}
            stops[index][child] = ready
            return
        if name == "references" and child:
            refs = extracted.setdefault("references", [])
            while len(refs) <= index:
                refs.append({})
            if not isinstance(refs[index], dict):
                refs[index] = {}
            refs[index][child] = ready
            return
    extracted[field] = ready


def build_reparse_proposal_document(
    saved: dict,
    *,
    filename: str,
    pdf_text: str,
    changes: list[dict],
) -> dict:
    """Minimal parse document for integrity tokens and identity checks after text-diff re-parse."""
    out = copy.deepcopy(saved)
    extracted = out.get("extracted")
    if not isinstance(extracted, dict):
        extracted = {}
        out["extracted"] = extracted
    for row in changes:
        field = str(row.get("field") or "").strip()
        if field:
            _apply_reparse_change_to_extracted(extracted, field, row.get("revised_value"))
    out["raw_text"] = pdf_text[:100_000]
    ctx = dict(out.get("context") or {})
    ctx["document_type"] = "rate_confirmation"
    ctx["reparse_path"] = "text_diff_v1"
    out["context"] = ctx
    document = out.get("document") if isinstance(out.get("document"), dict) else {}
    out["document"] = {**document, "filename": filename}
    return out


def _revised_value_in_pdf_text(field: str, value: Any, pdf_text: str) -> bool:
    if _blank(value):
        return False
    hay = (pdf_text or "").casefold()
    compact_hay = re.sub(r"\s+", "", hay)
    text = str(value).strip()
    if text and text.casefold() in hay:
        return True
    dec = _decimal_or_none(value)
    if dec is not None:
        candidates = {
            format(dec, "f"),
            format(dec, "f").rstrip("0").rstrip("."),
            f"${format(dec, 'f')}",
            f"${dec}",
        }
        for candidate in candidates:
            c = candidate.replace(",", "").casefold()
            if c and c in compact_hay:
                return True
    if field.endswith(".value") or field == "broker_load_reference":
        ref = _norm_ref(text)
        if ref and ref in compact_hay:
            return True
    if isinstance(value, int):
        if str(value) in compact_hay:
            return True
    return False


def _reparse_stop_field_editable(saved_extracted: dict, field: str, revised_value: Any) -> bool:
    if not field_is_editable(field):
        return False
    indexed = _INDEXED_FIELD.match(field)
    if not indexed or indexed.group(1) != "stops" or indexed.group(3) is None:
        return True
    saved_stops = _stop_dicts(saved_extracted)
    saved_index = int(indexed.group(2))
    child = indexed.group(3)
    if saved_index >= len(saved_stops):
        return False
    revised_stops = copy.deepcopy(saved_stops)
    revised_stops[saved_index] = {**revised_stops[saved_index], child: revised_value}
    confident, _review, _open_saved, _open_revised = _classify_stop_matches(saved_stops, revised_stops)
    return any(saved_index == pair[0] for pair in confident)


def validate_ai_reparse_changes(saved: dict | None, pdf_text: str, proposed: list) -> list[dict]:
    """Keep only AI-proposed rows that match saved JSON and revised text in the PDF.

    The server does not invent popup rows. Customer rate is never proposed.
    """
    saved_extracted = saved.get("extracted") if isinstance(saved, dict) and isinstance(saved.get("extracted"), dict) else {}
    rows: list[dict] = []
    for item in proposed or []:
        if not isinstance(item, dict):
            continue
        field = _normalize_field_path(str(item.get("field") or ""))
        if not field or field == "customer_rate" or not _comparable_reparse_field(field):
            continue
        saved_current = _resolve_extracted(saved_extracted, field)
        if saved_current is _MISSING:
            saved_current = None
        ai_current = item.get("current_value")
        ai_revised = item.get("revised_value")
        if not reparse_values_equivalent(field, ai_current, saved_current):
            continue
        if _blank(ai_revised):
            continue
        if reparse_values_equivalent(field, saved_current, ai_revised):
            continue
        if not _revised_value_in_pdf_text(field, ai_revised, pdf_text):
            continue
        editable = _reparse_stop_field_editable(saved_extracted, field, ai_revised)
        label = _reparse_field_label(field)
        note = _comparison_label(item, label)
        row = {
            "field": field,
            "label": label,
            "current_value": saved_current,
            "revised_value": ai_revised,
            "editable": editable,
        }
        if note:
            row["explanation"] = note
        rows.append(row)
    return rows


def attach_model_explanations(changes: list[dict], proposed: list) -> list[dict]:
    """Keep the comparison model's wording. Deterministic values stay authoritative."""
    notes: dict[str, str] = {}
    for item in proposed or []:
        if not isinstance(item, dict):
            continue
        field = _normalize_field_path(str(item.get("field") or ""))
        label = str(item.get("label") or "").strip()
        if field and label and len(label) <= 160 and "\n" not in label:
            notes[field] = label
    for change in changes:
        note = notes.get(str(change.get("field") or ""))
        if note:
            change["explanation"] = note
    return changes


def _rate_change_note(saved: dict, revised: dict) -> str:
    if "rate" not in saved and "rate" not in revised:
        return ""
    if reparse_values_equivalent("rate", saved.get("rate"), revised.get("rate")):
        return ""
    return f"Linehaul rate changed from {_money_text(saved.get('rate'))} to {_money_text(revised.get('rate'))}."


def ground_reparse_changes(saved: dict | None, revised: dict | None, proposed: list) -> list[dict]:
    """Keep a proposal only when the path exists on the revised extraction.

    Displayed values come from the saved JSON and the revised extraction.
    A path the form cannot edit stays visible and is not marked editable.
    """
    saved_extracted = saved.get("extracted") if isinstance(saved, dict) else None
    revised_extracted = revised.get("extracted") if isinstance(revised, dict) else None
    grounded: list[dict] = []
    seen: set[str] = set()
    for item in proposed or []:
        if not isinstance(item, dict):
            continue
        field = _normalize_field_path(str(item.get("field") or ""))
        if not field or field in seen:
            continue
        revised_value = _resolve_extracted(revised_extracted, field)
        if revised_value is _MISSING:
            continue
        current_value = _resolve_extracted(saved_extracted, field)
        if current_value is _MISSING:
            current_value = None
        if values_equivalent(current_value, revised_value):
            continue
        seen.add(field)
        label = str(item.get("label") or "").strip()
        if not label or len(label) > 80 or "\n" in label:
            label = field
        grounded.append(
            {
                "field": field,
                "label": label,
                "current_value": current_value,
                "revised_value": revised_value,
                "editable": field_is_editable(field),
            }
        )
    return grounded


async def parse_and_attach_workspace_draft_pdf(
    db: AsyncSession,
    tenant_id: int,
    tenant_slug: str,
    draft_id: uuid.UUID,
    file: UploadFile,
    *,
    updated_by_platform_user_id: str | None,
    expected_concurrency_version: int | None = None,
    continue_anyway: bool = False,
) -> tuple[LoadWorkspaceDraft, LoadDocumentParseResponse]:
    current = await db.scalar(
        select(LoadWorkspaceDraft).where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
        )
    )
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")
    await require_workspace_draft_open_for_mutation(db, current)
    server_version = int(current.concurrency_version)
    if expected_concurrency_version is not None and expected_concurrency_version != server_version:
        raise workspace_draft_version_conflict_exception(
            draft_id=draft_id,
            client_version=expected_concurrency_version,
            server_version=server_version,
        )

    pdf_bytes, filename = await _read_bounded_pdf(file)
    try:
        validate_load_parser_pdf(pdf_bytes)
    except UnsafeLoadPdfError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    draft_json = current.draft_json if isinstance(current.draft_json, dict) else {}
    broker_raw = draft_json.get("brokerId") or draft_json.get("broker_id")
    incoming_broker_id: int | None = None
    if broker_raw is not None and str(broker_raw).strip():
        try:
            parsed_broker = int(broker_raw)
            if parsed_broker > 0:
                incoming_broker_id = parsed_broker
        except (TypeError, ValueError):
            incoming_broker_id = None

    parse = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename=filename,
        tenant_id=tenant_id,
        db=db,
        continue_anyway=continue_anyway,
        incoming_broker_id=incoming_broker_id,
    )
    if parse.context.get("semantic_outcome") == "blocked_duplicate_review":
        # Review gate must not store/replace the draft PDF, accepted parse,
        # or increment concurrency. Continue anyway reuses the same draft.
        return current, parse
    ctx = dict(parse.context or {})
    ctx["workspace_draft_id"] = str(draft_id)
    parse = parse.model_copy(update={"context": ctx})

    stored = await get_storage().save_bytes(
        tenant_slug,
        LOAD_WORKSPACE_DRAFT_PDF_MODULE,
        "workspace_draft",
        str(draft_id),
        pdf_bytes,
        filename_hint=filename,
        content_type="application/pdf",
    )

    previous_key = current.pdf_storage_key
    now = datetime.now(timezone.utc)
    accepted = accepted_parse_from_response(parse)

    stmt = (
        update(LoadWorkspaceDraft)
        .where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
            LoadWorkspaceDraft.status == EDITABLE_STATUS,
            LoadWorkspaceDraft.concurrency_version == server_version,
        )
        .values(
            pdf_storage_key=stored.storage_key,
            pdf_sha256=stored.sha256,
            pdf_filename=stored.original_filename,
            pdf_size_bytes=stored.file_size_bytes,
            pdf_upload_state="ready",
            pdf_retention_class="workspace_ttl",
            accepted_parse_json=accepted,
            accepted_parse_schema_version=WORKSPACE_DRAFT_ACCEPTED_PARSE_SCHEMA_VERSION,
            accepted_parse_pdf_sha256=stored.sha256,
            concurrency_version=LoadWorkspaceDraft.concurrency_version + 1,
            updated_by_platform_user_id=updated_by_platform_user_id,
            updated_at=func.now(),
        )
        .returning(LoadWorkspaceDraft)
    )
    result = await db.execute(stmt)
    updated = result.scalar_one_or_none()
    if updated is None:
        await db.rollback()
        get_storage().delete(
            stored.storage_key,
            module=LOAD_WORKSPACE_DRAFT_PDF_MODULE,
            tenant_slug=tenant_slug,
        )
        raise workspace_draft_version_conflict_exception(
            draft_id=draft_id,
            client_version=expected_concurrency_version or server_version,
            server_version=server_version,
        )

    try:
        await db.commit()
        await db.refresh(updated)
    except Exception:
        await db.rollback()
        get_storage().delete(
            stored.storage_key,
            module=LOAD_WORKSPACE_DRAFT_PDF_MODULE,
            tenant_slug=tenant_slug,
        )
        raise

    if previous_key and previous_key != stored.storage_key:
        get_storage().delete(
            previous_key,
            module=LOAD_WORKSPACE_DRAFT_PDF_MODULE,
            tenant_slug=tenant_slug,
        )

    return updated, parse


async def get_workspace_draft_pdf_row(
    db: AsyncSession, tenant_id: int, draft_id: uuid.UUID
) -> LoadWorkspaceDraft:
    row = await db.scalar(
        select(LoadWorkspaceDraft).where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")
    if row.pdf_upload_state != "ready" or not row.pdf_storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No rate confirmation PDF on this draft")
    return row
