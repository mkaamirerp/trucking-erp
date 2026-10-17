"""Map persisted workspace draft_json into LoadCreate (commercial fields only)."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.schemas.load import LoadCreate, LoadStopCreate
from app.schemas.load_document_parse import LoadParseReferenceItem


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _optional_int(value: Any) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = int(text)
    except (TypeError, ValueError):
        return None
    return max(0, parsed)


def _optional_float(value: Any) -> float | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    return max(0.0, parsed)


def _hazmat_flag(draft_json: dict[str, Any]) -> bool | None:
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
    return None


def _references(draft_json: dict[str, Any]) -> list[LoadParseReferenceItem]:
    raw = draft_json.get("loadReferences") or draft_json.get("references") or []
    if not isinstance(raw, list):
        return []
    items: list[LoadParseReferenceItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            items.append(LoadParseReferenceItem.model_validate(entry))
        except Exception:
            continue
    return items


def _stops(draft_json: dict[str, Any]) -> list[LoadStopCreate]:
    raw = draft_json.get("draftStops") or draft_json.get("stops") or []
    if not isinstance(raw, list):
        return []
    stops: list[LoadStopCreate] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        stop_type = _text(entry.get("stop_type") or entry.get("stopType"))
        if not stop_type:
            continue
        appt_date_raw = entry.get("appointment_date") or entry.get("appointmentDate")
        appt_date: date | None = None
        if appt_date_raw:
            try:
                appt_date = date.fromisoformat(_text(appt_date_raw)[:10])
            except ValueError:
                appt_date = None
        stop_id = entry.get("id")
        parsed_id = int(stop_id) if stop_id not in (None, 0, "0") else None
        stops.append(
            LoadStopCreate(
                id=parsed_id,
                stop_type=stop_type,
                sequence=int(entry.get("sequence") if entry.get("sequence") is not None else index),
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
    load_number = _text(draft_json.get("loadNumber") or draft_json.get("load_number")) or None
    return LoadCreate(
        status="draft",
        load_number=load_number,
        broker_id=_optional_id(draft_json.get("brokerId") or draft_json.get("broker_id")),
        broker_contact_id=_optional_id(
            draft_json.get("brokerContactId") or draft_json.get("broker_contact_id")
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
        estimated_weight=_optional_int(draft_json.get("estimatedWeight") or draft_json.get("estimated_weight")),
        hazmat_flag=_hazmat_flag(draft_json),
        temperature_requirement=_text(
            draft_json.get("temperatureRequirement") or draft_json.get("temperature_requirement")
        )
        or None,
        pallet_case_count=_text(draft_json.get("palletCaseCount") or draft_json.get("pallet_case_count")) or None,
        rate=_optional_float(draft_json.get("rate")),
        customer_rate=_optional_float(draft_json.get("customerRate") or draft_json.get("customer_rate")),
        miles=_optional_int(draft_json.get("miles")),
        customs_broker_id=_optional_id(
            draft_json.get("customsBrokerId") or draft_json.get("customs_broker_id")
        ),
        internal_notes=_text(draft_json.get("internalNotes") or draft_json.get("internal_notes")) or None,
        references=_references(draft_json),
        stops=_stops(draft_json) or None,
    )
