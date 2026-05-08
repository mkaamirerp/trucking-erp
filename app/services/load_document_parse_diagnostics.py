"""Product-owned diagnostics for guarded load document parsing.

No Load Lab imports. Diagnostics are prompt/repair evidence only; product
responses strip diagnostics before returning to callers.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.load_document_parse_contact_candidates import (
    build_contact_candidates,
    summarize_contacts_from_candidates,
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\b(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b")
_MC_RE = re.compile(r"\bMC[#\s:-]*(\d{4,9})\b", re.IGNORECASE)
_DOT_RE = re.compile(r"\b(?:USDOT|DOT)[#\s:-]*(\d{4,9})\b", re.IGNORECASE)
_REF_RE = re.compile(
    r"\b(?P<label>load|order|po|p\.?o\.?|bol|b\.?o\.?l\.?|ref(?:erence)?|confirmation|conf|shipment|pro|fb|el)"
    r"[\s#:-]{0,8}(?P<value>[A-Z0-9][A-Z0-9._/-]{2,30})\b",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"\$\s*[\d,]+(?:\.\d{1,2})?")
_WEIGHT_RE = re.compile(r"\b[\d,]{4,6}\s*(?:lbs?|pounds?)\b", re.IGNORECASE)
_COMPANY_LINE_RE = re.compile(
    r"\b(?:broker|carrier|shipper|consignee|bill\s*to|remit\s*to|dispatcher|contact)\b"
    r"[\s:.-]+(?P<name>[A-Z][A-Za-z0-9 &,.'()/-]{2,80})",
    re.IGNORECASE,
)


def build_load_document_parse_diagnostics(
    *,
    raw_full_text: str,
    page_texts: list[str] | None,
    filename: str,
    extraction_method: str,
) -> dict[str, Any]:
    text = raw_full_text or ""
    pages = list(page_texts) if page_texts else []
    if not pages:
        pages = [text] if text else [""]
    contact_candidates = build_contact_candidates(pages)
    return {
        "version": "load_document_parse_diagnostics_v2",
        "source": {
            "filename": filename,
            "extraction_method": extraction_method,
            "page_count": len(pages),
            "raw_text_length": len(text),
        },
        "contact_candidates": contact_candidates,
        "contacts": summarize_contacts_from_candidates(contact_candidates),
        "authority_candidates": _extract_authority_candidates(text),
        "reference_candidates": _extract_reference_candidates(text),
        "numeric_candidates": _extract_numeric_candidates(text),
        "financial_hints": _extract_financial_hints(text),
        "equipment_hints": _extract_equipment_hints(text),
        "party_mentions": _extract_party_mentions(text),
        "route_stop_hints": _extract_stop_hints(text),
    }


def _line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(offset, 0)) + 1


def _normalize_person_name_key(value: str) -> str:
    return " ".join((value or "").split()).strip().casefold()


def _extract_authority_candidates(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for kind, regex in (("mc", _MC_RE), ("dot", _DOT_RE)):
        for match in regex.finditer(text):
            value = match.group(1).strip()
            window = text[max(0, match.start() - 80) : match.end() + 80]
            out.append(
                {
                    "kind": kind,
                    "value": value,
                    "line": _line_number_for_offset(text, match.start()),
                    "context": " ".join(window.split())[:240],
                    "role_hint": _authority_role_hint(window),
                }
            )
    return out[:60]


def _authority_role_hint(window: str) -> str:
    w = window.casefold()
    if any(x in w for x in ("carrier mc", "carrier mc#", "carrier:", "carrier mc#:", "carrier dot")):
        return "carrier_context"
    if any(x in w for x in ("broker", "bill to", "remit", "customer")):
        return "broker_context"
    if any(x in w for x in ("carrier", "driver", "truck", "dispatcher")):
        return "carrier_context"
    return "unknown"


def _extract_reference_candidates(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    # Alphanumeric load / shipment ids (e.g. LZ123456) near load or rate confirmation wording.
    # Skip MC######## (carrier authority is handled elsewhere).
    for match in re.finditer(r"\b(?P<prefix>[A-Z]{2})(?P<value>\d{5,8})\b", text):
        prefix = match.group("prefix")
        if prefix == "MC":
            continue
        window = text[max(0, match.start() - 320) : match.end() + 120]
        if not re.search(
            r"\b(?:carrier\s+rate\s+confirmation|load\s+confirmation)\b",
            window,
            re.I,
        ):
            continue
        value = match.group("value").strip()
        key = ("load_number", value.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "kind": "load_number",
                "value": value,
                "line": _line_number_for_offset(text, match.start()),
                "label": f"{prefix}#",
                "context": " ".join(window.split())[:240],
            }
        )
    for match in re.finditer(r"\bLoad\s*#\s*(?P<value>[A-Z0-9][A-Z0-9._/-]{2,30})\b", text, re.IGNORECASE):
        value = match.group("value").strip(" .,:;")
        key = ("load_number", value.casefold())
        if key in seen:
            continue
        seen.add(key)
        window = text[max(0, match.start() - 80) : match.end() + 80]
        out.append(
            {
                "kind": "load_number",
                "value": value,
                "line": _line_number_for_offset(text, match.start()),
                "label": "Load #",
                "context": " ".join(window.split())[:240],
            }
        )
    for match in _REF_RE.finditer(text):
        label = _normalize_reference_label(match.group("label"))
        value = match.group("value").strip(" .,:;")
        if not value or len(value) < 3:
            continue
        key = (label, value.casefold())
        if key in seen:
            continue
        seen.add(key)
        window = text[max(0, match.start() - 80) : match.end() + 80]
        out.append(
            {
                "kind": label,
                "value": value,
                "line": _line_number_for_offset(text, match.start()),
                "context": " ".join(window.split())[:240],
            }
        )
    return out[:80]


def _normalize_reference_label(label: str) -> str:
    l = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    if l in {"p_o", "po"}:
        return "po_number"
    if l in {"b_o_l", "bol"}:
        return "bol_number"
    if l in {"ref", "reference"}:
        return "reference_number"
    if l in {"conf", "confirmation"}:
        return "confirmation_number"
    if l in {"load", "order"}:
        return f"{l}_number"
    if l in {"fb", "el"}:
        return f"{l}_number"
    return f"{l}_number" if not l.endswith("_number") else l


def _extract_numeric_candidates(text: str) -> dict[str, list[dict[str, Any]]]:
    return {
        "money": [
            {
                "value": m.group(0),
                "line": _line_number_for_offset(text, m.start()),
                "context": " ".join(text[max(0, m.start() - 80) : m.end() + 80].split())[:240],
            }
            for m in list(_MONEY_RE.finditer(text))[:40]
        ],
        "weights": [
            {"value": m.group(0), "line": _line_number_for_offset(text, m.start())}
            for m in list(_WEIGHT_RE.finditer(text))[:40]
        ],
    }


def _extract_financial_hints(text: str) -> dict[str, Any]:
    for match in re.finditer(
        r"\b(?:line\s*haul|linehaul|carrier\s+pay|rate|total)\b[^$\n]{0,50}\$\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
        text,
        re.IGNORECASE,
    ):
        window = text[max(0, match.start() - 80) : match.end() + 80]
        if any(term in window.casefold() for term in ("detention", "tonu", "layover", "cap")):
            continue
        amount_text = match.group("amount").replace(",", "")
        try:
            amount = float(amount_text)
        except ValueError:
            continue
        return {
            "linehaul_rate": amount,
            "line": _line_number_for_offset(text, match.start()),
            "context": " ".join(window.split())[:240],
        }
    return {}


def _extract_equipment_hints(text: str) -> dict[str, Any]:
    hints: dict[str, Any] = {}
    patterns = [
        r"\b(?P<size>48|53|20|40|45)\s*(?:ft|foot|feet|')?\s*(?P<type>dry\s*van|van|reefer|refrigerated|flatbed|step\s*deck)\b",
        r"\b(?P<type>dry\s*van|van|reefer|refrigerated|flatbed|step\s*deck)\s*(?P<size>48|53|20|40|45)\s*(?:ft|foot|feet|')?\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        typ = _normalize_trailer_type(m.group("type"))
        size = m.group("size")
        hints["trailer_type"] = typ
        hints["trailer_size"] = size
        return hints
    return hints


def _normalize_trailer_type(value: str) -> str:
    v = re.sub(r"\s+", " ", value.strip()).casefold()
    if v in {"dry van", "van"}:
        return "Van"
    if v in {"reefer", "refrigerated"}:
        return "Reefer"
    if v == "flatbed":
        return "Flatbed"
    if v == "step deck":
        return "Step Deck"
    return value.strip()


def _extract_party_mentions(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _COMPANY_LINE_RE.finditer(text):
        name = " ".join(match.group("name").split()).strip(" .,:;-")
        if len(name) < 3:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        label = match.group(0).split(":", 1)[0].split()[0].casefold()
        out.append(
            {
                "name": name[:120],
                "label": label,
                "line": _line_number_for_offset(text, match.start()),
                "is_stop_level": any(x in label for x in ("shipper", "consignee")),
            }
        )
    return out[:80]


def _extract_stop_detail_pu_del_hints(text: str) -> list[dict[str, Any]]:
    """Detect STOP DETAIL-style rows: label + MM/DD/YY on one line, time on the next line."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hints: list[dict[str, Any]] = []
    stop_detail_row = re.compile(
        r"^(?P<kind>PU|PICKUP|DEL|DELIVERY|SO|DROP)\s+(?P<mdy>\d{1,2}/\d{1,2}/\d{2,4})\b",
        re.IGNORECASE,
    )
    time_line = re.compile(
        r"^(?P<t>\d{1,2}:\d{2}(?::\d{2})?)(?:\s*(?P<ap>AM|PM))?\s*$",
        re.IGNORECASE,
    )
    seq = -1
    i = 0
    while i < len(lines):
        m = stop_detail_row.match(lines[i])
        if m:
            seq += 1
            iso = _mdy_slash_to_iso(m.group("mdy"))
            appt_time: str | None = None
            if i + 1 < len(lines):
                tm = time_line.match(lines[i + 1])
                if tm:
                    appt_time = tm.group("t").strip()
                    if tm.group("ap"):
                        appt_time = f"{appt_time} {tm.group('ap')}".strip()
                    i += 1
            hint: dict[str, Any] = {
                "sequence": seq,
                "stop_type": _stop_detail_label_to_type(m.group("kind")),
            }
            if iso:
                hint["appointment_date"] = iso
            if appt_time:
                hint["appointment_time_text"] = appt_time
            hints.append(hint)
        i += 1
    return hints


def _mdy_slash_to_iso(mdy: str) -> str | None:
    parts = mdy.strip().split("/")
    if len(parts) != 3:
        return None
    try:
        month, day, year = (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None
    if year < 100:
        year += 2000 if year < 70 else 1900
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _stop_detail_label_to_type(label: str) -> str:
    k = label.strip().casefold()
    if k in {"pu", "pickup"}:
        return "pickup"
    if k == "drop":
        return "drop"
    # DEL DELIVERY SO (stop-off)
    return "delivery"


def _merge_route_stop_hints_by_sequence(hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_seq: dict[int, dict[str, Any]] = {}
    for h in hints:
        if not isinstance(h, dict) or not isinstance(h.get("sequence"), int):
            continue
        seq = int(h["sequence"])
        if seq not in by_seq:
            by_seq[seq] = dict(h)
            continue
        base = by_seq[seq]
        for k, val in h.items():
            if k == "sequence":
                continue
            if val is None or val == "":
                continue
            if not base.get(k):
                base[k] = val
    return [by_seq[s] for s in sorted(by_seq.keys())]


def _extract_stop_hints(text: str) -> list[dict[str, Any]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hints: list[dict[str, Any]] = []
    stop_re = re.compile(
        r"^Stop\s+(?P<sequence>\d+)\s+(?P<type>PICKUP|DELIVERY|DROP)\s+"
        r"(?P<city>[^,]+),\s*(?P<state>[A-Z]{2})"
        r"(?:\s+(?P<postal>[A-Z0-9][A-Z0-9 -]{2,10}?))?"
        r"(?:\s+Ref:\s*(?P<ref>[A-Z0-9._/-]+))?$",
        re.IGNORECASE,
    )
    detail_re = re.compile(
        r"^(?P<facility>[^-]+?)\s+-\s+(?P<street>[^-]+?)\s+-\s+"
        r"(?P<date>\d{4}-\d{2}-\d{2})(?:\s+(?P<time>.+))?$",
        re.IGNORECASE,
    )
    for idx, line in enumerate(lines):
        m = stop_re.match(line)
        if not m:
            continue
        detail = detail_re.match(lines[idx + 1]) if idx + 1 < len(lines) else None
        hint = {
            "sequence": int(m.group("sequence")) - 1,
            "stop_type": _normalize_stop_type(m.group("type")),
            "city": m.group("city").strip(),
            "state_or_province": m.group("state").strip(),
            "postal_code": (m.group("postal") or "").strip() or None,
            "reference_number": (m.group("ref") or "").strip() or None,
        }
        if detail:
            hint.update(
                {
                    "facility_name": detail.group("facility").strip(),
                    "street": detail.group("street").strip(),
                    "appointment_date": detail.group("date").strip(),
                    "appointment_time_text": (detail.group("time") or "").strip() or None,
                }
            )
        hints.append(hint)

    hints.extend(_extract_stop_detail_pu_del_hints(text))
    return _merge_route_stop_hints_by_sequence(hints)[:80]


def _normalize_stop_type(value: str) -> str:
    v = value.strip().casefold()
    if v == "pickup":
        return "pickup"
    if v == "drop":
        return "drop"
    return "delivery"
