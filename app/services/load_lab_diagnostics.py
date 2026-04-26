"""Load Lab diagnostics (Phase 1).

Goal: produce lightweight evidence structures for evaluation and later gating:
- document zones
- party mentions
- numeric candidates
- stop-block candidates

This module must not be required by workspace hydration; it is lab-only.
"""

from __future__ import annotations

import re
from typing import Any


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\b(\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4})\b")
_MONEY_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")
_WEIGHT_RE = re.compile(r"\b(?:Wgt|Weight|WT)\b[^\n]{0,40}\b([\d,]{2,})\b", re.I)
_MILES_RE = re.compile(r"\b([\d,]{2,5})\s*(?:loaded\s*)?miles?\b", re.I)
_REF_LABEL_RE = re.compile(r"\b(?:Load|Order|Ref(?:erence)?|PO|BOL|PRO|Freight\s*Bill|EL)\b", re.I)
_MC_RE = re.compile(r"\bMC[\s#:-]*(\d{4,10})\b", re.I)
_DOT_RE = re.compile(r"\b(?:USDOT|DOT)[\s#:-]*(\d{4,10})\b", re.I)

_REF_LINE_RE = re.compile(
    # Require the value to contain at least one digit to avoid false positives like "Load Tender".
    r"\b(?P<label>EL\s*#?|Freight\s*Bill\s*#?|Bill\s*#?|BOL\s*#?|PRO\s*#?|PO\s*#?|Pickup\s*#?|Delivery\s*#?|Load\s*#?|Order\s*#?|Reference\s*#?)\s*[:\-]?\s*(?P<value>[A-Z0-9][A-Z0-9\-_/]{0,39}\d[A-Z0-9\-_/]{0,39})\b",
    re.I,
)

_ORDER_LOAD_TOKEN_RE = re.compile(r"\b([A-Z]{1,4}\d{5,12})\b")
_LZ_TOKEN_RE = re.compile(r"\bLZ\d{4,10}\b", re.I)

_LABELLED_PARTY_RE = re.compile(
    r"^\s*(Broker|Carrier|Customer|Bill To|Customs\s*Broker|Shipper|Consignee)\s*[:\-]\s*(.{3,120})\s*$",
    re.I,
)

# Legal-entity tokens only (do not require logistics/transport/etc. as "suffix").
_LEGAL_ENTITY_SUFFIX_RE = re.compile(
    r"\b(inc\.?|llc|ltd\.?|limited|corp\.?|corporation)\b",
    re.I,
)
# Meaningful business-identity words stay in company names (not stripped as disposable).
_BUSINESS_IDENTITY_TOKEN_RE = re.compile(
    r"\b(logistics|transport(?:ation)?|freight|brokerage|supply\s*chain|group)\b",
    re.I,
)


def _looks_like_header_org_candidate(cand: str) -> bool:
    """Header/corporate line looks like an operating company name (legal suffix OR sector word OR long title)."""
    if not cand:
        return False
    return bool(
        _LEGAL_ENTITY_SUFFIX_RE.search(cand)
        or _BUSINESS_IDENTITY_TOKEN_RE.search(cand)
        or len(cand) > 28
    )

_HEADER_SKIP_PREFIX_RE = re.compile(r"^\s*(broker|carrier|customer|bill to|customs\s*broker|shipper|consignee)\s*[:\-]\s*", re.I)
_HEADER_BRAND_TOKEN_RE = re.compile(r"\b([A-Z]{2,6})\b")


def _sanitize_text(s: str) -> str:
    # PostgreSQL JSON/text cannot store NUL; strip it early.
    return (s or "").replace("\x00", "")


def build_parse_diagnostics(
    *,
    raw_full_text: str,
    page_texts: list[str] | None,
    filename: str,
    extraction_method: str,
    extraction_path: str | None,
) -> dict[str, Any]:
    raw_full_text = _sanitize_text(raw_full_text)
    pages = [_sanitize_text(x) for x in (page_texts or [])]
    if not pages:
        # Some early runs stored only parse_response.raw_text (no normalized_package.page_texts).
        # Fall back to a single pseudo-page so diagnostics still work.
        pages = [raw_full_text]

    zones = _zones_from_pages(pages)
    stop_blocks = _stop_block_candidates(pages)
    party_mentions = _party_mentions_from_pages(pages, stop_blocks=stop_blocks)
    numeric_candidates = _numeric_candidates_from_pages(pages)
    reference_candidates = _reference_candidates_from_pages(pages)
    authority_candidates = _authority_candidates(pages)

    return {
        "version": "parse_diagnostics_v1",
        "source": {
            "filename": filename,
            "extraction_method": extraction_method,
            "extraction_path": extraction_path,
            "page_count": len(pages),
        },
        "document_zones": zones,
        "party_mentions": party_mentions,
        "authority_candidates": authority_candidates,
        "numeric_candidates": numeric_candidates,
        "reference_candidates": reference_candidates,
        "stop_block_candidates": stop_blocks,
        "notes": [
            "Phase 1 heuristics: approximate zoning only (no pixel/OCR layout).",
        ],
    }


def _zones_from_pages(page_texts: list[str]) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    for p, txt in enumerate(page_texts, start=1):
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        if not lines:
            continue
        head = "\n".join(lines[:18])
        foot = "\n".join(lines[-18:])
        zones.append({"page": p, "zone": "header_title_zone", "text": head[:2000]})
        zones.append({"page": p, "zone": "footer_legal_zone", "text": foot[:2000]})
        # crude middle-zone buckets for later: identity/contact/payment/refs/route
        body = "\n".join(lines[18:-18]) if len(lines) > 40 else "\n".join(lines)
        zones.append({"page": p, "zone": "body_zone", "text": body[:4000]})
    return zones


def _line_zone(line_index: int, total_lines: int) -> str:
    if total_lines <= 0:
        return "unknown"
    if line_index < 18:
        return "header_title_zone"
    if total_lines - line_index <= 18:
        return "footer_legal_zone"
    return "body_zone"


def _party_mentions_from_pages(page_texts: list[str], *, stop_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mentions: dict[str, dict[str, Any]] = {}
    stop_blob = "\n\n".join([b.get("block_text", "") for b in stop_blocks if isinstance(b.get("block_text"), str)])

    for p, txt in enumerate(page_texts, start=1):
        lines = txt.splitlines()

        # labeled party lines (Broker:, Carrier:, Customs Broker:, etc.)
        for i, ln in enumerate(lines):
            m = _LABELLED_PARTY_RE.match(ln)
            if not m:
                continue
            label = (m.group(1) or "").strip()
            name = (m.group(2) or "").strip()
            if len(name) < 3:
                continue
            key = f"name:{name.casefold()}"
            rec = mentions.setdefault(
                key,
                {
                    "name": name,
                    "phones": [],
                    "emails": [],
                    "domains": [],
                    "pages": [],
                    "zones": [],
                    "nearby_labels": [],
                    "surrounding_text": "",
                    "mention_count": 0,
                    "is_header_level": False,
                    "is_document_identity_level": False,
                    "is_stop_level": False,
                    "is_contact_block": False,
                    "is_signature_block": False,
                },
            )
            zone = _line_zone(i, len(lines))
            rec["pages"] = sorted(set(rec["pages"] + [p]))
            rec["zones"] = sorted(set(rec["zones"] + [zone]))
            rec["nearby_labels"] = sorted(set(rec["nearby_labels"] + [label]))
            rec["mention_count"] += 1
            if zone == "header_title_zone":
                # Header placement alone is NOT document identity; it's just a location hint.
                rec["is_header_level"] = True

        # org-ish candidates from header (top lines)
        for idx, ln in enumerate(lines[:20]):
            cand = ln.strip()
            if len(cand) < 4 or len(cand) > 90:
                continue
            # Avoid accidentally treating labeled parties like "Broker: X" as identity/branding.
            if _HEADER_SKIP_PREFIX_RE.match(cand):
                continue
            # Avoid treating carrier legal name blocks as document identity (Armstrong-style RCs).
            if " dba " in cand.casefold() or cand.casefold().startswith("dba "):
                continue
            if re.match(r"^\d{4,}\b", cand):
                # Leading long numeric tokens are almost always carrier ids / internal ids, not broker identity.
                continue
            # Avoid treating carrier/driver blocks as document identity even if they contain org-ish words like "Logistics".
            prev_ctx = " ".join([x.strip().casefold() for x in lines[max(0, idx - 4) : idx]])
            if any(k in prev_ctx for k in ("carrier contact", "carrier:", "driver", "dispatcher")) and "logistics" in cand.casefold():
                continue

            # Brand token shortcut: "… INFORMATION SHEET TQL …" should emit TQL as identity.
            if "information sheet" in cand.casefold() or "load confirmation" in cand.casefold():
                toks = [m.group(1) for m in _HEADER_BRAND_TOKEN_RE.finditer(cand)]
                toks = [t for t in toks if 2 <= len(t) <= 6 and t not in ("PAGE", "LOAD", "INFO", "SHEET", "PO", "PICKUP", "DELIVERY")]
                # pick the last token (often the brand)
                if toks:
                    brand = toks[-1]
                    keyb = f"name:{brand.casefold()}"
                    recb = mentions.setdefault(
                        keyb,
                        {
                            "name": brand,
                            "phones": [],
                            "emails": [],
                            "domains": [],
                            "pages": [],
                            "zones": [],
                            "nearby_labels": [],
                            "surrounding_text": "",
                            "mention_count": 0,
                            "is_header_level": False,
                            "is_document_identity_level": True,
                            "is_stop_level": False,
                            "is_contact_block": False,
                            "is_signature_block": False,
                        },
                    )
                    recb["pages"] = sorted(set(recb["pages"] + [p]))
                    recb["zones"] = sorted(set(recb["zones"] + ["header_title_zone"]))
                    recb["mention_count"] += 1
                    recb["is_header_level"] = True
                    recb["is_document_identity_level"] = True

            if not _looks_like_header_org_candidate(cand):
                continue
            if any(x in cand.lower() for x in ("rate", "confirmation", "tender", "pickup", "delivery")):
                continue
            key = f"name:{cand.casefold()}"
            rec = mentions.setdefault(
                key,
                {
                    "name": cand,
                    "phones": [],
                    "emails": [],
                    "domains": [],
                    "pages": [],
                    "zones": [],
                    "nearby_labels": [],
                    "surrounding_text": "",
                    "mention_count": 0,
                    "is_header_level": False,
                    "is_document_identity_level": True,
                    "is_stop_level": False,
                    "is_contact_block": False,
                    "is_signature_block": False,
                },
            )
            rec["pages"] = sorted(set(rec["pages"] + [p]))
            rec["zones"] = sorted(set(rec["zones"] + ["header_title_zone"]))
            rec["mention_count"] += 1
            rec["is_header_level"] = True
            rec["is_document_identity_level"] = True

        # Corporate info identity candidates (not necessarily in top header lines)
        corp_idx = None
        for j, ln in enumerate(lines):
            if "corporate information" in (ln or "").casefold():
                corp_idx = j
                break
        if corp_idx is not None:
            for ln in lines[corp_idx : min(len(lines), corp_idx + 14)]:
                cand = (ln or "").strip()
                if len(cand) < 4 or len(cand) > 90:
                    continue
                if _HEADER_SKIP_PREFIX_RE.match(cand):
                    continue
                if " dba " in cand.casefold():
                    continue
                # allow org-ish names like "Armstrong Transport Group" without forcing legal suffix
                if not _looks_like_header_org_candidate(cand):
                    continue
                key = f"name:{cand.casefold()}"
                rec = mentions.setdefault(
                    key,
                    {
                        "name": cand,
                        "phones": [],
                        "emails": [],
                        "domains": [],
                        "pages": [],
                        "zones": [],
                        "nearby_labels": [],
                        "surrounding_text": "",
                        "mention_count": 0,
                        "is_header_level": False,
                        "is_document_identity_level": True,
                        "is_stop_level": False,
                        "is_contact_block": False,
                        "is_signature_block": False,
                    },
                )
                rec["pages"] = sorted(set(rec["pages"] + [p]))
                rec["zones"] = sorted(set(rec["zones"] + ["body_zone"]))
                rec["mention_count"] += 1
                rec["is_document_identity_level"] = True

        # emails/domains
        for m in _EMAIL_RE.finditer(txt):
            email = m.group(0)
            dom = email.split("@")[-1].lower()
            key = f"email:{email.lower()}"
            rec = mentions.setdefault(
                key,
                {
                    "name": None,
                    "phones": [],
                    "emails": [],
                    "domains": [],
                    "pages": [],
                    "zones": [],
                    "nearby_labels": [],
                    "surrounding_text": "",
                    "mention_count": 0,
                    "is_header_level": False,
                    "is_stop_level": False,
                    "is_contact_block": True,
                    "is_signature_block": False,
                },
            )
            rec["emails"] = sorted(set(rec["emails"] + [email]))
            rec["domains"] = sorted(set(rec["domains"] + [dom]))
            rec["pages"] = sorted(set(rec["pages"] + [p]))
            rec["mention_count"] += 1
        # phones
        for m in _PHONE_RE.finditer(txt):
            ph = m.group(1)
            key = f"phone:{re.sub(r'\\D+', '', ph)}"
            rec = mentions.setdefault(
                key,
                {
                    "name": None,
                    "phones": [],
                    "emails": [],
                    "domains": [],
                    "pages": [],
                    "zones": [],
                    "nearby_labels": [],
                    "surrounding_text": "",
                    "mention_count": 0,
                    "is_header_level": False,
                    "is_stop_level": False,
                    "is_contact_block": True,
                    "is_signature_block": False,
                },
            )
            rec["phones"] = sorted(set(rec["phones"] + [ph]))
            rec["pages"] = sorted(set(rec["pages"] + [p]))
            rec["mention_count"] += 1

    # mark stop-level parties if they appear in stop blocks
    if stop_blob.strip():
        stop_lower = stop_blob.casefold()
        for rec in mentions.values():
            nm = (rec.get("name") or "").strip()
            if nm and nm.casefold() in stop_lower:
                rec["is_stop_level"] = True
    # return stable list
    return list(mentions.values())[:200]


def _numeric_candidates_from_pages(page_texts: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p, txt in enumerate(page_texts, start=1):
        for m in _MONEY_RE.finditer(txt):
            val = m.group(1)
            out.append({"page": p, "text": f"${val}", "kind_hint": "money_like"})
        for m in _WEIGHT_RE.finditer(txt):
            out.append({"page": p, "text": m.group(1), "kind_hint": "weight_like"})
        for m in _MILES_RE.finditer(txt):
            out.append({"page": p, "text": m.group(1), "kind_hint": "miles_like"})
        # labeled reference-ish tokens
        for m in re.finditer(r"\b([A-Z0-9][A-Z0-9\-]{3,24})\b", txt):
            token = m.group(1)
            if token.isdigit() and len(token) < 5:
                continue
            # keep only if near a label within 60 chars
            start = max(0, m.start() - 60)
            end = min(len(txt), m.end() + 60)
            window = txt[start:end]
            if _REF_LABEL_RE.search(window):
                out.append({"page": p, "text": token, "kind_hint": "reference_like", "nearby": window.strip()[:180]})
    return out[:500]


def _normalize_ref_kind(label: str) -> str:
    s = (label or "").strip().casefold()
    if s.startswith("el"):
        return "el_number"
    if "freight" in s or "bill" in s:
        return "freight_bill_number"
    if s.startswith("po"):
        return "po_number"
    if s.startswith("pickup"):
        return "pickup_number"
    if s.startswith("delivery"):
        return "delivery_number"
    if s.startswith("bol"):
        return "bol_number"
    if s.startswith("pro"):
        return "pro_number"
    if s.startswith("order"):
        return "order_number"
    if s.startswith("load"):
        return "load_number"
    return "reference"


def _reference_candidates_from_pages(page_texts: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p, txt in enumerate(page_texts, start=1):
        lines = txt.splitlines()
        # Track proximity to ORDER INFORMATION / Order # table headers.
        order_context_ttl = 0
        prev_lines: list[tuple[int, str]] = []  # (line_index, text)
        for i, ln in enumerate(lines):
            ln_s = (ln or "").strip()
            if re.search(r"\bORDER\s+INFORMATION\b", ln_s, re.I) or re.search(r"\bOrder\s*#\b", ln_s, re.I):
                order_context_ttl = 6
                # Also look slightly *above* the header: RXO often prints the order id just before the header block.
                for j, prior in prev_lines[-4:]:
                    pr = (prior or "").strip()
                    if not pr:
                        continue
                    if _LZ_TOKEN_RE.search(pr):
                        for m in _LZ_TOKEN_RE.finditer(pr):
                            tok = m.group(0).strip()
                            out.append(
                                {
                                    "page": p,
                                    "line_index": j,
                                    "zone": _line_zone(j, len(lines)),
                                    "label": "Order token (context_back)",
                                    "kind": "order_token",
                                    "value": tok,
                                    "line_text": pr[:240],
                                }
                            )
                    # Only treat as order_number if the line is basically an ID (digits only / leading digits)
                    m0 = re.match(r"^(\d{5,12})\s*$", pr)
                    if m0:
                        out.append(
                            {
                                "page": p,
                                "line_index": j,
                                "zone": _line_zone(j, len(lines)),
                                "label": "Order # (context_back)",
                                "kind": "order_number",
                                "value": m0.group(1),
                                "line_text": pr[:240],
                            }
                        )
            elif order_context_ttl > 0:
                order_context_ttl -= 1

            for m in _REF_LINE_RE.finditer(ln):
                label = (m.group("label") or "").strip()
                value = (m.group("value") or "").strip()
                if not value:
                    continue
                out.append(
                    {
                        "page": p,
                        "line_index": i,
                        "zone": _line_zone(i, len(lines)),
                        "label": label,
                        "kind": _normalize_ref_kind(label),
                        "value": value,
                        "line_text": ln.strip()[:240],
                    }
                )

            # Prefixed order/load tokens like LZ179967 (often appear as a secondary identifier)
            for m in _LZ_TOKEN_RE.finditer(ln_s):
                tok = m.group(0).strip()
                out.append(
                    {
                        "page": p,
                        "line_index": i,
                        "zone": _line_zone(i, len(lines)),
                        "label": "Order token",
                        "kind": "order_token",
                        "value": tok,
                        "line_text": ln_s[:240],
                    }
                )

            # If we're near an Order # header, capture nearby bare IDs too (e.g. 179967 on its own line).
            if order_context_ttl > 0:
                # Prefer leading order id on the line (RXO: "42180.00 ...", but decimals should be downranked later).
                mlead = re.match(r"^(\d{5,12})(?:\.(\d{1,2}))?\b", ln_s)
                if mlead:
                    out.append(
                        {
                            "page": p,
                            "line_index": i,
                            "zone": _line_zone(i, len(lines)),
                            "label": "Order # (context)",
                            "kind": "order_number",
                            "value": mlead.group(1),
                            "line_text": ln_s[:240],
                        }
                    )

            prev_lines.append((i, ln_s))
            if len(prev_lines) > 8:
                prev_lines = prev_lines[-8:]

    return out[:500]


def _stop_block_candidates(page_texts: list[str]) -> list[dict[str, Any]]:
    """Very coarse stop-block detection: looks for pickup/delivery keywords and captures nearby lines."""
    out: list[dict[str, Any]] = []
    kw = re.compile(r"\b(pick.?up|delivery|deliver to|shipper|consignee|origin|destination)\b", re.I)
    for p, txt in enumerate(page_texts, start=1):
        lines = txt.splitlines()
        for i, ln in enumerate(lines):
            if not kw.search(ln):
                continue
            block = "\n".join(lines[max(0, i - 3) : min(len(lines), i + 12)]).strip()
            if block:
                out.append({"page": p, "trigger_line": ln.strip()[:200], "block_text": block[:2000]})
    return out[:200]


# Authority line context: role labels + hint for broker vs carrier MC/DOT separation.
# Generic document/broker cues only (no tenant-specific brands or domains).
_AUTHORITY_BROKER_LABEL_RE = re.compile(
    r"\b(corporate\s*information|freight\s*broker|broker(?:age)?\s+agreement|"
    r"invoice\s*instructions|payment\s*status|quickpay|general\s*load\s*questions|"
    r"dispatch\s*(?:to|for)\s*carrier|accounts?\s*payable)\b",
    re.I,
)
_AUTHORITY_CARRIER_LABEL_RE = re.compile(
    r"\b(carrier\s*name|carrier\s*signature|driver\s*phone|for\s*load\s*information|"
    r"\battn\s*:|dispatcher\b|\bdba\b|primary\s*driver|truck\s*#|trailer\s*#)\b",
    re.I,
)


def _authority_role_labels(surrounding_text: str) -> list[str]:
    s = surrounding_text or ""
    out: list[str] = []
    if _AUTHORITY_CARRIER_LABEL_RE.search(s):
        out.append("carrier")
    if _AUTHORITY_BROKER_LABEL_RE.search(s):
        out.append("corporate")
    if re.search(r"\bfreight\s*broker\b|\bbroker\b", s, re.I):
        out.append("broker")
    if re.search(r"\bsignature\b", s, re.I):
        out.append("signature")
    if re.search(r"\bdriver\b", s, re.I):
        out.append("driver")
    # de-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        k = x.casefold()
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq


def _authority_role_hint_and_reason(surrounding_text: str) -> tuple[str, str]:
    s = surrounding_text or ""
    sc = s.casefold()
    c = bool(_AUTHORITY_CARRIER_LABEL_RE.search(s))
    b = bool(_AUTHORITY_BROKER_LABEL_RE.search(s))
    if b and not c:
        return "broker_context", "broker_or_corporate_document_cues_without_carrier_block_cues"
    if c and not b:
        return "carrier_context", "carrier_driver_or_signature_block_cues_without_broker_document_cues"
    if b and c:
        return "unknown", "mixed_broker_and_carrier_cues_in_window"
    if re.search(r"\bfreight\s*broker\b|\bbroker\b", sc, re.I) and not c:
        return "broker_context", "generic_broker_keyword_without_carrier_cues"
    return "unknown", "no_strong_role_keywords_in_window"


def _authority_role_hint(surrounding_text: str) -> str:
    return _authority_role_hint_and_reason(surrounding_text)[0]


def _nearby_company_candidate(line_text: str, surrounding: str) -> str:
    """Best-effort company fragment on the authority line or an adjacent line (no DB)."""
    line = (line_text or "").strip()
    if not line:
        return ""

    def _reject_label_only(s: str) -> bool:
        sl = (s or "").strip()
        if not sl:
            return True
        if re.fullmatch(r"[\W\d_]+", sl):
            return True
        # Banner / instruction lines, not company names
        if re.search(r"^(for\s+load\s+information|attn|note|please)\b", sl, re.I):
            return True
        if sl.endswith(":") and len(sl) < 50 and "dba" not in sl.casefold() and "inc" not in sl.casefold():
            return True
        return False

    cleaned = _MC_RE.sub(" ", line)
    cleaned = _DOT_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:|")
    if 6 <= len(cleaned) <= 100 and re.search(r"[A-Za-z]{3,}", cleaned):
        if not re.fullmatch(r"[\d\s#:.\-]+", cleaned) and not _reject_label_only(cleaned):
            return cleaned[:120]
    for ln in (surrounding or "").splitlines():
        t = ln.strip()
        if not t or t == line:
            continue
        if _MC_RE.search(t) or _DOT_RE.search(t):
            continue
        if 8 <= len(t) <= 90 and re.search(r"[A-Za-z]{3,}", t) and not _reject_label_only(t):
            return t[:120]
    return ""


def _authority_candidates(page_texts: list[str]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    mcs: set[str] = set()
    dots: set[str] = set()

    for page_num, txt in enumerate(page_texts, start=1):
        lines = txt.splitlines()
        for line_idx, line in enumerate(lines):
            line_text = line
            if not line_text.strip():
                continue
            lo = max(0, line_idx - 3)
            hi = min(len(lines), line_idx + 4)
            surrounding = "\n".join(lines[lo:hi])

            for m in _MC_RE.finditer(line_text):
                val = m.group(1)
                if val:
                    mcs.add(val)
                    labels = _authority_role_labels(surrounding)
                    rh, rr = _authority_role_hint_and_reason(surrounding)
                    entries.append(
                        {
                            "value": val,
                            "kind": "mc",
                            "type": "MC",
                            "page": page_num,
                            "line_index": line_idx,
                            "line_text": line_text.strip()[:500],
                            "surrounding_text": surrounding.strip()[:1200],
                            "nearby_role_labels": labels,
                            "nearby_company_candidate": _nearby_company_candidate(line_text, surrounding),
                            "role_hint": rh,
                            "reason_for_role_hint": rr,
                        }
                    )

            for m in _DOT_RE.finditer(line_text):
                val = m.group(1)
                if val:
                    dots.add(val)
                    labels = _authority_role_labels(surrounding)
                    rh, rr = _authority_role_hint_and_reason(surrounding)
                    entries.append(
                        {
                            "value": val,
                            "kind": "dot",
                            "type": "DOT",
                            "page": page_num,
                            "line_index": line_idx,
                            "line_text": line_text.strip()[:500],
                            "surrounding_text": surrounding.strip()[:1200],
                            "nearby_role_labels": labels,
                            "nearby_company_candidate": _nearby_company_candidate(line_text, surrounding),
                            "role_hint": rh,
                            "reason_for_role_hint": rr,
                        }
                    )

    return {
        "entries": entries[:80],
        "mc_numbers": sorted(mcs)[:20],
        "dot_numbers": sorted(dots)[:20],
    }

