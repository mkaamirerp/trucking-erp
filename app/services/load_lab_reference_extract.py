"""Load Lab — structured reference extraction from normalized PDF text (pre-OCR).

Populates parse_diagnostics reference resolution fields and supplies DTO-shaped
references to merge into extracted.references + broker_load_reference when the
model leaves them sparse (common on carrier rate confirms, e.g. JB Hunt layouts).
"""

from __future__ import annotations

import re
from typing import Any

# Labels often used on carrier / broker rate confirms (JB Hunt–style and peers).
_SUPPLEMENTAL_LINE_RES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?i)\b(?P<label>Shipment\s*(?:ID|#)?|Trip\s*ID|Dispatch(?:\s*#|\s*ID)?|"
            r"Movement\s*#|Customer\s*Ref(?:erence)?|Cust\.?\s*Ref|Carrier\s*Ref)\s*[:#]?\s*"
            r"(?P<value>[A-Z0-9][A-Z0-9\-_/]{2,36})\b"
        ),
        "shipment_context",
    ),
    (
        re.compile(
            r"(?i)\b(?P<label>Tracking\s*#?|Trace\s*#?|Trailer\s*#?)\s*[:#]?\s*"
            r"(?P<value>[A-Z0-9][A-Z0-9\-_/]{2,24})\b"
        ),
        "tracking_context",
    ),
    (
        re.compile(
            r"(?i)\b(?P<label>Invoice\s*#|Inv\.?\s*#|Audit\s*ID)\s*[:#]?\s*"
            r"(?P<value>[A-Z0-9][A-Z0-9\-_/]{2,30})\b"
        ),
        "invoice_context",
    ),
    (
        re.compile(
            r"(?i)\b(?P<label>Broker\s*Load\s*#?|Bkr\.?\s*Ref|Booking\s*#)\s*[:#]?\s*"
            r"(?P<value>[A-Z0-9][A-Z0-9\-_/]{2,30})\b"
        ),
        "broker_load_context",
    ),
    (
        re.compile(
            r"(?i)\b(?P<label>Appt\.?\s*#|Appointment\s*#)\s*[:#]?\s*"
            r"(?P<value>[A-Z0-9][A-Z0-9\-]{2,20})\b"
        ),
        "appointment_context",
    ),
    # SCAC + PRO style (PRO often 9–10 digits)
    (
        re.compile(
            r"(?i)\b(?P<label>PRO)\s*[:#]?\s*(?P<value>\d{6,12}|[A-Z]{2,4}\d{6,12})\b"
        ),
        "pro_context",
    ),
]

_PHONE_LIKE = re.compile(r"^[\d\s().\-]{10,14}$")
_ZIP_US = re.compile(r"^\d{5}(?:-\d{4})?$")
_DATE_LIKE = re.compile(r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$")
_TIME_LIKE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
_MONEY_WINDOW = re.compile(r"\$\s*[\d,]+(?:\.\d{1,2})?")
_MC_LINE = re.compile(r"\bMC[\s#:-]*\d{4,10}\b", re.I)
_DOT_LINE = re.compile(r"\b(?:USDOT|DOT)[\s#:-]*\d{4,10}\b", re.I)
_WEIGHT_CTX = re.compile(r"\b(lbs?|pounds?|kgs?|weight|wgt|net\s*wt)\b", re.I)
_MILES_CTX = re.compile(r"\b(miles?|distance)\b", re.I)


def _line_zone(line_index: int, total_lines: int) -> str:
    if total_lines <= 0:
        return "unknown"
    if line_index < 18:
        return "header_title_zone"
    if total_lines - line_index <= 18:
        return "footer_legal_zone"
    return "body_zone"


def _looks_like_decimal_number(s: str) -> bool:
    try:
        s2 = (s or "").strip()
        if not s2 or s2.count(".") != 1:
            return False
        left, right = s2.split(".", 1)
        return right.isdigit() and len(right) in (1, 2) and any(c.isdigit() for c in left)
    except Exception:
        return False


def _reject_candidate(
    *,
    value: str,
    line_text: str,
    label: str,
) -> str | None:
    v = (value or "").strip()
    if not v:
        return "empty_value"
    if len(v) > 80:
        return "value_too_long"
    if _looks_like_decimal_number(v):
        return "money_like_decimal"
    if _DATE_LIKE.match(v):
        return "date_like"
    if _TIME_LIKE.match(v) and len(v) <= 8:
        return "time_like"
    if _ZIP_US.match(v) and re.search(r"\b(zip|postal|post\s*code)\b", line_text, re.I):
        return "postal_code_in_zip_context"
    if _PHONE_LIKE.match(v) and sum(c.isdigit() for c in v) >= 10:
        return "phone_like"
    low = line_text.casefold()
    if _MONEY_WINDOW.search(line_text) and v.replace(",", "").replace(".", "").isdigit():
        if any(x in low for x in ("rate", "total", "amount", "pay", "charge", "usd", "$")):
            return "money_amount_context"
    if _WEIGHT_CTX.search(line_text) and re.fullmatch(r"[\d,]+", v.replace(",", "")):
        return "weight_quantity_like"
    if _MILES_CTX.search(line_text) and v.replace(",", "").isdigit() and len(v) <= 5:
        return "miles_like"
    if _MC_LINE.search(line_text) or _DOT_LINE.search(line_text):
        if v.isdigit() and 4 <= len(v) <= 10 and "mc" not in label.casefold() and "dot" not in label.casefold():
            if re.search(r"\b(mc|usdot|dot)\b", low):
                return "mc_dot_authority_line_context"
    return None


def _internal_kind_from_label(label: str, ctx: str) -> str:
    s = (label or "").strip().casefold()
    # Prefer explicit label text (one supplemental regex groups Shipment|Trip|Dispatch).
    if "trip" in s:
        return "trip_id"
    if "dispatch" in s or "movement" in s:
        return "dispatch_number"
    if "shipment" in s:
        return "shipment_number"
    if "customer" in s or "cust" in s or "carrier ref" in s:
        return "customer_reference"
    if "tracking" in s or "trace" in s:
        return "tracking_number"
    if "trailer" in s:
        return "trailer_number"
    if "invoice" in s or "inv" in s:
        return "invoice_number"
    if "audit" in s:
        return "audit_id"
    if "appt" in s or "appointment" in s:
        return "appointment_number"
    if "broker" in s or "booking" in s or "bkr" in s:
        return "broker_load_number"
    if s == "pro" or "pro" in s:
        return "pro_number"
    return "reference"


def _to_dto_kind(internal: str, label: str) -> str:
    """Map to workspace parse kind (max 32 chars)."""
    m = {
        "el_number": "el_number",
        "freight_bill_number": "freight_bill_number",
        "po_number": "po_number",
        "pickup_number": "pickup_number",
        "delivery_number": "delivery_number",
        "bol_number": "bol_number",
        "pro_number": "pro_number",
        "order_number": "order_number",
        "load_number": "load_number",
        "order_token": "secondary_tracking_id",
        "shipment_number": "shipment_number",
        "trip_id": "secondary_tracking_id",
        "dispatch_number": "broker_load_number",
        "customer_reference": "unknown_reference",
        "tracking_number": "secondary_tracking_id",
        "trailer_number": "unknown_reference",
        "invoice_number": "invoice_number",
        "audit_id": "audit_id",
        "appointment_number": "appointment_number",
        "broker_load_number": "broker_load_number",
        "reference": "unknown_reference",
    }
    out = m.get(internal) or "unknown_reference"
    if len(out) > 32:
        return out[:32]
    return out


_ACCOUNTING_PRIMARY_BLOCKLIST = frozenset(
    {
        "freight_bill_number",
        "invoice_number",
        "audit_id",
        "unknown_reference",
    }
)


def _reference_confidence(dto_kind: str, *, label: str, line_text: str) -> str:
    """
    Confidence is about *primary suitability* for load identity.
    Accounting refs are intentionally low unless explicitly framed as load/order/reference.
    """
    k = (dto_kind or "").strip()
    lab = (label or "").casefold()
    ln = (line_text or "").casefold()
    has_load_order = bool(re.search(r"\b(load|order|reference|ref\s*#)\b", lab + " " + ln, re.I))
    has_broker_specific = bool(re.search(r"\b(broker\s*load|booking)\b", lab + " " + ln, re.I))

    if k in ("broker_load_number", "load_number", "order_number"):
        return "high"
    if k in ("shipment_number", "broker_load_number", "pro_number", "bol_number"):
        return "medium"
    if k in _ACCOUNTING_PRIMARY_BLOCKLIST:
        return "medium" if (has_broker_specific or has_load_order) else "low"
    if k in ("po_number", "pickup_number", "delivery_number", "appointment_number", "secondary_tracking_id"):
        return "medium"
    return "low"


def _primary_allowed(dto_kind: str, *, label: str, line_text: str) -> bool:
    k = (dto_kind or "").strip()
    lab = (label or "").casefold()
    ln = (line_text or "").casefold()
    has_load_order = bool(re.search(r"\b(load|order|reference|ref\s*#)\b", lab + " " + ln, re.I))
    has_broker_specific = bool(re.search(r"\b(broker\s*load|booking)\b", lab + " " + ln, re.I))

    if k in _ACCOUNTING_PRIMARY_BLOCKLIST:
        # Block by default; only allow with explicit load/order/reference framing.
        return bool(has_broker_specific or has_load_order)
    return True


def _candidate_key(c: dict[str, Any]) -> tuple[Any, ...]:
    return (
        c.get("page"),
        c.get("line_index"),
        str(c.get("value") or "").strip().casefold(),
        str(c.get("kind") or "").casefold(),
    )


def supplemental_reference_candidates(
    page_texts: list[str] | None,
    raw_full_text: str,
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen = {_candidate_key(c) for c in existing if isinstance(c, dict)}
    out: list[dict[str, Any]] = []
    pages = page_texts if page_texts else ([raw_full_text] if raw_full_text else [])
    for p, txt in enumerate(pages, start=1):
        if not txt:
            continue
        lines = txt.splitlines()
        for i, ln in enumerate(lines):
            ln_s = (ln or "").strip()
            if not ln_s:
                continue
            for rx, ctx in _SUPPLEMENTAL_LINE_RES:
                for m in rx.finditer(ln_s):
                    label = (m.groupdict().get("label") or "").strip()
                    value = (m.groupdict().get("value") or "").strip()
                    if not value:
                        continue
                    ik = _internal_kind_from_label(label, ctx)
                    rec = {
                        "page": p,
                        "line_index": i,
                        "zone": _line_zone(i, len(lines)),
                        "label": label or ctx,
                        "kind": ik,
                        "value": value,
                        "line_text": ln_s[:240],
                        "source": "supplemental_regex",
                    }
                    k = _candidate_key(rec)
                    if k in seen:
                        continue
                    seen.add(k)
                    out.append(rec)
    return out[:400]


def resolve_reference_candidates(
    *,
    raw_full_text: str,
    reference_candidates: list[dict[str, Any]],
    numeric_candidates: list[dict[str, Any]] | None,
    filename: str | None = None,
) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for c in reference_candidates:
        if not isinstance(c, dict):
            continue
        value = str(c.get("value") or "").strip()
        line_text = str(c.get("line_text") or "")
        label = str(c.get("label") or "")
        internal = str(c.get("kind") or "reference")
        rr = _reject_candidate(value=value, line_text=line_text, label=label)
        if rr:
            rejected.append(
                {
                    "page": c.get("page"),
                    "line_index": c.get("line_index"),
                    "label": label,
                    "kind": internal,
                    "value": value,
                    "line_text": line_text[:200],
                    "rejection_reason": rr,
                }
            )
            continue
        dto_kind = _to_dto_kind(internal, label)
        conf = _reference_confidence(dto_kind, label=label, line_text=line_text)
        primary_ok = conf in ("high", "medium") and _primary_allowed(dto_kind, label=label, line_text=line_text)
        accepted.append(
            {
                "page": c.get("page"),
                "line_index": c.get("line_index"),
                "zone": c.get("zone"),
                "label": label,
                "internal_kind": internal,
                "dto_kind": dto_kind,
                "value": value[:120],
                "line_text": line_text[:200],
                "confidence": conf,
                "primary_candidate": bool(primary_ok),
            }
        )

    # De-dupe accepted by (dto_kind, value_cf)
    deduped: list[dict[str, Any]] = []
    seen_acc: set[tuple[str, str]] = set()
    for a in accepted:
        key = (str(a.get("dto_kind")), str(a.get("value") or "").strip().casefold())
        if key in seen_acc or not key[1]:
            continue
        seen_acc.add(key)
        deduped.append(a)

    def _score(a: dict[str, Any]) -> int:
        s = 0
        dto = str(a.get("dto_kind") or "")
        zone = str(a.get("zone") or "")
        if zone == "header_title_zone":
            s += 4
        order_pref = [
            "broker_load_number",
            "shipment_number",
            "load_number",
            "order_number",
            "el_number",
            "bol_number",
            "pro_number",
            "po_number",
            "pickup_number",
            "delivery_number",
            "invoice_number",
            "appointment_number",
            "audit_id",
            "secondary_tracking_id",
        ]
        if dto in order_pref:
            s += (len(order_pref) - order_pref.index(dto)) * 3
        val = str(a.get("value") or "")
        if any(ch.isalpha() for ch in val) and any(ch.isdigit() for ch in val):
            s += 2
        if val.isdigit() and len(val) >= 5:
            s += 1
        return s

    deduped.sort(key=_score, reverse=True)
    primary = next((d for d in deduped if d.get("primary_candidate") is True), None)
    primary_val = (primary.get("value") if isinstance(primary, dict) else None) or None
    if primary:
        primary_reason = (
            f"selected_primary dto_kind={primary.get('dto_kind')!r} value={primary.get('value')!r} "
            f"confidence={primary.get('confidence')!r} score={_score(primary)} label={primary.get('label')!r}"
        )
    else:
        primary_reason = (
            "No high-confidence broker load/order reference found; "
            "accounting references (e.g. Freight Bill / Invoice / Audit) kept as secondary references only."
        )

    ref_like = 0
    if isinstance(numeric_candidates, list):
        ref_like = sum(1 for x in numeric_candidates if isinstance(x, dict) and x.get("kind_hint") == "reference_like")

    gap = ""
    if not deduped and ref_like:
        gap = (
            "numeric_candidates_include_reference_like_tokens_but_structured_reference_candidates "
            "either_empty_or_all_rejected_carrier_layouts_e_g_JB_Hunt_often_use_shipment_trip_dispatch "
            "labels_supplemental_regex_should_capture_next_pass"
        )
    elif not deduped and reference_candidates and rejected:
        gap = "all_raw_reference_candidates_rejected_see_rejected_reference_candidates"
    elif not deduped and not reference_candidates:
        gap = (
            "no_reference_candidates_from_label_regexes_text_may_use_non_standard_labels_or_table_only_layout"
        )
    elif deduped:
        gap = f"accepted_count={len(deduped)} rejected_count={len(rejected)}"

    fn = (filename or "").replace(" ", "").casefold()
    if "jbhunt" in fn and not deduped:
        gap += (
            ";jb_hunt_rate_confirms_often_label_shipment_trip_or_dispatch_ids_instead_of_el_freight_bill_po "
            "legacy_regex_only_matched_standard_labels_pre_supplemental_pass"
        )

    dto_refs = [
        {
            "kind": str(a.get("dto_kind")),
            "label": (str(a.get("label") or "")[:80] or None),
            "value": str(a.get("value"))[:120],
            "primary_candidate": bool(a.get("primary_candidate") is True),
            "confidence": str(a.get("confidence") or "") or None,
        }
        for a in deduped[:12]
    ]

    return {
        "accepted_references": deduped[:25],
        "rejected_reference_candidates": rejected[:200],
        "primary_reference_selection_reason": primary_reason,
        "reference_extraction_gap_analysis": gap,
        "references_dto_merge": dto_refs,
        "primary_broker_load_reference_merge": primary_val if primary else None,
    }


def augment_diagnostic_reference_resolution(
    diag: dict[str, Any],
    raw_full_text: str,
    page_texts: list[str] | None,
    filename: str | None = None,
) -> dict[str, Any] | None:
    """Mutates diag: extends reference_candidates, adds acceptance tables. Returns merge pack for extracted (not on diag)."""
    if not isinstance(diag, dict):
        return None
    raw = raw_full_text or ""
    base = diag.get("reference_candidates")
    if not isinstance(base, list):
        base = []
    extra = supplemental_reference_candidates(page_texts, raw, base)
    combined = base + extra
    diag["reference_candidates"] = combined[:600]

    nums = diag.get("numeric_candidates") if isinstance(diag.get("numeric_candidates"), list) else []
    res = resolve_reference_candidates(
        raw_full_text=raw,
        reference_candidates=combined,
        numeric_candidates=nums,
        filename=filename,
    )
    diag["accepted_references"] = res["accepted_references"]
    diag["rejected_reference_candidates"] = res["rejected_reference_candidates"]
    diag["primary_reference_selection_reason"] = res["primary_reference_selection_reason"]
    diag["reference_extraction_gap_analysis"] = res["reference_extraction_gap_analysis"]
    return {
        "references_dto_merge": res["references_dto_merge"],
        "primary_broker_load_reference_merge": res["primary_broker_load_reference_merge"],
    }


def merge_structured_references_into_extracted_dict(
    extracted: dict[str, Any],
    merge_pack: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge deterministic DTO references + primary broker_load_reference when model left gaps."""
    if not isinstance(extracted, dict) or not isinstance(merge_pack, dict):
        return extracted
    dto_list = merge_pack.get("references_dto_merge")
    if not isinstance(dto_list, list) or not dto_list:
        return extracted
    cur = extracted.get("references")
    if not isinstance(cur, list):
        cur = []
    seen: set[tuple[str, str]] = set()
    for r in cur:
        if not isinstance(r, dict):
            continue
        k = str(r.get("kind") or "").strip()[:32]
        v = str(r.get("value") or "").strip()[:120]
        if k and v:
            seen.add((k.casefold(), v.casefold()))
    for item in dto_list:
        if not isinstance(item, dict):
            continue
        k = str(item.get("kind") or "").strip()[:32]
        label = str(item.get("label") or "").strip()[:80] if isinstance(item.get("label"), str) else ""
        v = str(item.get("value") or "").strip()[:120]
        if not k or not v:
            continue
        key = (k.casefold(), v.casefold())
        if key in seen:
            continue
        cur.append(
            {
                "kind": k,
                "value": v,
                "label": (label or None),
                "primary_candidate": bool(item.get("primary_candidate") is True),
                "confidence": (str(item.get("confidence") or "").strip() or None),
            }
        )
        seen.add(key)
        if len(cur) >= 14:
            break
    extracted["references"] = cur
    prim = merge_pack.get("primary_broker_load_reference_merge")
    if isinstance(prim, str) and prim.strip():
        cur_ref = (extracted.get("broker_load_reference") or "").strip()
        if not cur_ref:
            extracted["broker_load_reference"] = prim.strip()[:120]
    return extracted
