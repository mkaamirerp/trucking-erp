"""Deterministic broker resolution for email intake (known sender → domain → strict alias)."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class BrokerIntakeResolveResult:
    """Result of header-based broker resolution.

    ``ambiguous`` — more than one non-blocked broker at a tier; route to review.
    ``blocked_match`` — at least one broker matched at a tier but all matching brokers
    have ``intake_blocked``; explicit policy outcome (not silent non-resolution).
    ``global_match_no_workspace`` — global reference matched but tenant policy disabled auto-create.
    ``is_global_ambiguous`` — tie in global reference tier (tenant had no decisive match).
    ``global_tier_d_requires_review`` — MC/DOT-only global match; no auto workspace row in this path.
    ``global_identity_disagreement`` — header-based global vs supplemental MC/DOT global disagree.
    ``intake_signal_conflict`` — tenant broker (linked to a global id) vs supplemental MC/DOT global disagree.
    """

    broker_id: int | None
    broker_label: str | None
    match_method: str | None  # exact_known_sender | domain | alias | global_*
    ambiguous: bool = False
    blocked_match: bool = False
    platform_global_broker_id: int | None = None
    global_match_no_workspace: bool = False
    is_global_ambiguous: bool = False
    global_tier_d_requires_review: bool = False
    global_identity_disagreement: bool = False
    intake_signal_conflict: bool = False


def confidence_tier_for_match_method(method: str | None) -> str | None:
    if method == "exact_known_sender":
        return "A"
    if method == "domain":
        return "B"
    if method == "alias":
        return "C"
    if method == "global_exact_known_sender":
        return "A"
    if method == "global_domain":
        return "B"
    if method == "global_alias":
        return "C"
    if method in ("global_exact_mc", "global_exact_dot", "global_exact_mc_dot"):
        return "D"
    if method == "fallback_tenant_default":
        return "D"
    return None


def _normalize_match_rows(rows: list) -> list[tuple[int, str, bool]]:
    out: list[tuple[int, str, bool]] = []
    for t in rows:
        if len(t) == 2:
            out.append((int(t[0]), str(t[1]), False))
        else:
            out.append((int(t[0]), str(t[1]), bool(t[2])))
    return out


def _result_from_match_rows(rows: list, match_method: str) -> BrokerIntakeResolveResult:
    """(broker_id, label) or (broker_id, label, intake_blocked) per row."""
    norm = _normalize_match_rows(rows)
    by_id: dict[int, tuple[str, bool]] = {}
    for bid, label, blocked in norm:
        by_id[int(bid)] = (label, bool(blocked))
    non_blocked = sorted(i for i, (_, ib) in by_id.items() if not ib)
    blocked_only = sorted(i for i, (_, ib) in by_id.items() if ib)
    if len(non_blocked) > 1:
        return BrokerIntakeResolveResult(None, None, None, ambiguous=True)
    if len(non_blocked) == 1:
        bid = non_blocked[0]
        return BrokerIntakeResolveResult(bid, by_id[bid][0], match_method, ambiguous=False)
    if blocked_only:
        return BrokerIntakeResolveResult(None, None, None, blocked_match=True)
    return BrokerIntakeResolveResult(None, None, None)


def explanation_for_match_method(method: str | None) -> str | None:
    if method == "exact_known_sender":
        return "Matched broker using exact normalized From address (known sender list)."
    if method == "domain":
        return "Matched broker using email domain."
    if method == "alias":
        return "Matched broker using strict alias."
    if method == "global_exact_known_sender":
        return "Matched platform global booking broker (approved known sender list)."
    if method == "global_domain":
        return "Matched platform global booking broker (approved email domain)."
    if method == "global_alias":
        return "Matched platform global booking broker (approved strict alias)."
    if method == "global_exact_mc":
        return "Matched platform global booking broker (exact MC number digits from supplemental text)."
    if method == "global_exact_dot":
        return "Matched platform global booking broker (exact USDOT digits from supplemental text)."
    if method == "global_exact_mc_dot":
        return "Matched platform global booking broker (exact MC and USDOT digits from supplemental text)."
    if method == "fallback_tenant_default":
        return "No header match; applied tenant default booking broker fallback (to be data-driven)."
    return None


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
) -> BrokerIntakeResolveResult:
    """
    Deterministic: active broker + active identity rows. ``intake_blocked`` brokers never win;
    if only blocked broker(s) match a tier, returns ``blocked_match=True``.

    Precedence: exact known sender email → domain match on From → strict alias candidates.

    If more than one distinct **non-blocked** broker matches a tier, returns ``ambiguous=True``.
    """
    hdr = (from_header or "").strip()
    if not hdr:
        return BrokerIntakeResolveResult(None, None, None)

    display, email_addr = parsed_from_display_and_email(hdr)

    broker_scope = (Broker.tenant_id == tenant_id, Broker.is_active.is_(True))

    if email_addr:
        try:
            em_norm = normalize_known_sender_email(email_addr)
        except ValueError:
            em_norm = None
        if em_norm:
            rows = (
                await db.execute(
                    select(Broker.id, _BROKER_LABEL, Broker.intake_blocked)
                    .join(BrokerKnownSender, BrokerKnownSender.broker_id == Broker.id)
                    .where(
                        *broker_scope,
                        BrokerKnownSender.tenant_id == tenant_id,
                        BrokerKnownSender.email_normalized == em_norm,
                        BrokerKnownSender.is_active.is_(True),
                    )
                )
            ).all()
            got = _result_from_match_rows(rows, "exact_known_sender")
            if got.broker_id is not None or got.ambiguous or got.blocked_match:
                return got

        try:
            dom = normalize_domain(email_addr.split("@", 1)[1])
        except (ValueError, IndexError):
            dom = None
        if dom:
            rows = (
                await db.execute(
                    select(Broker.id, _BROKER_LABEL, Broker.intake_blocked)
                    .join(BrokerDomain, BrokerDomain.broker_id == Broker.id)
                    .where(
                        *broker_scope,
                        BrokerDomain.tenant_id == tenant_id,
                        BrokerDomain.domain == dom,
                        BrokerDomain.is_active.is_(True),
                    )
                )
            ).all()
            got = _result_from_match_rows(rows, "domain")
            if got.broker_id is not None or got.ambiguous or got.blocked_match:
                return got

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
        rows = (
            await db.execute(
                select(Broker.id, _BROKER_LABEL, Broker.intake_blocked)
                .join(BrokerAlias, BrokerAlias.broker_id == Broker.id)
                .where(
                    *broker_scope,
                    BrokerAlias.tenant_id == tenant_id,
                    BrokerAlias.alias == cand,
                    BrokerAlias.is_active.is_(True),
                )
            )
        ).all()
        got = _result_from_match_rows(rows, "alias")
        if got.ambiguous or got.blocked_match:
            return got
        if got.broker_id is not None:
            return got

    return BrokerIntakeResolveResult(None, None, None)
