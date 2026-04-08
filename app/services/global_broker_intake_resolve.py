"""Read-only global booking-broker resolution (platform DB, approved rows only)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.global_booking_broker import (
    GlobalBookingBroker,
    GlobalBookingBrokerAlias,
    GlobalBookingBrokerDomain,
    GlobalBookingBrokerKnownSender,
)
from app.services.broker_intake_resolve import _result_from_match_rows
from app.utils.broker_identity import (
    email_local_part,
    normalize_alias,
    normalize_dot_number_digits,
    normalize_domain,
    normalize_known_sender_email,
    normalize_mc_number_digits,
    parsed_from_display_and_email,
)

_GLOBAL_LABEL = func.coalesce(
    GlobalBookingBroker.display_name,
    GlobalBookingBroker.legal_name,
    GlobalBookingBroker.name,
)


@dataclass(frozen=True)
class GlobalBrokerIntakeMatch:
    global_broker_id: int | None
    broker_label: str | None
    match_method: str | None  # global_exact_known_sender | global_domain | global_alias | global_exact_mc*
    ambiguous: bool = False


def _broker_digits(value: str | None) -> str:
    if not value:
        return ""
    return "".join(c for c in str(value) if c.isdigit())


async def resolve_global_broker_by_mc_dot(
    platform_db: AsyncSession,
    mc_raw: str | None,
    dot_raw: str | None,
) -> GlobalBrokerIntakeMatch:
    """
    Tier **D**: exact normalized MC and/or USDOT against **approved** global rows only.
    Intended for supplemental text (PDF/email), not header identity alone.
    """
    mc_norm = normalize_mc_number_digits(mc_raw)
    dot_norm = normalize_dot_number_digits(dot_raw)
    if not mc_norm and not dot_norm:
        return GlobalBrokerIntakeMatch(None, None, None)

    stmt = (
        select(GlobalBookingBroker.id, _GLOBAL_LABEL, GlobalBookingBroker.mc_number, GlobalBookingBroker.dot_number)
        .where(GlobalBookingBroker.canonical_status == "approved")
        .order_by(GlobalBookingBroker.id.asc())
    )
    rows = (await platform_db.execute(stmt)).all()

    mc_ids: set[int] = set()
    dot_ids: set[int] = set()
    for bid, _lbl, mc_col, dot_col in rows:
        if mc_norm and _broker_digits(mc_col) == mc_norm:
            mc_ids.add(int(bid))
        if dot_norm and _broker_digits(dot_col) == dot_norm:
            dot_ids.add(int(bid))

    if mc_norm:
        if len(mc_ids) > 1:
            return GlobalBrokerIntakeMatch(None, None, None, ambiguous=True)
    if dot_norm:
        if len(dot_ids) > 1:
            return GlobalBrokerIntakeMatch(None, None, None, ambiguous=True)

    if mc_norm and dot_norm:
        m_id = next(iter(mc_ids)) if mc_ids else None
        d_id = next(iter(dot_ids)) if dot_ids else None
        if m_id and d_id and m_id != d_id:
            return GlobalBrokerIntakeMatch(None, None, None, ambiguous=True)
        chosen = m_id or d_id
        if chosen is None:
            return GlobalBrokerIntakeMatch(None, None, None)
        lbl_row = next((r for r in rows if int(r[0]) == chosen), None)
        label = str(lbl_row[1]) if lbl_row and lbl_row[1] is not None else None
        method = "global_exact_mc_dot" if m_id and d_id else ("global_exact_mc" if m_id else "global_exact_dot")
        return GlobalBrokerIntakeMatch(chosen, label, method, ambiguous=False)

    if mc_norm:
        if not mc_ids:
            return GlobalBrokerIntakeMatch(None, None, None)
        bid = next(iter(mc_ids))
        lbl_row = next((r for r in rows if int(r[0]) == bid), None)
        label = str(lbl_row[1]) if lbl_row and lbl_row[1] is not None else None
        return GlobalBrokerIntakeMatch(bid, label, "global_exact_mc", ambiguous=False)

    if dot_norm:
        if not dot_ids:
            return GlobalBrokerIntakeMatch(None, None, None)
        bid = next(iter(dot_ids))
        lbl_row = next((r for r in rows if int(r[0]) == bid), None)
        label = str(lbl_row[1]) if lbl_row and lbl_row[1] is not None else None
        return GlobalBrokerIntakeMatch(bid, label, "global_exact_dot", ambiguous=False)

    return GlobalBrokerIntakeMatch(None, None, None)


async def resolve_global_broker_for_intake_from_header(
    platform_db: AsyncSession,
    from_header: str | None,
) -> GlobalBrokerIntakeMatch:
    """
    Deterministic global match: known sender → domain → strict alias (approved brokers only).
    """
    hdr = (from_header or "").strip()
    if not hdr:
        return GlobalBrokerIntakeMatch(None, None, None)

    display, email_addr = parsed_from_display_and_email(hdr)
    approved = GlobalBookingBroker.canonical_status == "approved"

    if email_addr:
        try:
            em_norm = normalize_known_sender_email(email_addr)
        except ValueError:
            em_norm = None
        if em_norm:
            raw_rows = (
                await platform_db.execute(
                    select(GlobalBookingBroker.id, _GLOBAL_LABEL)
                    .join(
                        GlobalBookingBrokerKnownSender,
                        GlobalBookingBrokerKnownSender.global_broker_id == GlobalBookingBroker.id,
                    )
                    .where(
                        approved,
                        GlobalBookingBrokerKnownSender.email_normalized == em_norm,
                        GlobalBookingBrokerKnownSender.is_active.is_(True),
                    )
                )
            ).all()
            rows = [(r[0], r[1], False) for r in raw_rows]
            got = _result_from_match_rows(rows, "global_exact_known_sender")
            if got.broker_id is not None or got.ambiguous:
                return GlobalBrokerIntakeMatch(
                    got.broker_id,
                    got.broker_label,
                    got.match_method,
                    ambiguous=got.ambiguous,
                )

        try:
            dom = normalize_domain(email_addr.split("@", 1)[1])
        except (ValueError, IndexError):
            dom = None
        if dom:
            raw_rows = (
                await platform_db.execute(
                    select(GlobalBookingBroker.id, _GLOBAL_LABEL)
                    .join(GlobalBookingBrokerDomain, GlobalBookingBrokerDomain.global_broker_id == GlobalBookingBroker.id)
                    .where(
                        approved,
                        GlobalBookingBrokerDomain.domain == dom,
                        GlobalBookingBrokerDomain.is_active.is_(True),
                    )
                )
            ).all()
            rows = [(r[0], r[1], False) for r in raw_rows]
            got = _result_from_match_rows(rows, "global_domain")
            if got.broker_id is not None or got.ambiguous:
                return GlobalBrokerIntakeMatch(
                    got.broker_id,
                    got.broker_label,
                    got.match_method,
                    ambiguous=got.ambiguous,
                )

    candidates: list[str] = []
    if display:
        try:
            candidates.append(normalize_alias(display))
        except ValueError:
            pass
    if email_addr:
        try:
            candidates.append(normalize_alias(email_addr))
        except ValueError:
            pass
        local = email_local_part(email_addr)
        if local:
            try:
                candidates.append(normalize_alias(local))
            except ValueError:
                pass

    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)

    for cand in ordered:
        raw_rows = (
            await platform_db.execute(
                select(GlobalBookingBroker.id, _GLOBAL_LABEL)
                .join(GlobalBookingBrokerAlias, GlobalBookingBrokerAlias.global_broker_id == GlobalBookingBroker.id)
                .where(
                    approved,
                    GlobalBookingBrokerAlias.alias == cand,
                    GlobalBookingBrokerAlias.is_active.is_(True),
                )
            )
        ).all()
        rows = [(r[0], r[1], False) for r in raw_rows]
        got = _result_from_match_rows(rows, "global_alias")
        if got.ambiguous:
            return GlobalBrokerIntakeMatch(None, None, None, ambiguous=True)
        if got.broker_id is not None:
            return GlobalBrokerIntakeMatch(got.broker_id, got.broker_label, got.match_method, ambiguous=False)

    return GlobalBrokerIntakeMatch(None, None, None)
