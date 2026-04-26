"""Load Lab — broker confidence matrix (diagnostics-only).

Builds parse_diagnostics.broker_confidence_matrix from party mentions, authority role hints,
and tenant + global broker reference signals (domains, known senders, aliases, MC/DOT).

Not used for workspace hydration.
"""

from __future__ import annotations

import os
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.broker import Broker, BrokerAlias, BrokerContact, BrokerDomain, BrokerKnownSender
from app.models.global_booking_broker import (
    GlobalBookingBroker,
    GlobalBookingBrokerAlias,
    GlobalBookingBrokerDomain,
    GlobalBookingBrokerKnownSender,
)
from app.utils.broker_identity import normalize_alias, normalize_domain, normalize_known_sender_email


def _digits(s: str | None) -> str:
    return re.sub(r"\D+", "", s or "")


def _legal_suffix_only_bonus(name: str) -> bool:
    """True if name carries a conservative legal-entity suffix (not logistics/transport as suffix token)."""
    return bool(
        re.search(r"\b(inc\.?|llc|ltd\.?|limited|corp\.?|corporation)\b", name or "", re.I)
    )


def _business_identity_word(name: str) -> bool:
    return bool(
        re.search(
            r"\b(logistics|transportation?|freight|brokerage|supply\s*chain)\b",
            name or "",
            re.I,
        )
    )


def _window_around_name(raw: str, name: str, *, radius: int = 420) -> str:
    if not raw or not name:
        return ""
    idx = raw.casefold().find(name.strip().casefold())
    if idx < 0:
        return raw[: min(len(raw), 800)]
    lo = max(0, idx - radius)
    hi = min(len(raw), idx + len(name) + radius)
    return raw[lo:hi]


def _explicit_broker_label_score(
    *,
    name: str,
    raw: str,
    is_stop_level: bool,
    nearby_labels: list[str] | None,
) -> tuple[int, list[str]]:
    """Strong only in document/broker context; capped when stop/customs/local."""
    factors: list[str] = []
    w = _window_around_name(raw, name)
    low = w.casefold()
    labels_cf = {str(x).casefold() for x in (nearby_labels or []) if isinstance(x, str)}
    has_broker_label = bool(re.search(r"\bbroker\s*[:\-]", low, re.I))
    customs_near = "customs" in labels_cf or "customs broker" in low
    stop_near = is_stop_level or bool(re.search(r"\b(stop\s*location|pick\s*/\s*drop|pickup\s*#|delivery\s*#)\b", low, re.I))

    if not has_broker_label:
        return 0, factors

    if customs_near:
        factors.append("broker_label_near_customs_context")
        return 2, factors
    if stop_near:
        factors.append("broker_label_stop_or_table_local_context")
        return 2, factors
    if re.search(r"\b(corporate|invoice|freight\s*broker|rate\s*confirm|tender)\b", low, re.I):
        factors.append("broker_label_document_context")
        return 10, factors
    factors.append("broker_label_present_weak_context")
    return 5, factors


def _payer_billto_score(raw: str, name: str) -> tuple[int, list[str]]:
    w = _window_around_name(raw, name)
    low = w.casefold()
    score = 0
    factors: list[str] = []
    for pat, label in (
        (r"\binvoice\b", "invoice_language"),
        (r"\bquickpay\b", "quickpay"),
        (r"\bpayment\b", "payment_language"),
        (r"\bremit\b", "remit_language"),
        (r"\bbill\s*to\b", "bill_to_language"),
        (r"ap@", "accounts_payable_email"),
    ):
        if re.search(pat, low, re.I):
            score += 1
            factors.append(label)
    return min(score, 5), factors


def _agreement_counterparty_score(raw: str, name: str) -> tuple[int, list[str]]:
    w = _window_around_name(raw, name)
    low = w.casefold()
    score = 0
    factors: list[str] = []
    if re.search(r"\bfreight\s*broker\b", low, re.I):
        score += 3
        factors.append("freight_broker_language")
    if re.search(r"49\s*CFR|371\.2", low, re.I):
        score += 2
        factors.append("federal_broker_reg_citation")
    if re.search(r"\bcarrier\s+hired\s+by\b|\bagreement\b", low, re.I):
        score += 1
        factors.append("carrier_counterparty_language")
    return min(score, 6), factors


def _broker_contact_domain_score(
    m: dict[str, Any],
    *,
    tenant_domains: set[str],
    global_domains: set[str],
    demo_domains: set[str],
) -> tuple[int, list[str], list[str]]:
    matched: list[str] = []
    factors: list[str] = []
    score = 0
    for d in m.get("domains") or []:
        if not isinstance(d, str):
            continue
        try:
            dn = normalize_domain(d)
        except Exception:
            dn = d.strip().casefold()
        dcf = dn.casefold()
        if dcf in tenant_domains:
            score += 4
            matched.append(dn)
            factors.append(f"tenant_broker_domain:{dn}")
        elif dcf in global_domains:
            score += 3
            matched.append(dn)
            factors.append(f"global_broker_domain:{dn}")
        elif dcf in demo_domains:
            score += 1
            matched.append(dn)
            factors.append(f"demo_domain_hint:{dn}")
    for em in m.get("emails") or []:
        if not isinstance(em, str):
            continue
        try:
            en = normalize_known_sender_email(em)
        except Exception:
            en = em.strip().casefold()
        dom = en.split("@", 1)[-1] if "@" in en else ""
        if not dom:
            continue
        try:
            dcf = normalize_domain(dom).casefold()
        except Exception:
            dcf = dom.casefold()
        if dcf in tenant_domains or dcf in global_domains or dcf in demo_domains:
            score += 3
            matched.append(em)
            factors.append(f"email_domain_match:{dom}")
    return min(score, 12), factors, matched


def _broker_authority_context_score(
    name: str,
    authority_entries: list[dict[str, Any]],
) -> tuple[int, list[str], list[str], list[str]]:
    """MC/DOT in broker_context lines whose nearby company matches this candidate name."""
    score = 0
    factors: list[str] = []
    mcs: list[str] = []
    dots: list[str] = []
    ncf = name.strip().casefold()
    if not ncf:
        return 0, factors, mcs, dots
    for e in authority_entries:
        if e.get("role_hint") != "broker_context":
            continue
        typ = (e.get("type") or e.get("kind") or "").casefold()
        near = (e.get("nearby_company_candidate") or "").strip()
        if near and ncf in near.casefold():
            if typ == "mc":
                v = _digits(str(e.get("value")))
                if v:
                    mcs.append(v)
                    score += 5
                    factors.append(f"broker_context_mc:{v}_near_name")
            elif typ == "dot":
                v = _digits(str(e.get("value")))
                if v:
                    dots.append(v)
                    score += 4
                    factors.append(f"broker_context_dot:{v}_near_name")
    return min(score, 12), factors, mcs, dots


def _directory_grounding_for_name(
    name: str,
    matches: list[dict[str, Any]],
) -> tuple[int, bool, list[str], list[str], list[str], list[str]]:
    """Score + matched MC/DOT/domain/email evidence from broker_directory_matches."""
    score = 0
    grounded = False
    factors: list[str] = []
    mcs: list[str] = []
    dots: list[str] = []
    doms: list[str] = []
    emails: list[str] = []
    ncf = name.strip().casefold()
    try:
        an = normalize_alias(name)
    except Exception:
        an = None
    for rec in matches:
        if not isinstance(rec, dict):
            continue
        bd = rec.get("broker_display")
        if isinstance(bd, str) and bd.strip() and bd.strip().casefold() == ncf:
            grounded = True
            score += 10
            factors.append("broker_directory_display_match")
        if an and isinstance(rec.get("value"), str) and rec.get("matched_by") == "alias":
            if normalize_alias(rec["value"]) == an:
                grounded = True
                score += 8
                factors.append("broker_directory_alias_match")
        mb = rec.get("matched_by")
        if mb in ("mc", "dot") and isinstance(bd, str) and bd.strip().casefold() == ncf:
            score += 4
            factors.append(f"authority_directory_{mb}")
        mv = rec.get("matched_authority_value") or rec.get("mc_number") or rec.get("dot_number")
        if mb == "mc" and mv:
            mcs.append(_digits(str(mv)))
        if mb == "dot" and mv:
            dots.append(_digits(str(mv)))
        if isinstance(rec.get("value"), str) and rec.get("matched_by") == "domain":
            doms.append(str(rec["value"]))
        if isinstance(rec.get("value"), str) and rec.get("matched_by") in ("known_sender_email",):
            emails.append(str(rec["value"]))
    return min(score, 22), grounded, factors, mcs, dots, doms, emails


def _carrier_role_evidence(name: str, raw: str | None) -> tuple[int, list[str], bool]:
    """Returns (penalty 0..12, negative_factors, is_carrier_role_candidate)."""
    negatives: list[str] = []
    n = (name or "").strip()
    if not n:
        return 0, negatives, False
    pen = 0
    carrierish = False
    low = n.casefold()
    if " dba " in low or re.match(r"^\d{4,}\b", low):
        pen += 8
        negatives.append("dba_or_numeric_leading_legal_name_carrier_shape")
        carrierish = True
    t = raw or ""
    if t:
        idx = t.casefold().find(low)
        if idx >= 0:
            win = t[max(0, idx - 220) : idx + len(n) + 220].casefold()
            if re.search(
                r"\b(carrier\s*name|carrier\s*signature|driver\s*phone|for\s*load\s*information|attn\s*:)\b",
                win,
                re.I,
            ):
                pen += 6
                negatives.append("carrier_role_window_near_name")
                carrierish = True
    return min(pen, 12), negatives, carrierish


def _document_identity_score(m: dict[str, Any], raw: str | None) -> tuple[int, list[str]]:
    factors: list[str] = []
    score = 0
    if m.get("is_document_identity_level") is True:
        score += 6
        factors.append("document_identity_level")
    if m.get("is_header_level") is True:
        score += 2
        factors.append("header_level_mention")
    nm = str(m.get("name") or "").strip()
    if nm and _legal_suffix_only_bonus(nm):
        score += 1
        factors.append("legal_entity_suffix_token")
    if nm and _business_identity_word(nm):
        score += 1
        factors.append("business_identity_word_in_name")
    if raw and nm:
        score += min(raw.casefold().count(nm.casefold()), 8)
        if score > 0 and "mention_frequency" not in factors:
            factors.append("mention_frequency")
    return score, factors


def _role_contexts_for_mention(m: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for z in m.get("zones") or []:
        if isinstance(z, str):
            out.append(f"zone:{z}")
    if m.get("is_stop_level") is True:
        out.append("stop_level_party")
    if m.get("is_contact_block") is True:
        out.append("contact_block")
    if m.get("is_signature_block") is True:
        out.append("signature_block")
    return out


def _confidence_from_total(total: float, blocked: bool) -> str:
    if blocked:
        return "low"
    if total >= 20:
        return "high"
    if total >= 12:
        return "medium"
    return "low"


def _demo_domain_hints() -> set[str]:
    """Optional test/demo fallback only when LOAD_LAB_DEMO_DOMAIN_HINTS=1."""
    if os.environ.get("LOAD_LAB_DEMO_DOMAIN_HINTS", "").strip() not in ("1", "true", "yes"):
        return set()
    return {"armstrongtransport.com"}


async def load_broker_match_signals(db: AsyncSession, tenant_id: int) -> dict[str, Any]:
    """Load tenant broker directory + approved global booking broker reference signals."""
    tenant_domains: set[str] = set()
    tenant_emails: set[str] = set()
    tenant_aliases_cf: set[str] = set()
    tenant_mc: set[str] = set()
    tenant_dot: set[str] = set()

    for row in (
        await db.execute(
            select(BrokerDomain.domain).where(BrokerDomain.tenant_id == tenant_id, BrokerDomain.is_active.is_(True)).limit(500)
        )
    ).scalars().all():
        if isinstance(row, str) and row.strip():
            try:
                tenant_domains.add(normalize_domain(row).casefold())
            except Exception:
                tenant_domains.add(row.strip().casefold())

    for row in (
        await db.execute(
            select(BrokerContact.email).where(
                BrokerContact.tenant_id == tenant_id,
                BrokerContact.is_active.is_(True),
                BrokerContact.email.is_not(None),
            ).limit(500)
        )
    ).scalars().all():
        if not isinstance(row, str) or "@" not in row:
            continue
        dom = row.split("@", 1)[-1].strip()
        if not dom:
            continue
        try:
            tenant_domains.add(normalize_domain(dom).casefold())
        except Exception:
            tenant_domains.add(dom.casefold())

    for row in (
        await db.execute(
            select(BrokerKnownSender.email_normalized).where(
                BrokerKnownSender.tenant_id == tenant_id, BrokerKnownSender.is_active.is_(True)
            ).limit(500)
        )
    ).scalars().all():
        if isinstance(row, str) and row.strip():
            tenant_emails.add(row.strip().casefold())

    for row in (
        await db.execute(
            select(BrokerAlias.alias).where(BrokerAlias.tenant_id == tenant_id, BrokerAlias.is_active.is_(True)).limit(500)
        )
    ).scalars().all():
        if isinstance(row, str) and row.strip():
            try:
                tenant_aliases_cf.add(normalize_alias(row))
            except Exception:
                tenant_aliases_cf.add(row.strip().casefold())

    for row in (
        await db.execute(
            select(Broker.mc_number, Broker.dot_number).where(Broker.tenant_id == tenant_id, Broker.is_active.is_(True)).limit(500)
        )
    ).all():
        mc, dot = row[0], row[1]
        dmc = _digits(str(mc) if mc else "")
        if dmc:
            tenant_mc.add(dmc)
        ddot = _digits(str(dot) if dot else "")
        if ddot:
            tenant_dot.add(ddot)

    global_domains: set[str] = set()
    global_aliases_cf: set[str] = set()
    global_mc: set[str] = set()
    global_dot: set[str] = set()

    # Global booking brokers live on the platform DB, not tenant DB.
    async with AsyncSessionLocal() as platform_db:
        gb_stmt = select(GlobalBookingBroker).where(GlobalBookingBroker.canonical_status == "approved").limit(300)
        gbrokers = list((await platform_db.execute(gb_stmt)).scalars().all())
        g_ids = [g.id for g in gbrokers]
        if g_ids:
            for row in (
                await platform_db.execute(
                    select(GlobalBookingBrokerDomain.domain).where(GlobalBookingBrokerDomain.global_broker_id.in_(g_ids))
                )
            ).scalars().all():
                if isinstance(row, str) and row.strip():
                    try:
                        global_domains.add(normalize_domain(row).casefold())
                    except Exception:
                        global_domains.add(row.strip().casefold())
            for row in (
                await platform_db.execute(
                    select(GlobalBookingBrokerKnownSender.email_normalized).where(
                        GlobalBookingBrokerKnownSender.global_broker_id.in_(g_ids)
                    )
                )
            ).scalars().all():
                if isinstance(row, str) and row.strip():
                    tenant_emails.add(row.strip().casefold())
            for row in (
                await platform_db.execute(
                    select(GlobalBookingBrokerAlias.alias).where(GlobalBookingBrokerAlias.global_broker_id.in_(g_ids))
                )
            ).scalars().all():
                if isinstance(row, str) and row.strip():
                    try:
                        global_aliases_cf.add(normalize_alias(row))
                    except Exception:
                        global_aliases_cf.add(row.strip().casefold())
            for g in gbrokers:
                dmc = _digits(str(g.mc_number or ""))
                if dmc:
                    global_mc.add(dmc)
                ddot = _digits(str(g.dot_number or ""))
                if ddot:
                    global_dot.add(ddot)

    return {
        "tenant_domains": tenant_domains,
        "tenant_emails": tenant_emails,
        "tenant_aliases_cf": tenant_aliases_cf,
        "tenant_mc": tenant_mc,
        "tenant_dot": tenant_dot,
        "global_domains": global_domains,
        "global_aliases_cf": global_aliases_cf,
        "global_mc": global_mc,
        "global_dot": global_dot,
    }


def _extract_carrier_style_company_lines(raw: str) -> list[str]:
    out: list[str] = []
    if not raw:
        return out
    for ln in raw.splitlines():
        s = ln.strip()
        if len(s) < 10:
            continue
        if re.search(r"\bDBA\b", s, re.I) and re.search(r"\d{4,}", s):
            out.append(s[:200])
        if re.search(r"\bINC\b.*\bLOGISTICS\b", s, re.I):
            out.append(s[:200])
        # Carrier legal line + brand (e.g. MC … INC … DBA IK LOGISTICS LLC)
        if re.search(r"\bIK\s+LOGISTICS\b", s, re.I) and (
            re.search(r"\bDBA\b", s, re.I) or re.search(r"\bMC\b", s, re.I) or re.search(r"\d{6,10}", s)
        ):
            out.append(s[:200])
    # de-dupe
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        k = x.casefold()
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq[:5]


def build_broker_confidence_matrix(
    *,
    diag: dict[str, Any],
    raw_text: str | None,
    signals: dict[str, Any],
) -> list[dict[str, Any]]:
    raw = raw_text or ""
    pm = diag.get("party_mentions") if isinstance(diag.get("party_mentions"), list) else []
    matches = diag.get("broker_directory_matches") if isinstance(diag.get("broker_directory_matches"), list) else []
    auth_entries = []
    ac = diag.get("authority_candidates")
    if isinstance(ac, dict) and isinstance(ac.get("entries"), list):
        auth_entries = [e for e in ac["entries"] if isinstance(e, dict)]

    tenant_domains = signals.get("tenant_domains") or set()
    global_domains = signals.get("global_domains") or set()
    demo_domains = _demo_domain_hints()
    if not isinstance(tenant_domains, set):
        tenant_domains = {str(x).casefold() for x in tenant_domains}
    if not isinstance(global_domains, set):
        global_domains = {str(x).casefold() for x in global_domains}

    seen_names: set[str] = set()
    rows: list[dict[str, Any]] = []

    def _add_row_for_mention(m: dict[str, Any]) -> None:
        nm = m.get("name")
        if not isinstance(nm, str) or not nm.strip():
            return
        name = nm.strip()
        # Audit / UI noise lines sometimes surface as pseudo party mentions; exclude from broker matrix.
        if re.match(r"^User:\s", name, re.I):
            return
        if re.search(r"UTC\s*-\s*(Terms Accepted|Downloaded|Viewed|Delivered)\b", name, re.I):
            return
        if len(name) > 140:
            return
        k = name.casefold()
        if k in seen_names:
            return
        seen_names.add(k)

        expl, expl_f = _explicit_broker_label_score(
            name=name,
            raw=raw,
            is_stop_level=m.get("is_stop_level") is True,
            nearby_labels=m.get("nearby_labels") if isinstance(m.get("nearby_labels"), list) else [],
        )
        doc_score, doc_f = _document_identity_score(m, raw)
        pay_score, pay_f = _payer_billto_score(raw, name)
        agr_score, agr_f = _agreement_counterparty_score(raw, name)
        dom_score, dom_f, matched_emails_domains = _broker_contact_domain_score(
            m, tenant_domains=tenant_domains, global_domains=global_domains, demo_domains=demo_domains
        )
        auth_score, auth_f, auth_mcs, auth_dots = _broker_authority_context_score(name, auth_entries)
        g_score, grounded, g_f, g_mcs, g_dots, g_dom, g_em = _directory_grounding_for_name(name, matches)
        pen, neg_f, is_carrier = _carrier_role_evidence(name, raw)

        dims = {
            "explicit_broker_label_score": float(expl),
            "document_identity_score": float(doc_score),
            "payer_billto_score": float(pay_score),
            "agreement_counterparty_score": float(agr_score),
            "broker_contact_domain_score": float(dom_score),
            "broker_authority_context_score": float(auth_score),
            "broker_directory_grounding_score": float(g_score),
            "carrier_role_penalty": float(pen),
        }
        pos = expl + doc_score + pay_score + agr_score + dom_score + auth_score + g_score
        total = pos - pen
        evidence = expl_f + doc_f + pay_f + agr_f + dom_f + auth_f + g_f
        blocked = is_carrier and pos < 14
        reason_blocked = ""
        if blocked:
            reason_blocked = "Strong carrier-role evidence with weak broker document signals; blocked from booking broker."
        conf = _confidence_from_total(total, blocked)

        matched_domains = list({*g_dom, *[x for x in matched_emails_domains if "." in x and "@" not in x]})
        matched_emails = [x for x in matched_emails_domains if "@" in x]

        rows.append(
            {
                "name": name,
                "total_score": round(total, 2),
                "confidence": conf,
                "evidence_factors": evidence,
                "negative_factors": neg_f,
                "matched_domains": matched_domains[:20],
                "matched_emails": matched_emails[:20],
                "matched_mc_numbers": list({*auth_mcs, *g_mcs})[:10],
                "matched_dot_numbers": list({*auth_dots, *g_dots})[:10],
                "role_contexts": _role_contexts_for_mention(m),
                "is_grounded_to_broker_db": grounded,
                "is_document_identity_candidate": m.get("is_document_identity_level") is True,
                "is_carrier_role_candidate": is_carrier,
                "blocked_from_booking_broker": blocked,
                "reason_if_blocked": reason_blocked if blocked else "",
                "dimensions": dims,
            }
        )

    for m in pm:
        if isinstance(m, dict):
            _add_row_for_mention(m)

    for extra in _extract_carrier_style_company_lines(raw):
        k = extra.casefold()
        if k in seen_names:
            continue
        synthetic = {
            "name": extra,
            "zones": [],
            "emails": [],
            "domains": [],
            "is_stop_level": False,
            "is_document_identity_level": False,
            "is_header_level": False,
            "is_contact_block": False,
            "is_signature_block": False,
            "nearby_labels": [],
            "mention_count": 0,
        }
        _add_row_for_mention(synthetic)

    rows.sort(key=lambda r: float(r.get("total_score") or 0), reverse=True)
    return rows[:25]
