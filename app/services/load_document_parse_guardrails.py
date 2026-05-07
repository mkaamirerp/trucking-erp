"""Product-owned guarded repairs for load document parse responses."""

from __future__ import annotations

import re
from typing import Any

from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_parse_diagnostics import _normalize_person_name_key
from app.services.load_document_parse_reference import merge_ranked_references_into_extracted

_DECIMAL_RE = re.compile(r"^\d+\.\d+$")


def apply_guarded_load_document_repairs(
    response: LoadDocumentParseResponse,
    *,
    diagnostics: dict[str, Any] | None,
) -> LoadDocumentParseResponse:
    payload = response.model_dump(mode="json")
    extracted = payload.get("extracted") if isinstance(payload.get("extracted"), dict) else {}
    warnings = list(payload.get("warnings") or [])
    field_confidence = dict(payload.get("field_confidence") or {})

    extracted, ref_warnings, ref_conf = merge_ranked_references_into_extracted(extracted, diagnostics)
    warnings.extend(ref_warnings)
    field_confidence.update(ref_conf)

    extracted, route_warnings, route_conf = _apply_route_stop_hints(extracted, diagnostics)
    warnings.extend(route_warnings)
    field_confidence.update(route_conf)

    extracted, cleanup_warnings, cleanup_conf = _cleanup_trailer_temp_and_reference(extracted, diagnostics)
    warnings.extend(cleanup_warnings)
    field_confidence.update(cleanup_conf)

    extracted, stop_warnings, stop_conf = _normalize_stop_appointments(extracted)
    warnings.extend(stop_warnings)
    field_confidence.update(stop_conf)

    extracted, authority_warnings, authority_conf = _repair_broker_authority_fields(extracted, diagnostics)
    warnings.extend(authority_warnings)
    field_confidence.update(authority_conf)

    extracted, contact_warnings, contact_conf = _enforce_broker_contact_candidate_rules(
        extracted, diagnostics
    )
    warnings.extend(contact_warnings)
    field_confidence.update(contact_conf)

    payload["extracted"] = extracted
    payload["warnings"] = _dedupe_strings(warnings)
    payload["field_confidence"] = field_confidence
    repaired = LoadDocumentParseResponse.model_validate(payload)
    return repaired


def _apply_route_stop_hints(
    extracted: dict[str, Any],
    diagnostics: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    out = dict(extracted)
    hints = diagnostics.get("route_stop_hints") if isinstance(diagnostics, dict) else None
    stops = out.get("stops") if isinstance(out.get("stops"), list) else None
    if not isinstance(hints, list) or not isinstance(stops, list) or not hints:
        return out, [], {}

    hint_by_sequence = {
        int(h["sequence"]): h
        for h in hints
        if isinstance(h, dict) and isinstance(h.get("sequence"), int)
    }
    changed = False
    next_stops: list[Any] = []
    for stop in stops:
        if not isinstance(stop, dict):
            next_stops.append(stop)
            continue
        s = dict(stop)
        hint = hint_by_sequence.get(int(s.get("sequence") or 0))
        if hint:
            for field in (
                "facility_name",
                "street",
                "city",
                "state_or_province",
                "postal_code",
                "reference_number",
                "appointment_date",
                "appointment_time_text",
            ):
                if not s.get(field) and hint.get(field):
                    s[field] = hint[field]
                    changed = True
        next_stops.append(s)

    out["stops"] = next_stops
    if not changed:
        return out, [], {}
    return out, ["[guarded] Filled missing stop details from structured route lines."], {"stops": "medium"}


def _cleanup_trailer_temp_and_reference(
    extracted: dict[str, Any],
    diagnostics: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    out = dict(extracted)
    warnings: list[str] = []
    field_confidence: dict[str, str] = {}

    ref = str(out.get("broker_load_reference") or "").strip()
    if ref and _DECIMAL_RE.match(ref):
        out["broker_load_reference"] = None
        warnings.append("[guarded] Cleared decimal-like broker_load_reference; likely money, weight, or rate.")
        field_confidence["broker_load_reference"] = "low"

    temp = str(out.get("temperature_requirement") or "").strip()
    if temp and temp.casefold() in {"reefer", "refrigerated", "dry van", "van", "flatbed"}:
        if not out.get("trailer_type"):
            out["trailer_type"] = temp
        out["temperature_requirement"] = None
        warnings.append("[guarded] Moved equipment-like temperature value to trailer_type.")
        field_confidence["trailer_type"] = "low"

    equipment_type_raw = str(out.get("equipment_type") or "").strip()
    if equipment_type_raw and (not out.get("trailer_type") or not out.get("trailer_size")):
        eq_m = re.match(
            r"^(?P<type>[A-Za-z][A-Za-z\s]{0,40}?)\s*-\s*(?P<size>.+)$",
            equipment_type_raw,
        )
        if eq_m:
            split_applied = False
            left = eq_m.group("type").strip()
            right = eq_m.group("size").strip()
            if left and right and not out.get("trailer_type"):
                inferred_left = _trailer_type_from_clean_equipment(left)
                out["trailer_type"] = inferred_left or (left.title() if len(left) < 36 else None)
                if out.get("trailer_type"):
                    field_confidence.setdefault("trailer_type", "medium")
                    split_applied = True
            if right and not out.get("trailer_size"):
                rs = right.strip()
                if re.fullmatch(r"\d{2,3}", rs):
                    out["trailer_size"] = f"{rs}'"
                else:
                    out["trailer_size"] = rs
                field_confidence.setdefault("trailer_size", "medium")
                split_applied = True
            if split_applied:
                warnings.append("[guarded] Split combined equipment_type into trailer_type and trailer_size.")

    trailer_size = str(out.get("trailer_size") or "").strip()
    if trailer_size and trailer_size.isdigit():
        out["trailer_size"] = f"{trailer_size}'"
    trailer_type = str(out.get("trailer_type") or "").strip()
    equipment = diagnostics.get("equipment_hints") if isinstance(diagnostics, dict) else None
    moved_numeric_trailer_type = False
    if trailer_type.isdigit() and not out.get("trailer_size"):
        out["trailer_size"] = trailer_type
        out["trailer_type"] = None
        moved_numeric_trailer_type = True
        warnings.append("[guarded] Moved numeric trailer_type into trailer_size.")
        field_confidence["trailer_size"] = "medium"
    if isinstance(equipment, dict):
        if moved_numeric_trailer_type and not out.get("trailer_type") and equipment.get("trailer_type"):
            out["trailer_type"] = equipment["trailer_type"]
            field_confidence["trailer_type"] = "medium"
        if moved_numeric_trailer_type and not out.get("trailer_size") and equipment.get("trailer_size"):
            out["trailer_size"] = equipment["trailer_size"]
            field_confidence["trailer_size"] = "medium"
    if not out.get("trailer_type"):
        inferred = _trailer_type_from_clean_equipment(str(out.get("equipment_type") or ""))
        if inferred:
            out["trailer_type"] = inferred
            field_confidence["trailer_type"] = "medium"

    rate = out.get("rate")
    if isinstance(rate, (int, float)) and rate <= 300 and _low_rate_has_accessorial_context(rate, diagnostics):
        out["rate"] = None
        warnings.append("[guarded] Cleared low dollar amount likely from detention/TONU/layover terms, not linehaul rate.")
        field_confidence["rate"] = "low"
    if out.get("rate") is None and isinstance(out.get("customer_rate"), (int, float)):
        out["rate"] = out.get("customer_rate")
        out["customer_rate"] = None
        warnings.append("[guarded] Moved parsed customer_rate into rate for broker rate confirmation.")
        field_confidence["rate"] = "medium"
    if out.get("rate") is None:
        financial = diagnostics.get("financial_hints") if isinstance(diagnostics, dict) else None
        linehaul_rate = financial.get("linehaul_rate") if isinstance(financial, dict) else None
        if isinstance(linehaul_rate, (int, float)) and linehaul_rate > 0:
            out["rate"] = float(linehaul_rate)
            warnings.append("[guarded] rate filled from explicit linehaul/rate amount in document text.")
            field_confidence["rate"] = "medium"

    return out, warnings, field_confidence


def _normalize_stop_appointments(
    extracted: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    out = dict(extracted)
    stops = out.get("stops") if isinstance(out.get("stops"), list) else None
    if stops is None:
        return out, [], {}

    changed = False
    new_stops: list[Any] = []
    for stop in stops:
        if not isinstance(stop, dict):
            new_stops.append(stop)
            continue
        s = dict(stop)
        time_text = str(s.get("appointment_time_text") or "").strip()
        if time_text.casefold().startswith("appt "):
            s["appointment_type"] = s.get("appointment_type") or "APPT"
            s["appointment_time_text"] = time_text[5:].strip()
            changed = True
        elif time_text.casefold().startswith("fcfs "):
            s["appointment_type"] = s.get("appointment_type") or "FCFS"
            s["appointment_time_text"] = time_text[5:].strip()
            changed = True
        new_stops.append(s)

    out["stops"] = new_stops
    if not changed:
        return out, [], {}
    return out, ["[guarded] Normalized stop appointment type/time text."], {"stops": "medium"}


def _phone_fingerprint(value: str) -> str:
    return re.sub(r"\D", "", value or "")


_BROKER_EMAIL_SHAPE = re.compile(r"^[\w.+-]+@(?:[\w-]+\.)+[a-zA-Z]{2,}$")
_NON_BROKER_ROLES = frozenset(
    {
        "carrier_party",
        "driver_party",
        "payment_paperwork_party",
        "shipper_receiver_party",
    }
)


def _sanitize_broker_contact_field_types(extracted: dict[str, Any]) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    out = dict(extracted)
    warnings: list[str] = []
    fc: dict[str, str] = {}

    name = str(out.get("broker_contact_name_snapshot") or "").strip()
    if name:
        if "@" in name:
            out["broker_contact_name_snapshot"] = None
            warnings.append("[guarded] Cleared broker_contact_name_snapshot: must not contain '@'.")
            fc["broker_contact_name_snapshot"] = "low"
        elif re.search(
            r"\b(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b",
            name,
        ):
            out["broker_contact_name_snapshot"] = None
            warnings.append("[guarded] Cleared broker_contact_name_snapshot: value is phone-like.")
            fc["broker_contact_name_snapshot"] = "low"

    email = str(out.get("broker_contact_email_snapshot") or "").strip()
    if email and not _BROKER_EMAIL_SHAPE.match(email):
        out["broker_contact_email_snapshot"] = None
        warnings.append("[guarded] Cleared broker_contact_email_snapshot: not email-shaped.")
        fc["broker_contact_email_snapshot"] = "low"

    phone = str(out.get("broker_contact_phone_snapshot") or "").strip()
    if phone and not re.search(
        r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}",
        phone,
    ):
        out["broker_contact_phone_snapshot"] = None
        warnings.append("[guarded] Cleared broker_contact_phone_snapshot: not phone-shaped.")
        fc["broker_contact_phone_snapshot"] = "low"

    return out, warnings, fc


def _norm_email_key(value: str) -> str:
    return str(value or "").strip().casefold()


def _first_primary_broker_email(candidates: list[dict[str, Any]]) -> str | None:
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if item.get("kind") != "email" or item.get("role") != "broker_party":
            continue
        if item.get("broker_contact_tier") == "secondary":
            continue
        val = str(item.get("value") or "").strip()
        if val:
            return val
    return None


def _first_primary_broker_phone(candidates: list[dict[str, Any]]) -> str | None:
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if item.get("kind") != "phone" or item.get("role") != "broker_party":
            continue
        if item.get("broker_contact_tier") == "secondary":
            continue
        val = str(item.get("value") or "").strip()
        if val:
            return val
    return None


def _enforce_broker_contact_candidate_rules(
    extracted: dict[str, Any],
    diagnostics: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    """Shape + contact_candidates allowlist: broker_contact_* only from broker_party roles."""
    out = dict(extracted)
    warnings: list[str] = []
    field_confidence: dict[str, str] = {}

    out, w1, f1 = _sanitize_broker_contact_field_types(out)
    warnings.extend(w1)
    field_confidence.update(f1)

    if not isinstance(diagnostics, dict):
        return out, warnings, field_confidence

    cands = diagnostics.get("contact_candidates")
    if not isinstance(cands, list):
        return out, warnings, field_confidence

    broker_email_keys: set[str] = set()
    broker_phone_fps: set[str] = set()
    broker_name_keys: set[str] = set()
    forbidden_email_keys: set[str] = set()
    forbidden_phone_fps: set[str] = set()
    forbidden_name_keys: set[str] = set()
    secondary_email_keys: set[str] = set()
    secondary_phone_fps: set[str] = set()

    for item in cands:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        role = str(item.get("role") or "")
        val = str(item.get("value") or "").strip()
        if not val:
            continue

        if kind == "email":
            key = _norm_email_key(val)
            if role == "broker_party":
                broker_email_keys.add(key)
                if item.get("broker_contact_tier") == "secondary":
                    secondary_email_keys.add(key)
            elif role in _NON_BROKER_ROLES:
                forbidden_email_keys.add(key)
        elif kind == "phone":
            fp = _phone_fingerprint(val)
            if len(fp) >= 10:
                fp = fp[-10:]
            if role == "broker_party":
                if fp:
                    broker_phone_fps.add(fp)
                if item.get("broker_contact_tier") == "secondary" and fp:
                    secondary_phone_fps.add(fp)
            elif role in _NON_BROKER_ROLES:
                if fp:
                    forbidden_phone_fps.add(fp)
        elif kind == "name":
            nk = _normalize_person_name_key(val)
            if role == "broker_party":
                if nk:
                    broker_name_keys.add(nk)
            elif role in _NON_BROKER_ROLES:
                if nk:
                    forbidden_name_keys.add(nk)

    email_val = str(out.get("broker_contact_email_snapshot") or "").strip()
    if email_val:
        ek = _norm_email_key(email_val)
        if ek in forbidden_email_keys:
            out["broker_contact_email_snapshot"] = None
            field_confidence["broker_contact_email_snapshot"] = "low"
            warnings.append(
                "[guarded] Cleared broker_contact_email_snapshot: classified as non-broker contact in document sections."
            )
        elif ek in secondary_email_keys:
            primary = _first_primary_broker_email(cands)
            if primary and _norm_email_key(primary) != ek:
                out["broker_contact_email_snapshot"] = primary
                field_confidence["broker_contact_email_snapshot"] = "medium"
                warnings.append(
                    "[guarded] broker_contact_email_snapshot preferred primary broker ops address over tracking/secondary mailbox."
                )
        elif broker_email_keys and ek not in broker_email_keys:
            out["broker_contact_email_snapshot"] = None
            field_confidence["broker_contact_email_snapshot"] = "low"
            warnings.append(
                "[guarded] Cleared broker_contact_email_snapshot: not among broker_party email candidates from diagnostics."
            )

    phone_val = str(out.get("broker_contact_phone_snapshot") or "").strip()
    if phone_val:
        pfp = _phone_fingerprint(phone_val)
        if len(pfp) >= 10:
            pfp = pfp[-10:]
        if pfp and pfp in forbidden_phone_fps:
            out["broker_contact_phone_snapshot"] = None
            field_confidence["broker_contact_phone_snapshot"] = "low"
            warnings.append(
                "[guarded] Cleared broker_contact_phone_snapshot: classified as non-broker phone in document sections."
            )
        elif pfp in secondary_phone_fps:
            primary_phone = _first_primary_broker_phone(cands)
            if primary_phone:
                pfp_p = _phone_fingerprint(primary_phone)
                if len(pfp_p) >= 10:
                    pfp_p = pfp_p[-10:]
                if pfp_p and pfp_p != pfp:
                    out["broker_contact_phone_snapshot"] = primary_phone
                    field_confidence["broker_contact_phone_snapshot"] = "medium"
                    warnings.append(
                        "[guarded] broker_contact_phone_snapshot preferred primary broker ops line over after-hours/secondary phone."
                    )
        elif broker_phone_fps and pfp not in broker_phone_fps:
            out["broker_contact_phone_snapshot"] = None
            field_confidence["broker_contact_phone_snapshot"] = "low"
            warnings.append(
                "[guarded] Cleared broker_contact_phone_snapshot: not among broker_party phone candidates from diagnostics."
            )

    name_val = str(out.get("broker_contact_name_snapshot") or "").strip()
    if name_val:
        nk = _normalize_person_name_key(name_val)
        if nk and nk in forbidden_name_keys:
            out["broker_contact_name_snapshot"] = None
            field_confidence["broker_contact_name_snapshot"] = "low"
            warnings.append(
                "[guarded] Cleared broker_contact_name_snapshot: classified as carrier/driver-party name in document sections."
            )
        elif broker_name_keys and nk not in broker_name_keys:
            out["broker_contact_name_snapshot"] = None
            field_confidence["broker_contact_name_snapshot"] = "low"
            warnings.append(
                "[guarded] Cleared broker_contact_name_snapshot: not among broker_party name candidates from diagnostics."
            )

    return out, warnings, field_confidence


def _repair_broker_authority_fields(
    extracted: dict[str, Any],
    diagnostics: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    out = dict(extracted)
    warnings: list[str] = []
    field_confidence: dict[str, str] = {}
    authority = diagnostics.get("authority_candidates") if isinstance(diagnostics, dict) else None
    if not isinstance(authority, list):
        return out, warnings, field_confidence

    broker_mc = _first_authority(authority, "mc", "broker_context")
    broker_dot = _first_authority(authority, "dot", "broker_context")
    carrier_mc_values = _authority_values(authority, "mc", "carrier_context")
    carrier_dot_values = _authority_values(authority, "dot", "carrier_context")

    current_mc = str(out.get("broker_mc_number_snapshot") or "").strip()
    current_mc_key = _digits_key(current_mc)
    if current_mc and current_mc_key in carrier_mc_values and broker_mc and _digits_key(broker_mc) != current_mc_key:
        out["broker_mc_number_snapshot"] = broker_mc
        warnings.append("[guarded] Broker MC repaired using authority role hints.")
        field_confidence["broker_mc_number_snapshot"] = "low"
    elif current_mc and current_mc_key in carrier_mc_values and not broker_mc:
        out["broker_mc_number_snapshot"] = None
        warnings.append("[guarded] Cleared broker MC because only carrier-context MC was found.")
        field_confidence["broker_mc_number_snapshot"] = "low"

    current_dot = str(out.get("broker_dot_number_snapshot") or "").strip()
    current_dot_key = _digits_key(current_dot)
    if current_dot and current_dot_key in carrier_dot_values and broker_dot and _digits_key(broker_dot) != current_dot_key:
        out["broker_dot_number_snapshot"] = broker_dot
        warnings.append("[guarded] Broker DOT repaired using authority role hints.")
        field_confidence["broker_dot_number_snapshot"] = "low"
    elif current_dot and current_dot_key in carrier_dot_values and not broker_dot:
        out["broker_dot_number_snapshot"] = None
        warnings.append("[guarded] Cleared broker DOT because only carrier-context DOT was found.")
        field_confidence["broker_dot_number_snapshot"] = "low"

    return out, warnings, field_confidence


def _first_authority(authority: list[Any], kind: str, role_hint: str) -> str | None:
    for item in authority:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == kind and item.get("role_hint") == role_hint and item.get("value"):
            return str(item["value"])
    return None


def _authority_values(authority: list[Any], kind: str, role_hint: str) -> set[str]:
    return {
        _digits_key(str(item.get("value") or ""))
        for item in authority
        if isinstance(item, dict) and item.get("kind") == kind and item.get("role_hint") == role_hint and item.get("value")
    }


def _digits_key(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _trailer_type_from_clean_equipment(value: str) -> str | None:
    v = re.sub(r"\s+", " ", value.strip()).casefold()
    if any(ch.isdigit() for ch in v):
        return None
    if v in {"dry van", "van"}:
        return "Van"
    if v in {"reefer", "refrigerated"}:
        return "Reefer"
    if v == "flatbed":
        return "Flatbed"
    if v == "step deck":
        return "Step Deck"
    return None


def _dedupe_strings(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        s = str(value)
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _low_rate_has_accessorial_context(rate: int | float, diagnostics: dict[str, Any] | None) -> bool:
    money = diagnostics.get("numeric_candidates", {}).get("money") if isinstance(diagnostics, dict) else None
    if not isinstance(money, list):
        return False
    target = f"{int(rate)}"
    for item in money:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "")
        context = str(item.get("context") or "").casefold()
        if target in value and any(term in context for term in ("detention", "tonu", "layover", "cap")):
            return True
    return False
