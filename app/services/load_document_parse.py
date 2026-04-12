"""Parse freight load / rate confirmation PDFs for workspace field hydration.

Uses pypdf for text extraction and regex heuristics to populate LoadDocumentParseResponse.
No mutations — caller decides what to do with the returned dict.
"""
from __future__ import annotations

import io
import re
from typing import Any

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text_from_pdf_bytes(data: bytes) -> tuple[str, list[str]]:
    """Return (full_text, warnings)."""
    warnings: list[str] = []
    if PdfReader is None:
        warnings.append("pypdf not installed — cannot extract text")
        return "", warnings
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        warnings.append(f"PDF open error: {type(exc).__name__}")
        return "", warnings
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            parts.append(page.extract_text() or "")
        except Exception as exc:
            warnings.append(f"Page {i} extract error: {type(exc).__name__}")
    return "\n".join(parts), warnings


def _first(pattern: str, text: str, flags: int = re.IGNORECASE) -> str | None:
    m = re.search(pattern, text, flags)
    if m:
        val = m.group(1).strip()
        return val if val else None
    return None


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


def _try_float(s: str | None) -> float | None:
    if s is None:
        return None
    cleaned = re.sub(r"[,$\s]", "", s)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _try_int(s: str | None) -> int | None:
    v = _try_float(s)
    if v is None:
        return None
    return int(round(v))


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def _extract_mc(text: str) -> str | None:
    m = re.search(r"\bMC[#\s\-]*(\d{4,9})\b", text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _extract_dot(text: str) -> str | None:
    m = re.search(r"\bDOT[#\s\-]*(\d{4,9})\b", text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _extract_broker_name(text: str) -> str | None:
    """Heuristic: first line of the document or line before MC/DOT."""
    # Try explicit patterns first
    for pat in (
        r"(?:carrier|shipper|broker|company)[:\s]+([A-Z][A-Za-z0-9 &,.'()-]{3,60})",
        r"(?:from|issued by)[:\s]+([A-Z][A-Za-z0-9 &,.'()-]{3,60})",
    ):
        v = _first(pat, text)
        if v:
            return v

    # Use the first non-empty line if it looks like a company name
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 4 or len(line) > 80:
            continue
        if re.search(r"\d{5}", line):  # skip lines that are mostly an address
            continue
        if re.match(r"[A-Z][A-Za-z0-9 &,.'()-]{3,}", line):
            return line
    return None


def _extract_broker_contact_email(text: str) -> str | None:
    m = re.search(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", text)
    if m:
        return m.group(0)
    return None


def _extract_broker_contact_phone(text: str) -> str | None:
    m = re.search(
        r"\b(\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4})\b", text
    )
    if m:
        return m.group(1)
    return None


def _extract_load_reference(text: str) -> str | None:
    for pat in (
        r"(?:order|load|ref(?:erence)?|confirmation|conf|bol)[#\s\-:]*([A-Z0-9][A-Z0-9\-]{2,24})\b",
        r"\b(?:PO|REF|ORD)[#\s\-]*([A-Z0-9]{3,20})\b",
    ):
        v = _first(pat, text)
        if v:
            return v
    return None


def _extract_rate(text: str) -> float | None:
    for pat in (
        r"(?:all.?in|total|carrier|linehaul)[^$\n]{0,40}\$\s*([\d,]+(?:\.\d{1,2})?)",
        r"\$\s*([\d,]{3,}(?:\.\d{1,2})?)\b",
    ):
        v = _first(pat, text)
        if v:
            return _try_float(v)
    return None


def _extract_miles(text: str) -> float | None:
    for pat in (
        r"(\d{2,5})\s*(?:loaded\s*)?miles?",
        r"(?:distance|mileage)[:\s]+([\d,]+)",
    ):
        v = _first(pat, text, re.IGNORECASE)
        if v:
            return _try_float(v)
    return None


def _extract_weight(text: str) -> int | None:
    for pat in (
        r"(?:weight|wt)[:\s.]*([\d,]+)\s*(?:lbs?|pounds?|kg)?",
        r"([\d,]+)\s*lbs?\b",
    ):
        v = _first(pat, text, re.IGNORECASE)
        if v:
            return _try_int(v)
    return None


def _extract_equipment(text: str) -> tuple[str | None, str | None, str | None]:
    """Returns (equipment_type, trailer_type, trailer_size)."""
    equip = None
    for pat in (
        r"(?:equipment|equip(?:ment)?)[:\s]+([A-Za-z0-9/ -]{3,40})",
        r"\b(flatbed|reefer|refrigerated|dry\s*van|step\s*deck|lowboy|tanker|conestoga|van|curtain)\b",
    ):
        v = _first(pat, text)
        if v:
            equip = v
            break

    trailer = None
    for pat in (
        r"(?:trailer|unit)[:\s]+([A-Za-z0-9/ -]{3,40})",
        r"\b(flatbed|reefer|refrigerated|dry\s*van|step\s*deck|lowboy|tanker|conestoga|van|curtain)\b",
    ):
        v = _first(pat, text)
        if v:
            trailer = v
            break

    size = None
    m = re.search(r"\b(48|53|20|40|45)\s*(?:ft|foot|feet|')\b", text, re.IGNORECASE)
    if m:
        size = f"{m.group(1)}'"

    return equip, trailer, size


def _extract_commodity(text: str) -> str | None:
    for pat in (
        r"(?:commodity|cargo|freight|product|goods)[:\s]+([A-Za-z][A-Za-z0-9 ,/()-]{2,60})",
        r"(?:description)[:\s]+([A-Za-z][A-Za-z0-9 ,/()-]{2,60})",
    ):
        v = _first(pat, text)
        if v and len(v) > 2:
            return v
    return None


def _extract_temperature(text: str) -> str | None:
    m = re.search(r"(-?\d+)\s*°?\s*[FfCc]\b", text)
    if m:
        full = m.group(0).strip()
        return full
    for kw in ("frozen", "refrigerated", "temperature.?controlled", "reefer"):
        if re.search(kw, text, re.IGNORECASE):
            return kw.capitalize()
    return None


def _extract_customs_broker(text: str) -> str | None:
    v = _first(r"customs?\s*broker[:\s]+([A-Za-z][A-Za-z0-9 &,.'()-]{2,60})", text)
    return v


# ---------------------------------------------------------------------------
# Stop parsing
# ---------------------------------------------------------------------------

_US_STATE_RE = (
    r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO"
    r"|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY"
    r"|AB|BC|MB|NB|NL|NS|ON|PE|QC|SK|NT|NU|YT)\b"
)

_PICKUP_RE = re.compile(r"\b(pick.?up|shipper|origin|load at|loading)\b", re.IGNORECASE)
_DELIVERY_RE = re.compile(r"\b(deliver(?:y)?|consignee|destination|deliver to|drop.?off|unload)\b", re.IGNORECASE)
_DATE_RE = re.compile(
    r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}-\d{2}-\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)\b")
_ZIP_RE = re.compile(r"\b(\d{5}(?:-\d{4})?)\b")
_STATE_RE = re.compile(_US_STATE_RE)


def _normalize_date(raw: str) -> str | None:
    """Best-effort YYYY-MM-DD from common freight date formats."""
    raw = raw.strip()
    # Already ISO
    if re.match(r"\d{4}-\d{2}-\d{2}$", raw):
        return raw
    # MM/DD/YY or MM/DD/YYYY or MM-DD-YYYY
    m = re.match(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$", raw)
    if m:
        mo, dy, yr = m.group(1), m.group(2), m.group(3)
        if len(yr) == 2:
            yr = f"20{yr}"
        return f"{yr}-{int(mo):02d}-{int(dy):02d}"
    # Month name
    m2 = re.match(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})",
        raw, re.IGNORECASE,
    )
    if m2:
        _month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        mo_num = _month_map.get(m2.group(1)[:3].lower(), 0)
        if mo_num:
            return f"{m2.group(3)}-{mo_num:02d}-{int(m2.group(2)):02d}"
    return raw


def _parse_stops(text: str) -> list[dict[str, Any]]:
    """Heuristic multi-stop extraction from freight rate con text."""
    stops: list[dict[str, Any]] = []
    lines = text.splitlines()
    i = 0
    seq = 0

    while i < len(lines):
        line = lines[i].strip()
        stop_type: str | None = None

        if _PICKUP_RE.search(line):
            stop_type = "pickup"
        elif _DELIVERY_RE.search(line):
            stop_type = "delivery"

        if stop_type is None:
            i += 1
            continue

        # Collect the next few lines as a candidate address block
        block_lines = [line]
        for j in range(1, 8):
            if i + j >= len(lines):
                break
            nxt = lines[i + j].strip()
            if not nxt:
                break
            if _PICKUP_RE.search(nxt) or _DELIVERY_RE.search(nxt):
                break
            block_lines.append(nxt)

        block = " ".join(block_lines)

        facility_name: str | None = None
        street: str | None = None
        city: str | None = None
        state_or_province: str | None = None
        postal_code: str | None = None
        appointment_date: str | None = None
        appointment_time_text: str | None = None
        reference_number: str | None = None

        # Date
        dm = _DATE_RE.search(block)
        if dm:
            appointment_date = _normalize_date(dm.group(1))

        # Time
        tm = _TIME_RE.search(block)
        if tm:
            appointment_time_text = tm.group(1)

        # State
        sm = _STATE_RE.search(block)
        if sm:
            state_or_province = sm.group(1)

        # ZIP
        zm = _ZIP_RE.search(block)
        if zm:
            postal_code = zm.group(1)

        # Try to find city: word(s) before state
        if state_or_province:
            city_m = re.search(
                r"([A-Za-z][A-Za-z ]{1,30}),?\s+" + re.escape(state_or_province),
                block,
            )
            if city_m:
                city = city_m.group(1).strip()

        # Facility: first capitalized phrase not matching dates/times/addresses
        for bl in block_lines[1:3]:
            bl = bl.strip()
            if re.match(r"[A-Z][A-Za-z0-9 &,.'()-]{3,}", bl) and not _DATE_RE.search(bl):
                if not _ZIP_RE.search(bl) and not _STATE_RE.fullmatch(bl.strip()):
                    facility_name = bl
                    break

        # Reference number
        ref_m = re.search(
            r"(?:ref(?:erence)?|order|pu|po)[#:\s]+([A-Z0-9][A-Z0-9\-]{2,20})\b",
            block, re.IGNORECASE,
        )
        if ref_m:
            reference_number = ref_m.group(1)

        stops.append({
            "stop_type": stop_type,
            "sequence": seq,
            "facility_name": facility_name,
            "street": street,
            "city": city,
            "state_or_province": state_or_province,
            "postal_code": postal_code,
            "country": None,
            "reference_number": reference_number,
            "appointment_type": None,
            "appointment_date": appointment_date,
            "appointment_time_text": appointment_time_text,
            "notes": None,
        })
        seq += 1
        i += len(block_lines)

    return stops


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_load_workspace_from_pdf_bytes(
    data: bytes,
    *,
    filename: str | None = None,
    email_thread_id: int | None = None,
    load_id: int | None = None,
) -> dict[str, Any]:
    """Extract freight load fields from raw PDF bytes.

    Returns a plain dict matching LoadDocumentParseResponse.
    """
    safe_filename = (filename or "upload.pdf")[:512]
    raw_text, warnings = _extract_text_from_pdf_bytes(data)

    text = raw_text

    mc = _extract_mc(text)
    dot = _extract_dot(text)
    broker_name = _extract_broker_name(text)
    contact_email = _extract_broker_contact_email(text)
    contact_phone = _extract_broker_contact_phone(text)
    load_ref = _extract_load_reference(text)
    rate = _extract_rate(text)
    miles = _extract_miles(text)
    weight = _extract_weight(text)
    equip_type, trailer_type, trailer_size = _extract_equipment(text)
    commodity = _extract_commodity(text)
    temperature = _extract_temperature(text)
    customs_broker = _extract_customs_broker(text)
    stops = _parse_stops(text)

    if not raw_text.strip():
        warnings.append("No text could be extracted from this PDF — it may be image-only.")

    field_confidence: dict[str, str] = {}
    for field, value in (
        ("broker_name_snapshot", broker_name),
        ("broker_mc_number_snapshot", mc),
        ("broker_load_reference", load_ref),
        ("rate", rate),
        ("stops", stops),
    ):
        if value:
            field_confidence[field] = "regex"

    context: dict[str, Any] = {}
    if email_thread_id is not None:
        context["email_thread_id"] = email_thread_id
    if load_id is not None:
        context["load_id"] = load_id

    return {
        "document": {"filename": safe_filename},
        "extracted": {
            "broker_name_snapshot": broker_name,
            "broker_contact_name_snapshot": None,
            "broker_contact_phone_snapshot": contact_phone,
            "broker_contact_email_snapshot": contact_email,
            "broker_load_reference": load_ref,
            "broker_mc_number_snapshot": mc,
            "broker_dot_number_snapshot": dot,
            "mode": None,
            "equipment_type": equip_type,
            "trailer_type": trailer_type,
            "trailer_size": trailer_size,
            "commodity": commodity,
            "estimated_weight": weight,
            "temperature_requirement": temperature,
            "rate": rate,
            "customer_rate": None,
            "miles": miles,
            "customs_broker_name": customs_broker,
            "references": [],
            "stops": stops,
        },
        "raw_text": raw_text,
        "warnings": warnings,
        "field_confidence": field_confidence,
        "context": context,
    }
