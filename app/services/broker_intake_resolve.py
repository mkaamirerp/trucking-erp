"""Deterministic broker resolution for email intake (known sender → domain → strict alias)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker, BrokerAlias, BrokerDomain, BrokerKnownSender
from app.models.email_ingestion import EmailMessage
from app.utils.broker_identity import (
    email_local_part,
    normalize_alias,
    normalize_domain,
    normalize_known_sender_email,
    parsed_from_display_and_email,
)

_BROKER_LABEL = func.coalesce(Broker.display_name, Broker.legal_name, Broker.name)


async def fetch_latest_inbound_from_header(db: AsyncSession, tenant_id: int, thread_id: int) -> str | None:
    """Best-effort From line for intake: prefer inbound messages, latest by received/sent/id."""
    stmt = (
        select(EmailMessage.from_email, EmailMessage.direction)
        .where(EmailMessage.tenant_id == tenant_id, EmailMessage.thread_id == thread_id)
        .order_by(
            EmailMessage.received_at.desc().nulls_last(),
            EmailMessage.sent_at.desc().nulls_last(),
            EmailMessage.id.desc(),
        )
    )
    rows = (await db.execute(stmt)).all()
    for from_email, direction in rows:
        if direction == "inbound" and from_email and from_email.strip():
            return from_email.strip()
    for from_email, _ in rows:
        if from_email and from_email.strip():
            return from_email.strip()
    return None


async def resolve_broker_for_intake_from_header(
    db: AsyncSession,
    tenant_id: int,
    from_header: str | None,
) -> tuple[int | None, str | None]:
    """
    Deterministic: active broker + active identity rows only.
    Precedence: exact known sender email → domain match on From → strict alias candidates.
    Returns (broker_id, broker_display_label) or (None, None).
    """
    hdr = (from_header or "").strip()
    if not hdr:
        return None, None

    display, email_addr = parsed_from_display_and_email(hdr)

    if email_addr:
        try:
            em_norm = normalize_known_sender_email(email_addr)
        except ValueError:
            em_norm = None
        if em_norm:
            row = (
                await db.execute(
                    select(Broker.id, _BROKER_LABEL)
                    .join(BrokerKnownSender, BrokerKnownSender.broker_id == Broker.id)
                    .where(
                        Broker.tenant_id == tenant_id,
                        Broker.is_active.is_(True),
                        BrokerKnownSender.tenant_id == tenant_id,
                        BrokerKnownSender.email_normalized == em_norm,
                        BrokerKnownSender.is_active.is_(True),
                    )
                    .limit(1)
                )
            ).first()
            if row:
                return int(row[0]), str(row[1])

        try:
            dom = normalize_domain(email_addr.split("@", 1)[1])
        except (ValueError, IndexError):
            dom = None
        if dom:
            row = (
                await db.execute(
                    select(Broker.id, _BROKER_LABEL)
                    .join(BrokerDomain, BrokerDomain.broker_id == Broker.id)
                    .where(
                        Broker.tenant_id == tenant_id,
                        Broker.is_active.is_(True),
                        BrokerDomain.tenant_id == tenant_id,
                        BrokerDomain.domain == dom,
                        BrokerDomain.is_active.is_(True),
                    )
                    .limit(1)
                )
            ).first()
            if row:
                return int(row[0]), str(row[1])

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
        row = (
            await db.execute(
                select(Broker.id, _BROKER_LABEL)
                .join(BrokerAlias, BrokerAlias.broker_id == Broker.id)
                .where(
                    Broker.tenant_id == tenant_id,
                    Broker.is_active.is_(True),
                    BrokerAlias.tenant_id == tenant_id,
                    BrokerAlias.alias == cand,
                    BrokerAlias.is_active.is_(True),
                )
                .limit(1)
            )
        ).first()
        if row:
            return int(row[0]), str(row[1])

    return None, None
