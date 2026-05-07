"""Section-aware Contact role classification for product load document diagnostics.

Builds contact_candidates[] with roles for guarded parsing. No Load Lab imports.

Core model: rate confirmations flow Broker → Carrier. "CARRIER INFORMATION" blocks
describe the motor carrier / driver side; "CONTACT INFORMATION" blocks describe the
broker/agent contact for the load. When both appear (including on one flattened line),
we split wide gaps into left/right columns when possible (left = carrier, right = broker).
"""

from __future__ import annotations

import re
from typing import Any

_KINDS = frozenset({"name", "email", "phone"})
_ROLES = frozenset(
    {
        "broker_party",
        "carrier_party",
        "driver_party",
        "shipper_receiver_party",
        "payment_paperwork_party",
        "unknown",
    }
)

# Section headers: (regex, canonical_key). Scan each line with finditer; collect by start offset.
_SECTION_HEADER_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bCARRIER\s+CONTACT\b", re.I), "carrier_information"),
    (re.compile(r"\bDRIVER\s*/\s*CARRIER\b", re.I), "carrier_information"),
    (re.compile(r"\bCARRIER\s+INFORMATION\b", re.I), "carrier_information"),
    (re.compile(r"\bCONTACT\s+INFORMATION\b", re.I), "contact_information"),
    (re.compile(r"\bCONTACT\s+INFO\b", re.I), "contact_information"),
    (re.compile(r"\bPAYMENT\s+STATUS\s+QUESTIONS\b", re.I), "payment_status_questions"),
    (re.compile(r"\bPAPERWORK\s+SUBMISSION\b", re.I), "paperwork_submission"),
    (re.compile(r"\bORDER\s+INFORMATION\b", re.I), "order_information"),
    (
        re.compile(r"\bCARRIER\s+RATE\s+CONFIRMATION\b", re.I),
        "rate_confirmation",
    ),
    (re.compile(r"\bSTOP\s+DETAIL\b", re.I), "stop_detail"),
    (re.compile(r"\bLOCATION\s+NOTES\b", re.I), "location_notes"),
    (re.compile(r"\bPAYMENT\b", re.I), "payment"),
    (re.compile(r"\bAGREEMENT\b", re.I), "agreement"),
    (re.compile(r"\bNOTES\b", re.I), "notes"),
    (re.compile(r"\bINSTRUCTIONS\b", re.I), "instructions"),
)

_EMAIL_SINGLE = re.compile(r"[\w.+-]+@(?:[\w-]+\.)+[a-zA-Z]{2,}")
_PHONE_SINGLE = re.compile(r"\b(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b")
_NAME_SKIP_CO = re.compile(
    r"\b(?:llc|l\.l\.c\.|inc\.?|corp\.?|ltd\.?|co\.?|company|logistics|transport|freight|trucking|warehouse)\b",
    re.I,
)
_SKIP_TOKENS = frozenset(
    {
        "name",
        "dispatcher",
        "driver",
        "phone",
        "email",
        "fax",
        "cell",
        "mobile",
        "contact",
        "carrier",
        "truck",
        "trailer",
    }
)

_PAYMENT_PAPERWORK_CUE = re.compile(
    r"\b(?:"
    r"quickpay|accounts?\s*payable|a/?p\b|ap\s+email|payment\s*status|"
    r"paperwork\s*submission|carrier\s*paperwork|invoice\s*submission|remit|"
    r"payment\s*questions|billing\s*desk|docs?\s*desk|document\s*desk"
    r")\b",
    re.I,
)
_SHIPPER_RECEIVER_CUE = re.compile(
    r"\b(?:"
    r"shipper|consignee|receiver|delivery\s*contact|pickup\s*contact|"
    r"ship\s*to|deliver\s*to|consignee\s*contact"
    r")\b",
    re.I,
)
_CARRIER_BLOCK_CUE = re.compile(
    r"\b(?:"
    r"carrier\s*rep|motor\s*carrier|dispatcher\b|\bdriver\b|signature|"
    r"carrier\s*signature|for\s*load\s*information|equipment\s*operator|"
    r"tractor|trailer\s*#|truck\s*#|primary\s*driver"
    r")\b",
    re.I,
)
_DRIVER_CUE = re.compile(
    r"\b(?:\bdriver\b|cdl|tractor|signature|cell\s*phone\s*\(?\s*driver)\b",
    re.I,
)
_BROKER_OPS_CUE = re.compile(
    r"\b(?:"
    r"account\s*rep|after[\s-]*hours|tracking\s*contact|load\s*planner|"
    r"broker\s*contact|dispatch\s*desk|freight\s*(?:agent|coordinator)|\bagent\b"
    r")\b",
    re.I,
)
_PUBLIC_WEBMAIL = re.compile(
    r"@(?:gmail|hotmail|yahoo|outlook|live|icloud|msn|aol)\.(?:com|ca|co\.uk|net)\b",
    re.I,
)
_SECONDARY_BROKER_LOCAL = re.compile(
    r"(?:^tracking|tracking$|etrack|loadtrack|afterhours|ahdesk|paperwork|billing|cha\d*track)",
    re.I,
)


def _dual_column_segments(line: str) -> list[tuple[str, str]] | None:
    """Split two-column flattened rows: left cell → carrier_information, right → contact_information.

    Uses tab or 4+ spaces (common when PDF text preserves wide column gaps).
    """
    raw = line.strip()
    if "\t" in raw:
        parts = [p.strip() for p in raw.split("\t") if p.strip()]
    else:
        parts = [p.strip() for p in re.split(r"\s{4,}", raw) if p.strip()]
    if len(parts) < 2:
        return None
    left = parts[0]
    right = " ".join(parts[1:]).strip() if len(parts) > 2 else parts[1]
    if not left or not right:
        return None
    return [(left, "carrier_information"), (right, "contact_information")]


def _headers_on_line(line: str) -> list[str]:
    hits: list[tuple[int, str]] = []
    for rx, key in _SECTION_HEADER_RULES:
        for m in rx.finditer(line):
            hits.append((m.start(), key))
    hits.sort(key=lambda x: x[0])
    out: list[str] = []
    seen: set[str] = set()
    for _, key in hits:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _nearby_lines(lines: list[str], idx: int, before: int = 2, after: int = 2) -> str:
    lo = max(0, idx - before)
    hi = min(len(lines), idx + after + 1)
    return "\n".join(lines[lo:hi])


def _line_person_name_ok(line: str) -> bool:
    s = " ".join(line.split()).strip()
    if not s or len(s) > 70:
        return False
    if any(ch.isdigit() for ch in s) or "@" in s:
        return False
    sl = s.casefold()
    if sl in _SKIP_TOKENS or len(sl) <= 2:
        return False
    if _NAME_SKIP_CO.search(s):
        return False
    if "(" in s or ")" in s:
        return False
    tokens = s.split()
    if len(tokens) < 2 or len(tokens) > 5:
        return False
    return all(re.match(r"^[A-Za-z][A-Za-z'.-]*$", t) for t in tokens)


def _name_prefix_before_contact_tokens(line: str) -> str | None:
    """Recover 'First Last' from 'First Last 555-1212 x@y.com' after stripping phones/emails."""
    tmp = line
    for m in list(_EMAIL_SINGLE.finditer(tmp))[::-1]:
        tmp = tmp[: m.start()] + " " + tmp[m.end() :]
    for m in list(_PHONE_SINGLE.finditer(tmp))[::-1]:
        tmp = tmp[: m.start()] + " " + tmp[m.end() :]
    tmp = " ".join(tmp.split()).strip(" ,;|-")
    if _line_person_name_ok(tmp):
        return " ".join(tmp.split())
    return None


def _broker_contact_tier_for_email(email: str, nearby_cf: str) -> str:
    local = email.split("@", 1)[0].casefold()
    blob = f"{local} {nearby_cf}"
    if _SECONDARY_BROKER_LOCAL.match(local) or _SECONDARY_BROKER_LOCAL.match(blob):
        return "secondary"
    if _BROKER_OPS_CUE.search(nearby_cf) and "tracking" in local:
        return "secondary"
    return "primary"


def _assign_role(
    *,
    kind: str,
    value: str,
    section_ctx: list[str],
    nearby: str,
    line_text: str,
) -> tuple[str, str, str | None]:
    """Returns (role, reason, broker_contact_tier or None)."""
    sec_cf = " ".join(section_ctx).casefold() if section_ctx else ""
    nearby_cf = nearby.casefold()
    line_cf = line_text.casefold()
    blob_cf = f"{nearby_cf} {line_cf} {sec_cf}"

    ctx_set = frozenset(section_ctx)

    if kind == "email" and _PAYMENT_PAPERWORK_CUE.search(blob_cf):
        return "payment_paperwork_party", "Payment, A/P, quickpay, or paperwork cue near email.", None
    if kind == "phone" and ctx_set & {"payment", "paperwork_submission", "payment_status_questions"}:
        if _PAYMENT_PAPERWORK_CUE.search(blob_cf):
            return "payment_paperwork_party", "Phone under payment/paperwork-related section header.", None
    if kind == "email":
        local = value.split("@", 1)[0].casefold()
        if local in {"ap", "billing", "invoices", "paperwork", "carrierpaperwork", "payments", "ar", "acc"}:
            return "payment_paperwork_party", "Email local part suggests payment/paperwork mailbox.", None

    shipper_section = ctx_set & {"stop_detail", "location_notes", "notes", "order_information"}
    if shipper_section and _SHIPPER_RECEIVER_CUE.search(blob_cf):
        return "shipper_receiver_party", "Shipper/receiver/stop cue in location or order context.", None
    if kind == "email" and _SHIPPER_RECEIVER_CUE.search(blob_cf) and not _BROKER_OPS_CUE.search(blob_cf):
        if "contact_information" not in ctx_set or ctx_set & {"stop_detail", "location_notes"}:
            return "shipper_receiver_party", "Shipper/receiver wording near email; not broker ops context.", None

    if ctx_set & {"rate_confirmation"}:
        if kind == "email":
            tier = _broker_contact_tier_for_email(value, nearby_cf)
            return (
                "broker_party",
                "Carrier rate confirmation banner: broker-facing contact channel.",
                tier,
            )
        if kind == "phone":
            return (
                "broker_party",
                "Carrier rate confirmation banner: broker ops phone line.",
                None,
            )

    has_carrier = "carrier_information" in ctx_set
    has_contact_info = "contact_information" in ctx_set

    if has_carrier and not has_contact_info:
        if kind == "email" and _PUBLIC_WEBMAIL.search(value):
            return "carrier_party", "Contact section carrier-only scope; webmail domain typical of carrier ops.", None
        if _DRIVER_CUE.search(blob_cf):
            if kind == "name":
                return "driver_party", "Carrier information scope with driver/signature/equipment cues.", None
            return "carrier_party", "Carrier information scope with driver/signature/equipment cues.", None
        return "carrier_party", "Under carrier information header(s) without parallel contact information header.", None

    if has_contact_info and not has_carrier:
        if _PAYMENT_PAPERWORK_CUE.search(blob_cf) and kind == "email":
            return "payment_paperwork_party", "Contact information block but payment/paperwork cue dominates.", None
        tier = _broker_contact_tier_for_email(value, nearby_cf) if kind == "email" else None
        reason = "Under contact information header(s); default broker-facing contact."
        if tier == "secondary":
            reason += " Tracking/after-hours style address treated as secondary broker ops."
        return "broker_party", reason, tier if kind == "email" else None

    if has_carrier and has_contact_info:
        if kind == "name":
            emails_on_row = _EMAIL_SINGLE.findall(line_text)
            if len(emails_on_row) == 1:
                er, _, _bt = _assign_role(
                    kind="email",
                    value=emails_on_row[0],
                    section_ctx=section_ctx,
                    nearby=nearby,
                    line_text=line_text,
                )
                if er == "carrier_party":
                    return (
                        "carrier_party",
                        "Rate con Broker→Carrier: name row paired with carrier-classified email in dual-header scope.",
                        None,
                    )
                if er == "broker_party":
                    return (
                        "broker_party",
                        "Rate con Broker→Carrier: name row paired with broker-classified email in dual-header scope.",
                        None,
                    )
        if _CARRIER_BLOCK_CUE.search(blob_cf) and not _BROKER_OPS_CUE.search(blob_cf):
            t = "driver_party" if _DRIVER_CUE.search(blob_cf) and kind == "name" else "carrier_party"
            return t, "Dual headers: carrier/driver/dispatcher cues — carrier-side row.", None
        if _BROKER_OPS_CUE.search(blob_cf):
            tier = _broker_contact_tier_for_email(value, nearby_cf) if kind == "email" else None
            return "broker_party", "Dual headers: broker/agent/load-planner ops cues — broker-side row.", tier
        if kind == "email":
            _local_cf = value.split("@", 1)[0].casefold()
            if _PUBLIC_WEBMAIL.search(value) and not _SECONDARY_BROKER_LOCAL.search(_local_cf):
                return (
                    "carrier_party",
                    "Dual headers: webmail → motor-carrier contact (not broker_contact_*).",
                    None,
                )
            tier = _broker_contact_tier_for_email(value, nearby_cf)
            return (
                "broker_party",
                "Dual headers: corporate/domain email → broker/agent contact column (secondary if tracking-style).",
                tier,
            )
        if kind == "phone":
            raw_phone = value.strip()
            digits_only = re.sub(r"\D", "", raw_phone)
            if (
                len(digits_only) >= 10
                and len(digits_only) <= 11
                and not re.search(r"[\s().-]", raw_phone)
                and _PUBLIC_WEBMAIL.search(nearby)
            ):
                return (
                    "carrier_party",
                    "Dual headers: compact phone on carrier column before webmail (dispatcher/mobile).",
                    None,
                )
            return (
                "broker_party",
                "Dual headers: phone row defaulting to broker/agent column (no carrier/dispatcher cues on fragment).",
                None,
            )
        if kind == "name":
            if _DRIVER_CUE.search(blob_cf) or _CARRIER_BLOCK_CUE.search(blob_cf):
                return "carrier_party", "Dual headers: person name with carrier/driver cues.", None
            return (
                "unknown",
                "Dual headers: ambiguous person name without column split or email pairing.",
                None,
            )

    if ctx_set & {"payment", "paperwork_submission", "payment_status_questions", "agreement"}:
        if kind in {"email", "phone"} and _PAYMENT_PAPERWORK_CUE.search(blob_cf):
            return "payment_paperwork_party", "Under payment/paperwork/agreement header with operational cues.", None

    return "unknown", "No decisive section alignment for this token (flattened multi-column text).", None


def _candidate_dict(
    *,
    kind: str,
    value: str,
    page: int,
    line_index: int | None,
    nearby_text: str,
    section_context: list[str],
    role: str,
    reason: str,
    broker_contact_tier: str | None = None,
) -> dict[str, Any]:
    c: dict[str, Any] = {
        "kind": kind,
        "value": value,
        "page": page,
        "line_index": line_index,
        "nearby_text": nearby_text[:500],
        "section_context": list(section_context),
        "role": role,
        "reason": reason[:500],
    }
    if broker_contact_tier is not None:
        c["broker_contact_tier"] = broker_contact_tier
    return c


def build_contact_candidates(page_texts: list[str]) -> list[dict[str, Any]]:
    if not page_texts:
        page_texts = [""]

    candidates: list[dict[str, Any]] = []
    active_headers: list[str] = []

    for page_num, page_text in enumerate(page_texts, start=1):
        lines = page_text.splitlines()
        banner_phone_slot = 0

        for line_idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line:
                continue

            hdrs = _headers_on_line(line)
            if hdrs:
                # Rate cons often print "CARRIER INFORMATION CONTACT INFORMATION" then a sub-row
                # like "Carrier Contact ... After Hours". That row matches CARRIER CONTACT only and
                # must not drop the broker column — treat it as a continuation of the dual-header block.
                if (
                    "contact_information" in active_headers
                    and "contact_information" not in hdrs
                    and re.search(r"\bCARRIER\s+CONTACT\b", line, re.I)
                ):
                    hdrs = list(dict.fromkeys(list(hdrs) + ["contact_information"]))
                if "rate_confirmation" in hdrs:
                    banner_phone_slot = 0
                active_headers = hdrs
                continue

            nearby = _nearby_lines(lines, line_idx)
            sec_ctx = list(active_headers)
            dual_active = (
                "carrier_information" in active_headers and "contact_information" in active_headers
            )
            segs = _dual_column_segments(line) if dual_active else None
            if segs:
                frag_scopes: list[tuple[str, list[str]]] = [(txt, [key]) for txt, key in segs]
            else:
                frag_scopes = [(line, sec_ctx)]

            for frag_text, scope_ctx in frag_scopes:
                if not frag_text.strip():
                    continue

                name_val: str | None = None
                if _line_person_name_ok(frag_text):
                    name_val = " ".join(frag_text.split())
                else:
                    name_val = _name_prefix_before_contact_tokens(frag_text)
                if name_val:
                    role, reason, tier = _assign_role(
                        kind="name",
                        value=name_val,
                        section_ctx=scope_ctx,
                        nearby=nearby,
                        line_text=frag_text,
                    )
                    candidates.append(
                        _candidate_dict(
                            kind="name",
                            value=name_val,
                            page=page_num,
                            line_index=line_idx + 1,
                            nearby_text=nearby,
                            section_context=scope_ctx,
                            role=role,
                            reason=reason,
                            broker_contact_tier=tier,
                        )
                    )

                for m in _EMAIL_SINGLE.finditer(frag_text):
                    val = m.group(0).strip()
                    role, reason, tier = _assign_role(
                        kind="email",
                        value=val,
                        section_ctx=scope_ctx,
                        nearby=nearby,
                        line_text=frag_text,
                    )
                    candidates.append(
                        _candidate_dict(
                            kind="email",
                            value=val,
                            page=page_num,
                            line_index=line_idx + 1,
                            nearby_text=nearby,
                            section_context=scope_ctx,
                            role=role,
                            reason=reason,
                            broker_contact_tier=tier,
                        )
                    )

                for m in _PHONE_SINGLE.finditer(frag_text):
                    val = m.group(0).strip()
                    role, reason, tier = _assign_role(
                        kind="phone",
                        value=val,
                        section_ctx=scope_ctx,
                        nearby=nearby,
                        line_text=frag_text,
                    )
                    if "rate_confirmation" in scope_ctx and role == "broker_party":
                        banner_phone_slot += 1
                        tier = "secondary" if banner_phone_slot == 1 else "primary"
                    candidates.append(
                        _candidate_dict(
                            kind="phone",
                            value=val,
                            page=page_num,
                            line_index=line_idx + 1,
                            nearby_text=nearby,
                            section_context=scope_ctx,
                            role=role,
                            reason=reason,
                            broker_contact_tier=tier,
                        )
                    )

    return candidates[:200]


def summarize_contacts_from_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive legacy contacts.{broker_party,carrier_party} buckets from contact_candidates."""

    def _uniq(vals: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for v in vals:
            k = v.casefold()
            if k in seen:
                continue
            seen.add(k)
            out.append(v)
        return out

    broker_emails: list[str] = []
    broker_phones: list[str] = []
    broker_names: list[str] = []
    carrier_emails: list[str] = []
    carrier_phones: list[str] = []
    carrier_names: list[str] = []

    emails_all: list[str] = []
    phones_all: list[str] = []

    for c in candidates:
        if not isinstance(c, dict):
            continue
        kind = str(c.get("kind") or "")
        val = str(c.get("value") or "").strip()
        role = str(c.get("role") or "unknown")
        if not val or kind not in _KINDS or role not in _ROLES:
            continue
        if kind == "email":
            emails_all.append(val)
        elif kind == "phone":
            phones_all.append(val)

        if role == "broker_party":
            if kind == "email":
                broker_emails.append(val)
            elif kind == "phone":
                broker_phones.append(val)
            elif kind == "name":
                broker_names.append(val)
        elif role in {"carrier_party", "driver_party"}:
            if kind == "email":
                carrier_emails.append(val)
            elif kind == "phone":
                carrier_phones.append(val)
            elif kind == "name":
                carrier_names.append(val)

    return {
        "emails": _uniq(emails_all)[:30],
        "phones": _uniq(phones_all)[:30],
        "broker_party": {
            "emails": _uniq(broker_emails)[:15],
            "phones": _uniq(broker_phones)[:15],
            "person_names": _uniq(broker_names)[:20],
        },
        "carrier_party": {
            "emails": _uniq(carrier_emails)[:15],
            "phones": _uniq(carrier_phones)[:15],
            "person_names": _uniq(carrier_names)[:20],
        },
    }
