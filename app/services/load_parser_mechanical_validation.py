"""Mechanical post-model validation for Load / Rate Confirmation parse responses.

OpenAI owns semantic interpretation. This module only:
- schema/shape cleanup
- exact/normalized tenant_identity_exclusion matches
- numeric/date/sequence sanity
- weak literal presence warnings (anti-hallucination)

Does **not** rank candidates, repair broker/carrier roles, select rates, or
consume PRODUCT_PARSE_DIAGNOSTICS.

Not wired into the production guarded parser path yet.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from app.schemas.load_document_parse import LoadDocumentParseResponse, LoadParseExtractedFields
from app.services.load_parser_rate_con_field_rules import LOAD_RATE_CON_FIELD_RULES
from app.services.load_parser_tenant_identity_exclusion import (
    normalize_authority_id,
    normalize_email,
    normalize_name_key,
    normalize_phone_digits,
)

# Syntactic contact shape (mirrors guarded contact-shape rules; no candidate scoring).
_EMAIL_SHAPE = re.compile(r"^[\w.+-]+@(?:[\w-]+\.)+[a-zA-Z]{2,}$")
_PHONE_IN_NAME_RE = re.compile(
    r"\b(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b"
)
_PHONE_SHAPE_RE = re.compile(
    r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}"
)
_DECIMAL_MONEY_LIKE_RE = re.compile(r"^\d+\.\d{2}$")
_WHITESPACE_RE = re.compile(r"\s+")

# Suspicious reference tokens (frozen mechanical list; no ranking / no diagnostics).
_SUSPICIOUS_REFERENCE_VALUES = frozenset(
    {
        "information",
        "information sheet",
        "load",
        "sheet",
        "type",
        "size",
        "date",
        "time",
        "throughout",
        "app",
    }
)

_ALLOWED_STOP_TYPES = frozenset({"pickup", "delivery", "drop", "other"})

# Frozen generic company mailbox local-parts (rejection backstop only; no replacement).
_GENERIC_COMPANY_MAILBOX_LOCALS = frozenset(
    {
        "carriers",
        "dispatch",
        "info",
        "operations",
        "billing",
        "accounting",
        "support",
    }
)

# Keys that must never leak into the public response context.
_CONTEXT_LEAK_KEYS = frozenset(
    {
        "parse_diagnostics",
        "PRODUCT_PARSE_DIAGNOSTICS",
        "contact_candidates",
        "authority_candidates",
        "reference_candidates",
        "reference_ranking",
        "financial_hints",
        "route_stop_hints",
        "numeric_candidates",
        "equipment_hints",
        "party_mentions",
    }
)


def apply_load_parser_mechanical_validation(
    response: LoadDocumentParseResponse,
    *,
    tenant_identity_exclusion: Mapping[str, Any] | None = None,
    page_texts: Sequence[str] | None = None,
) -> LoadDocumentParseResponse:
    """Return a sanitized copy of ``response`` after mechanical checks only.

    Does not mutate ``response``. Does not call OpenAI or diagnostics builders.
    """
    payload = response.model_dump(mode="json")
    warnings = list(payload.get("warnings") or [])
    field_confidence = dict(payload.get("field_confidence") or {})
    extracted = dict(payload.get("extracted") or {})
    context = dict(payload.get("context") or {})

    # Leak prevention: strip diagnostics / wire blobs from public context.
    for key in list(context.keys()):
        if key in _CONTEXT_LEAK_KEYS or key.casefold().startswith("diagnostic"):
            context.pop(key, None)
    payload.pop("parse_diagnostics", None)

    # References: non-empty kind/value only.
    extracted, w = _sanitize_references(extracted)
    warnings.extend(w)

    # Contact syntactic shape.
    extracted, w, fc = _validate_contact_shapes(extracted)
    warnings.extend(w)
    field_confidence.update(fc)

    # Named-person + generic company mailbox: reject email only (no replacement).
    extracted, w, fc = _reject_generic_company_mailbox(extracted)
    warnings.extend(w)
    field_confidence.update(fc)

    # Tenant identity exclusion (exact/normalized only).
    if tenant_identity_exclusion is not None:
        extracted, w, fc = _enforce_tenant_identity_exclusion(
            extracted, tenant_identity_exclusion
        )
        warnings.extend(w)
        field_confidence.update(fc)

    # Numeric sanity (no ceiling invented — finite + positive / non-negative only).
    extracted, w, fc = _validate_numerics(extracted)
    warnings.extend(w)
    field_confidence.update(fc)

    # Broker load reference mechanical checks (no candidate replacement).
    extracted, w, fc = _validate_broker_load_reference(extracted)
    warnings.extend(w)
    field_confidence.update(fc)

    # Stops: structure only.
    extracted, w, fc = _validate_stops(extracted)
    warnings.extend(w)
    field_confidence.update(fc)

    # Weak literal presence (warning-only; no substitution).
    combined = _combine_page_text(page_texts, fallback_raw=str(payload.get("raw_text") or ""))
    if combined:
        extracted, w = _literal_presence_warnings(extracted, combined)
        warnings.extend(w)

    payload["extracted"] = extracted
    payload["warnings"] = _dedupe_warnings(warnings)
    payload["field_confidence"] = field_confidence
    payload["context"] = context

    # Re-validate through Pydantic (types, required stop fields, lengths).
    return LoadDocumentParseResponse.model_validate(payload)


def _combine_page_text(
    page_texts: Sequence[str] | None,
    *,
    fallback_raw: str,
) -> str:
    if page_texts:
        return "\n".join(str(p or "") for p in page_texts)
    return fallback_raw or ""


def _dedupe_warnings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        s = str(v)
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _null_field(
    extracted: dict[str, Any],
    field: str,
    *,
    warning: str,
    field_confidence: dict[str, str],
) -> list[str]:
    extracted[field] = None
    field_confidence[field] = "low"
    return [warning]


def _sanitize_references(
    extracted: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    out = dict(extracted)
    refs = out.get("references")
    if not isinstance(refs, list):
        out["references"] = []
        return out, []
    clean: list[dict[str, Any]] = []
    warnings: list[str] = []
    dropped = 0
    for item in refs:
        if not isinstance(item, dict):
            dropped += 1
            continue
        kind = item.get("kind")
        value = item.get("value")
        if not isinstance(kind, str) or not kind.strip():
            dropped += 1
            continue
        if not isinstance(value, str) or not value.strip():
            dropped += 1
            continue
        clean.append({**item, "kind": kind.strip(), "value": value.strip()})
    out["references"] = clean
    if dropped:
        warnings.append(f"invalid_reference_item: dropped={dropped}")
    return out, warnings


def _validate_contact_shapes(
    extracted: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    out = dict(extracted)
    warnings: list[str] = []
    fc: dict[str, str] = {}

    name = str(out.get("broker_contact_name_snapshot") or "").strip()
    if name:
        if "@" in name:
            warnings.extend(
                _null_field(
                    out,
                    "broker_contact_name_snapshot",
                    warning="invalid_contact_name: broker_contact_name_snapshot (email-shaped)",
                    field_confidence=fc,
                )
            )
        elif _PHONE_IN_NAME_RE.search(name):
            warnings.extend(
                _null_field(
                    out,
                    "broker_contact_name_snapshot",
                    warning="invalid_contact_name: broker_contact_name_snapshot (phone-shaped)",
                    field_confidence=fc,
                )
            )

    email = str(out.get("broker_contact_email_snapshot") or "").strip()
    if email and not _EMAIL_SHAPE.match(email):
        warnings.extend(
            _null_field(
                out,
                "broker_contact_email_snapshot",
                warning="invalid_email: broker_contact_email_snapshot",
                field_confidence=fc,
            )
        )

    phone = str(out.get("broker_contact_phone_snapshot") or "").strip()
    if phone and not _PHONE_SHAPE_RE.search(phone):
        warnings.extend(
            _null_field(
                out,
                "broker_contact_phone_snapshot",
                warning="invalid_phone: broker_contact_phone_snapshot",
                field_confidence=fc,
            )
        )

    return out, warnings, fc


def _reject_generic_company_mailbox(
    extracted: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    """Null a named agent's email when the local-part is a frozen generic company mailbox."""
    out = dict(extracted)
    warnings: list[str] = []
    fc: dict[str, str] = {}

    name = str(out.get("broker_contact_name_snapshot") or "").strip()
    email = str(out.get("broker_contact_email_snapshot") or "").strip()
    if not name or not email or "@" not in email:
        return out, warnings, fc

    local = email.split("@", 1)[0].strip().casefold()
    if local not in _GENERIC_COMPANY_MAILBOX_LOCALS:
        return out, warnings, fc

    warnings.extend(
        _null_field(
            out,
            "broker_contact_email_snapshot",
            warning="generic_company_mailbox: broker_contact_email_snapshot",
            field_confidence=fc,
        )
    )
    return out, warnings, fc


def _enforce_tenant_identity_exclusion(
    extracted: dict[str, Any],
    exclusion: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    out = dict(extracted)
    warnings: list[str] = []
    fc: dict[str, str] = {}

    name_keys = {
        normalize_name_key(n)
        for n in (exclusion.get("names") or [])
        if isinstance(n, str) and normalize_name_key(n)
    }
    email_keys = {
        normalize_email(e)
        for e in (exclusion.get("emails") or [])
        if isinstance(e, str) and normalize_email(e)
    }
    phone_keys = {
        normalize_phone_digits(p)
        for p in (exclusion.get("phones") or [])
        if isinstance(p, str) and normalize_phone_digits(p)
    }
    mc_keys = {
        normalize_authority_id(m)
        for m in (exclusion.get("mc_numbers") or [])
        if isinstance(m, str) and normalize_authority_id(m)
    }
    dot_keys = {
        normalize_authority_id(d)
        for d in (exclusion.get("usdot_numbers") or [])
        if isinstance(d, str) and normalize_authority_id(d)
    }

    broker_name = str(out.get("broker_name_snapshot") or "").strip()
    if broker_name and normalize_name_key(broker_name) in name_keys:
        warnings.extend(
            _null_field(
                out,
                "broker_name_snapshot",
                warning="tenant_identity_match: broker_name_snapshot",
                field_confidence=fc,
            )
        )

    email = str(out.get("broker_contact_email_snapshot") or "").strip()
    if email:
        ek = normalize_email(email)
        if ek and ek in email_keys:
            warnings.extend(
                _null_field(
                    out,
                    "broker_contact_email_snapshot",
                    warning="tenant_identity_match: broker_contact_email_snapshot",
                    field_confidence=fc,
                )
            )

    phone = str(out.get("broker_contact_phone_snapshot") or "").strip()
    if phone:
        pk = normalize_phone_digits(phone)
        if pk and pk in phone_keys:
            warnings.extend(
                _null_field(
                    out,
                    "broker_contact_phone_snapshot",
                    warning="tenant_identity_match: broker_contact_phone_snapshot",
                    field_confidence=fc,
                )
            )

    mc = str(out.get("broker_mc_number_snapshot") or "").strip()
    if mc:
        mk = normalize_authority_id(mc)
        if mk and mk in mc_keys:
            warnings.extend(
                _null_field(
                    out,
                    "broker_mc_number_snapshot",
                    warning="tenant_identity_match: broker_mc_number_snapshot",
                    field_confidence=fc,
                )
            )

    dot = str(out.get("broker_dot_number_snapshot") or "").strip()
    if dot:
        dk = normalize_authority_id(dot)
        if dk and dk in dot_keys:
            warnings.extend(
                _null_field(
                    out,
                    "broker_dot_number_snapshot",
                    warning="tenant_identity_match: broker_dot_number_snapshot",
                    field_confidence=fc,
                )
            )

    return out, warnings, fc


def _is_bad_number(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return not math.isfinite(float(value))
    return True


def _validate_numerics(
    extracted: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    out = dict(extracted)
    warnings: list[str] = []
    fc: dict[str, str] = {}

    for field in ("rate", "customer_rate"):
        val = out.get(field)
        if val is None:
            continue
        if _is_bad_number(val) or float(val) <= 0:
            warnings.extend(
                _null_field(
                    out,
                    field,
                    warning=f"invalid_number: {field}",
                    field_confidence=fc,
                )
            )

    miles = out.get("miles")
    if miles is not None:
        if _is_bad_number(miles) or float(miles) < 0:
            warnings.extend(
                _null_field(
                    out,
                    "miles",
                    warning="invalid_number: miles",
                    field_confidence=fc,
                )
            )

    weight = out.get("estimated_weight")
    if weight is not None:
        # Schema expects int; reject bool, non-finite float, negatives.
        bad = False
        if isinstance(weight, bool):
            bad = True
        elif isinstance(weight, int):
            bad = weight < 0
        elif isinstance(weight, float):
            bad = (not math.isfinite(weight)) or weight < 0
        else:
            bad = True
        if bad:
            warnings.extend(
                _null_field(
                    out,
                    "estimated_weight",
                    warning="invalid_number: estimated_weight",
                    field_confidence=fc,
                )
            )

    return out, warnings, fc


def _is_suspicious_load_reference(value: str) -> bool:
    v = value.strip().casefold()
    if v in _SUSPICIOUS_REFERENCE_VALUES:
        return True
    raw = value.strip().replace(",", "")
    if raw and _DECIMAL_MONEY_LIKE_RE.fullmatch(raw):
        return True
    if not any(ch.isdigit() for ch in v) and len(v) < 16:
        return True
    return False


def _strip_load_reference_field_label(value: str) -> str:
    """Remove a leading discovery label when a field separator is present.

    Separator-gated only: glued identifiers such as PO12345 are preserved.
    Does not select a different identifier.
    """
    text = (value or "").strip()
    if not text:
        return text
    labels = [
        str(label).strip()
        for label in (
            LOAD_RATE_CON_FIELD_RULES["rules"]["principal_load_identifier"].get(
                "possible_labels_examples"
            )
            or []
        )
        if str(label).strip()
    ]
    labels.sort(key=len, reverse=True)
    for raw in labels:
        if raw.endswith("#"):
            stem = raw[:-1].strip()
            pat = re.compile(rf"^{re.escape(stem)}\s*#\s*", re.IGNORECASE)
        else:
            pat = re.compile(rf"^{re.escape(raw)}\s*[:#]\s*", re.IGNORECASE)
        match = pat.match(text)
        if match:
            rest = text[match.end() :].strip()
            if raw.endswith("#") and rest.startswith(":"):
                rest = rest[1:].strip()
            return rest
    return text


def _validate_broker_load_reference(
    extracted: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    out = dict(extracted)
    warnings: list[str] = []
    fc: dict[str, str] = {}

    ref = out.get("broker_load_reference")
    if ref is None:
        return out, warnings, fc
    if not isinstance(ref, str):
        warnings.extend(
            _null_field(
                out,
                "broker_load_reference",
                warning="invalid_load_reference: broker_load_reference",
                field_confidence=fc,
            )
        )
        return out, warnings, fc

    trimmed = _WHITESPACE_RE.sub(" ", ref).strip()
    trimmed = _strip_load_reference_field_label(trimmed)
    if not trimmed:
        warnings.extend(
            _null_field(
                out,
                "broker_load_reference",
                warning="invalid_load_reference: broker_load_reference (empty)",
                field_confidence=fc,
            )
        )
        return out, warnings, fc

    if _is_suspicious_load_reference(trimmed):
        warnings.extend(
            _null_field(
                out,
                "broker_load_reference",
                warning="invalid_load_reference: broker_load_reference",
                field_confidence=fc,
            )
        )
        return out, warnings, fc

    out["broker_load_reference"] = trimmed
    return out, warnings, fc


def _parse_calendar_date(value: str) -> date | None:
    """Require a real calendar YYYY-MM-DD (rejects 2026-02-31)."""
    s = (value or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _validate_stops(
    extracted: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    out = dict(extracted)
    warnings: list[str] = []
    fc: dict[str, str] = {}
    stops = out.get("stops")
    if not isinstance(stops, list):
        out["stops"] = []
        return out, warnings, fc

    new_stops: list[Any] = []
    seen_sequences: dict[int, int] = {}
    for idx, stop in enumerate(stops):
        if not isinstance(stop, dict):
            continue
        s = dict(stop)

        # stop_type: allow product set; unknown → "other" + warning (schema requires string).
        st = str(s.get("stop_type") or "").strip().casefold()
        if st not in _ALLOWED_STOP_TYPES:
            warnings.append(f"invalid_stop_type: stops[{idx}]")
            s["stop_type"] = "other"
            fc["stops"] = "low"
        else:
            s["stop_type"] = st

        # sequence >= 0
        seq_raw = s.get("sequence")
        try:
            seq = int(seq_raw)
        except (TypeError, ValueError):
            seq = 0
            warnings.append(f"invalid_stop_sequence: stops[{idx}]")
            fc["stops"] = "low"
        if seq < 0:
            warnings.append(f"invalid_stop_sequence: stops[{idx}]")
            seq = 0
            fc["stops"] = "low"
        s["sequence"] = seq
        seen_sequences[seq] = seen_sequences.get(seq, 0) + 1

        # Syntactic appointment prefix normalize.
        time_text = str(s.get("appointment_time_text") or "").strip()
        if time_text.casefold().startswith("appt "):
            s["appointment_type"] = s.get("appointment_type") or "APPT"
            s["appointment_time_text"] = time_text[5:].strip()
        elif time_text.casefold().startswith("fcfs "):
            s["appointment_type"] = s.get("appointment_type") or "FCFS"
            s["appointment_time_text"] = time_text[5:].strip()

        # Calendar date validation.
        appt = s.get("appointment_date")
        if appt is not None and str(appt).strip():
            parsed = _parse_calendar_date(str(appt))
            if parsed is None:
                s["appointment_date"] = None
                warnings.append(f"invalid_date: stops[{idx}].appointment_date")
                fc["stops"] = "low"
            else:
                s["appointment_date"] = parsed.isoformat()

        new_stops.append(s)

    for seq, count in sorted(seen_sequences.items()):
        if count > 1:
            warnings.append(f"duplicate_stop_sequence: {seq}")
            fc["stops"] = "low"

    out["stops"] = new_stops
    return out, warnings, fc


def _normalize_money_token(amount: float) -> set[str]:
    """Comparable digit tokens for weak rate presence (no semantic linehaul pick)."""
    if not math.isfinite(amount):
        return set()
    # Integer cents path when close to two decimals.
    cents = int(round(amount * 100))
    whole = cents // 100
    frac = cents % 100
    tokens = {
        str(whole),
        f"{whole}.{frac:02d}",
        f"{whole:d}",
    }
    # Also allow comma-grouped whole (search uses digit-stripped haystack too).
    return tokens


def _digits_only(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def _literal_presence_warnings(
    extracted: dict[str, Any],
    combined_text: str,
) -> tuple[dict[str, Any], list[str]]:
    """Warning-only anti-hallucination checks. Never substitutes values."""
    out = dict(extracted)
    warnings: list[str] = []
    hay = combined_text or ""
    hay_cf = hay.casefold()
    hay_digits = _digits_only(hay)

    ref = str(out.get("broker_load_reference") or "").strip()
    if ref:
        # Conservative: casefold substring OR digit-core substring for hyphenated ids.
        ref_cf = ref.casefold()
        ref_digits = _digits_only(ref)
        present = ref_cf in hay_cf
        if not present and ref_digits and len(ref_digits) >= 4:
            present = ref_digits in hay_digits
        if not present:
            warnings.append("value_not_found_in_source: broker_load_reference")

    phone = str(out.get("broker_contact_phone_snapshot") or "").strip()
    if phone:
        pk = normalize_phone_digits(phone)
        if pk and pk not in hay_digits:
            # Also try last-10 for longer fingerprints.
            last10 = pk[-10:] if len(pk) >= 10 else pk
            if last10 not in hay_digits:
                warnings.append("value_not_found_in_source: broker_contact_phone_snapshot")

    rate = out.get("rate")
    if isinstance(rate, (int, float)) and not isinstance(rate, bool) and math.isfinite(float(rate)):
        tokens = _normalize_money_token(float(rate))
        # Search in digit-stripped form and plain text.
        found = False
        for tok in tokens:
            if tok in hay or tok in hay_digits:
                found = True
                break
            # Comma form e.g. 1,800
            if "." not in tok and len(tok) > 3:
                with_comma = f"{int(tok):,}"
                if with_comma in hay:
                    found = True
                    break
        if not found:
            warnings.append("value_not_found_in_source: rate")

    return out, warnings
