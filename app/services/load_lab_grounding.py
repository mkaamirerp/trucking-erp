"""Broker directory grounding for Load Lab (Phase 2).

Matches extracted party mentions to tenant broker directory records.
This is evidence, not automatic truth.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker, BrokerAlias, BrokerContact, BrokerDomain, BrokerKnownSender
from app.services.brokers import resolve_broker_by_authority
from app.utils.broker_identity import normalize_alias, normalize_domain, normalize_known_sender_email


def _digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")


async def ground_party_mentions_to_brokers(
    db: AsyncSession,
    *,
    tenant_id: int,
    party_mentions: list[dict[str, Any]] | None,
    authority_candidates: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return list of broker match evidence records."""
    out: list[dict[str, Any]] = []

    # 1) Authority (MC/DOT) — iterate every distinct candidate; record matched authority value.
    ac = authority_candidates or {}
    entries = ac.get("entries") if isinstance(ac, dict) else None
    seen_match: set[tuple[Any, ...]] = set()

    async def _append_authority_match(
        *,
        matched_by: str | None,
        broker: Any,
        matched_value: str | None,
        page: int | None = None,
    ) -> None:
        if broker is None or not matched_by:
            return
        key = (matched_by, int(broker.id), _digits(matched_value or ""))
        if key in seen_match:
            return
        seen_match.add(key)
        rec: dict[str, Any] = {
            "matched_by": matched_by,
            "broker_id": broker.id,
            "broker_display": broker.display_name or broker.legal_name or broker.name,
            "mc_number": broker.mc_number,
            "dot_number": broker.dot_number,
            "matched_authority_value": matched_value,
            "confidence": "high",
        }
        if page is not None:
            rec["authority_entry_page"] = page
        out.append(rec)

    if isinstance(entries, list) and entries:
        for ent in entries[:80]:
            if not isinstance(ent, dict):
                continue
            kind = str(ent.get("type") or ent.get("kind") or "").casefold()
            val = ent.get("value")
            if not isinstance(val, str) or not val.strip():
                continue
            page = ent.get("page") if isinstance(ent.get("page"), int) else None
            v = val.strip()
            if kind == "mc":
                mb, br = await resolve_broker_by_authority(db, tenant_id, mc_number=v, dot_number=None)
                await _append_authority_match(matched_by=mb, broker=br, matched_value=v, page=page)
            elif kind == "dot":
                mb, br = await resolve_broker_by_authority(db, tenant_id, mc_number=None, dot_number=v)
                await _append_authority_match(matched_by=mb, broker=br, matched_value=v, page=page)
    else:
        mc_list = ac.get("mc_numbers") if isinstance(ac.get("mc_numbers"), list) else []
        dot_list = ac.get("dot_numbers") if isinstance(ac.get("dot_numbers"), list) else []
        if isinstance(mc_list, list):
            for mc in mc_list:
                if not isinstance(mc, str) or not mc.strip():
                    continue
                mb, br = await resolve_broker_by_authority(db, tenant_id, mc_number=mc.strip(), dot_number=None)
                await _append_authority_match(matched_by=mb, broker=br, matched_value=mc.strip(), page=None)
        if isinstance(dot_list, list):
            for dot in dot_list:
                if not isinstance(dot, str) or not dot.strip():
                    continue
                mb, br = await resolve_broker_by_authority(db, tenant_id, mc_number=None, dot_number=dot.strip())
                await _append_authority_match(matched_by=mb, broker=br, matched_value=dot.strip(), page=None)

    if not party_mentions:
        return out

    # 2) Email / domain / known sender
    for pm in party_mentions[:200]:
        emails = pm.get("emails") if isinstance(pm, dict) else None
        domains = pm.get("domains") if isinstance(pm, dict) else None
        phones = pm.get("phones") if isinstance(pm, dict) else None
        name = pm.get("name") if isinstance(pm, dict) else None

        if isinstance(emails, list):
            for e in emails[:5]:
                if not isinstance(e, str):
                    continue
                try:
                    en = normalize_known_sender_email(e)
                except Exception:
                    continue
                stmt = (
                    select(BrokerKnownSender.broker_id)
                    .where(
                        BrokerKnownSender.tenant_id == tenant_id,
                        BrokerKnownSender.is_active.is_(True),
                        BrokerKnownSender.email_normalized == en,
                    )
                    .limit(5)
                )
                for bid in list((await db.execute(stmt)).scalars().all()):
                    out.append({"matched_by": "known_sender_email", "broker_id": int(bid), "value": en, "confidence": "high"})

        if isinstance(domains, list):
            for d in domains[:5]:
                if not isinstance(d, str):
                    continue
                try:
                    dn = normalize_domain(d)
                except Exception:
                    continue
                stmt = (
                    select(BrokerDomain.broker_id)
                    .where(
                        BrokerDomain.tenant_id == tenant_id,
                        BrokerDomain.is_active.is_(True),
                        BrokerDomain.domain == dn,
                    )
                    .limit(5)
                )
                for bid in list((await db.execute(stmt)).scalars().all()):
                    out.append({"matched_by": "domain", "broker_id": int(bid), "value": dn, "confidence": "medium"})

        # 3) Phone / contact email (softer)
        if isinstance(phones, list):
            for ph in phones[:3]:
                if not isinstance(ph, str):
                    continue
                d = _digits(ph)
                if len(d) < 7:
                    continue
                stmt = (
                    select(BrokerContact.broker_id)
                    .where(
                        BrokerContact.tenant_id == tenant_id,
                        BrokerContact.is_active.is_(True),
                        or_(
                            BrokerContact.phone.ilike(f"%{d}%"),
                            BrokerContact.fax.ilike(f"%{d}%"),
                        ),
                    )
                    .limit(5)
                )
                for bid in list((await db.execute(stmt)).scalars().all()):
                    out.append({"matched_by": "contact_phone", "broker_id": int(bid), "value": d, "confidence": "low"})

        # 4) Alias/name (soft, avoids fuzzy matching for now)
        if isinstance(name, str) and name.strip():
            try:
                an = normalize_alias(name)
            except Exception:
                an = None
            if an:
                stmt = (
                    select(BrokerAlias.broker_id)
                    .where(
                        BrokerAlias.tenant_id == tenant_id,
                        BrokerAlias.is_active.is_(True),
                        BrokerAlias.alias == an,
                    )
                    .limit(5)
                )
                for bid in list((await db.execute(stmt)).scalars().all()):
                    out.append({"matched_by": "alias", "broker_id": int(bid), "value": name, "confidence": "medium"})

    # Hydrate broker display names for unique broker_ids we found
    broker_ids = sorted({int(x["broker_id"]) for x in out if "broker_id" in x and str(x["broker_id"]).isdigit()})[:50]
    if broker_ids:
        rows = list(
            (await db.execute(select(Broker).where(Broker.tenant_id == tenant_id, Broker.id.in_(broker_ids)))).scalars().all()
        )
        by_id = {r.id: r for r in rows}
        for rec in out:
            bid = rec.get("broker_id")
            if isinstance(bid, int) and bid in by_id:
                br = by_id[bid]
                rec.setdefault("broker_display", br.display_name or br.legal_name or br.name)
                rec.setdefault("mc_number", br.mc_number)
                rec.setdefault("dot_number", br.dot_number)

    return out[:200]

