"""Map persisted workspace draft_json into LoadCreate (commercial fields only)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Callable

from pydantic import ValidationError

from app.schemas.load import LoadCreate, LoadStopCreate
from app.schemas.load_document_parse import LoadParseReferenceItem
from app.utils.load_commercial_money import parse_load_customer_rate, parse_load_rate


class DraftJsonMappingError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(message)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_empty(value: Any) -> bool:
    return value is None or _text(value) == ""


def _parse_optional_id(value: Any, field: str) -> int | None:
    if _is_empty(value):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DraftJsonMappingError(field, "must be a positive integer") from exc
    if parsed <= 0:
        raise DraftJsonMappingError(field, "must be a positive integer")
    return parsed


def _parse_optional_nonneg_int(value: Any, field: str) -> int | None:
    if _is_empty(value):
        return None
    text = _text(value)
    try:
        parsed = int(text)
    except (TypeError, ValueError) as exc:
        raise DraftJsonMappingError(field, "must be a non-negative integer") from exc
    if parsed < 0:
        raise DraftJsonMappingError(field, "must be a non-negative integer")
    return parsed


def _parse_optional_commercial_money(
    value: Any,
    field: str,
    *,
    parser: Callable[[Any], Decimal | None],
) -> Decimal | None:
    if _is_empty(value):
        return None
    raw = value if isinstance(value, (int, float, Decimal)) else _text(value)
    try:
        return parser(raw)
    except ValueError as exc:
        raise DraftJsonMappingError(field, "must be a non-negative monetary amount") from exc


def _hazmat_flag(draft_json: dict[str, Any]) -> bool | None:
    if "hazmat" not in draft_json:
        return None
    raw = draft_json.get("hazmat")
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    text = _text(raw).lower()
    if text == "unset" or text == "":
        return None
    if text == "yes":
        return True
    if text == "no":
        return False
    raise DraftJsonMappingError("hazmat", "must be unset, yes, or no")


def _references(draft_json: dict[str, Any]) -> list[LoadParseReferenceItem]:
    if "loadReferences" not in draft_json and "references" not in draft_json:
        return []
    raw = draft_json.get("loadReferences") if "loadReferences" in draft_json else draft_json.get("references")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise DraftJsonMappingError("loadReferences", "must be a JSON array")
    items: list[LoadParseReferenceItem] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise DraftJsonMappingError(f"loadReferences[{index}]", "must be a JSON object")
        try:
            items.append(LoadParseReferenceItem.model_validate(entry))
        except ValidationError as exc:
            raise DraftJsonMappingError(f"loadReferences[{index}]", str(exc.errors()[0]["msg"])) from exc
    return items


def _parse_appointment_date(raw: Any, field: str) -> date | None:
    if _is_empty(raw):
        return None
    text = _text(raw)
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise DraftJsonMappingError(field, "must be an ISO date (YYYY-MM-DD)") from exc


def _parse_stop_id(raw: Any, field: str) -> int | None:
    if raw is None or raw == 0 or raw == "0":
        return None
    return _parse_optional_id(raw, field)


def _stops(draft_json: dict[str, Any]) -> list[LoadStopCreate]:
    if "draftStops" not in draft_json and "stops" not in draft_json:
        return []
    raw = draft_json.get("draftStops") if "draftStops" in draft_json else draft_json.get("stops")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise DraftJsonMappingError("draftStops", "must be a JSON array")
    stops: list[LoadStopCreate] = []
    for index, entry in enumerate(raw):
        prefix = f"draftStops[{index}]"
        if not isinstance(entry, dict):
            raise DraftJsonMappingError(prefix, "must be a JSON object")
        stop_type = _text(entry.get("stop_type") or entry.get("stopType"))
        if not stop_type:
            raise DraftJsonMappingError(f"{prefix}.stop_type", "is required")
        seq_raw = entry.get("sequence")
        if seq_raw is None:
            sequence = index
        else:
            sequence = _parse_optional_nonneg_int(seq_raw, f"{prefix}.sequence")
            if sequence is None:
                sequence = index
        appt_date = _parse_appointment_date(
            entry.get("appointment_date") or entry.get("appointmentDate"),
            f"{prefix}.appointment_date",
        )
        parsed_id = _parse_stop_id(entry.get("id"), f"{prefix}.id")
        stops.append(
            LoadStopCreate(
                id=parsed_id,
                stop_type=stop_type,
                sequence=sequence,
                facility_name=_text(entry.get("facility_name") or entry.get("facilityName")) or None,
                street=_text(entry.get("street")) or None,
                city=_text(entry.get("city")) or None,
                state_or_province=_text(entry.get("state_or_province") or entry.get("stateOrProvince"))
                or None,
                postal_code=_text(entry.get("postal_code") or entry.get("postalCode")) or None,
                country=_text(entry.get("country")) or None,
                reference_number=_text(entry.get("reference_number") or entry.get("referenceNumber")) or None,
                appointment_type=_text(entry.get("appointment_type") or entry.get("appointmentType")) or None,
                appointment_date=appt_date,
                appointment_time_text=_text(
                    entry.get("appointment_time_text") or entry.get("appointmentTimeText")
                )
                or None,
                notes=_text(entry.get("notes")) or None,
                commodity_notes=_text(entry.get("commodity_notes") or entry.get("commodityNotes")) or None,
            )
        )
    return stops


def draft_json_to_load_create(draft_json: dict[str, Any]) -> LoadCreate:
    """Build LoadCreate from workspace draft_json; ignores assignment / trip fields."""
    if not isinstance(draft_json, dict):
        raise DraftJsonMappingError("draft_json", "must be a JSON object")
    load_create = LoadCreate(
        status="draft",
        load_number=None,
        broker_id=_parse_optional_id(draft_json.get("brokerId") or draft_json.get("broker_id"), "brokerId"),
        broker_contact_id=_parse_optional_id(
            draft_json.get("brokerContactId") or draft_json.get("broker_contact_id"),
            "brokerContactId",
        ),
        broker_name_snapshot=_text(
            draft_json.get("brokerNameSnapshot") or draft_json.get("broker_name_snapshot")
        )
        or None,
        broker_contact_name_snapshot=_text(
            draft_json.get("brokerContactNameSnapshot") or draft_json.get("broker_contact_name_snapshot")
        )
        or None,
        broker_contact_phone_snapshot=_text(
            draft_json.get("brokerContactPhoneSnapshot") or draft_json.get("broker_contact_phone_snapshot")
        )
        or None,
        broker_contact_extension_snapshot=_text(
            draft_json.get("brokerContactExtensionSnapshot")
            or draft_json.get("broker_contact_extension_snapshot")
        )
        or None,
        broker_contact_email_snapshot=_text(
            draft_json.get("brokerContactEmailSnapshot") or draft_json.get("broker_contact_email_snapshot")
        )
        or None,
        broker_load_reference=_text(
            draft_json.get("brokerLoadReference") or draft_json.get("broker_load_reference")
        )
        or None,
        mode=_text(draft_json.get("freightMode") or draft_json.get("mode")) or None,
        equipment_type=_text(draft_json.get("equipmentType") or draft_json.get("equipment_type")) or None,
        trailer_type=_text(draft_json.get("trailerType") or draft_json.get("trailer_type")) or None,
        trailer_size=_text(draft_json.get("trailerSize") or draft_json.get("trailer_size")) or None,
        commodity=_text(draft_json.get("commodity")) or None,
        estimated_weight=_parse_optional_nonneg_int(
            draft_json.get("estimatedWeight") or draft_json.get("estimated_weight"),
            "estimatedWeight",
        ),
        hazmat_flag=_hazmat_flag(draft_json),
        temperature_requirement=_text(
            draft_json.get("temperatureRequirement") or draft_json.get("temperature_requirement")
        )
        or None,
        pallet_case_count=_text(draft_json.get("palletCaseCount") or draft_json.get("pallet_case_count")) or None,
        rate=_parse_optional_commercial_money(draft_json.get("rate"), "rate", parser=parse_load_rate),
        customer_rate=_parse_optional_commercial_money(
            draft_json.get("customerRate") or draft_json.get("customer_rate"),
            "customerRate",
            parser=parse_load_customer_rate,
        ),
        miles=_parse_optional_nonneg_int(draft_json.get("miles"), "miles"),
        customs_broker_id=_parse_optional_id(
            draft_json.get("customsBrokerId") or draft_json.get("customs_broker_id"),
            "customsBrokerId",
        ),
        internal_notes=_text(draft_json.get("internalNotes") or draft_json.get("internal_notes")) or None,
        references=_references(draft_json),
        stops=_stops(draft_json) or None,
    )
    if load_create.customer_rate is None and load_create.rate is not None:
        load_create = load_create.model_copy(update={"customer_rate": load_create.rate})
    return load_create
