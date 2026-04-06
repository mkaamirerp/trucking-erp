from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import Select, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker, BrokerAlias, BrokerContact, BrokerDomain, BrokerKnownSender
from app.models.load import Load
from app.schemas.broker import (
    BrokerAliasCreate,
    BrokerAliasOut,
    BrokerAliasUpdate,
    BrokerContactCreateBody,
    BrokerContactOut,
    BrokerContactUpdate,
    BrokerCreate,
    BrokerDomainCreate,
    BrokerDomainOut,
    BrokerDomainUpdate,
    BrokerKnownSenderCreate,
    BrokerKnownSenderOut,
    BrokerKnownSenderUpdate,
    BrokerResponse,
    BrokerUpdate,
    BrokerWorkspaceOut,
)
from app.utils.broker_identity import (
    normalize_alias,
    normalize_domain,
    normalize_known_sender_email,
)
from app.utils.pagination import paginate

SortKey = Literal["name_asc", "name_desc", "id_desc"]

_REFERENCED_DETAIL: dict[str, Any] = {
    "code": "BROKER_REFERENCED_BY_LOADS",
    "message": "Broker is referenced by one or more loads and cannot be deleted.",
}

_BROKER_SORT_LABEL = func.coalesce(Broker.display_name, Broker.legal_name, Broker.name)


def _domain_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "DOMAIN_CONFLICT",
            "message": "This domain is already assigned to an active broker for this workspace.",
        },
    )


def _alias_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "ALIAS_CONFLICT",
            "message": "This alias is already assigned to an active broker for this workspace.",
        },
    )


def _known_sender_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "KNOWN_SENDER_CONFLICT",
            "message": "This sender email is already assigned to an active broker for this workspace.",
        },
    )


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate == "23505":
        return True
    s = str(orig) if orig else str(exc)
    return "23505" in s or "UniqueViolationError" in s or "unique constraint" in s.lower()


def _prepare_broker_create_dict(data: BrokerCreate) -> dict[str, Any]:
    raw = data.model_dump(exclude_unset=False)
    name = (raw.get("name") or "").strip()
    disp = (raw.get("display_name") or "").strip()
    legal = (raw.get("legal_name") or "").strip()
    if not disp and name:
        disp = name[:255]
    if not legal and name:
        legal = name[:500]
    if not disp and legal:
        disp = legal[:255]
    if not legal and disp:
        legal = disp[:500]
    list_name = (disp or legal or name or "Broker").strip()[:255]
    raw["name"] = list_name
    raw["display_name"] = disp or None
    raw["legal_name"] = legal or None
    col_names = {c.name for c in Broker.__table__.columns}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k in col_names and k not in ("id", "tenant_id", "created_at", "updated_at", "is_active", "archived_at"):
            out[k] = v
    return out


def _sync_legacy_name_row(broker: Broker) -> None:
    label = (broker.display_name or broker.legal_name or broker.name or "").strip()
    if label:
        broker.name = label[:255]


async def create_broker(db: AsyncSession, tenant_id: int, payload: BrokerCreate) -> Broker:
    row_data = _prepare_broker_create_dict(payload)
    broker = Broker(
        tenant_id=tenant_id,
        is_active=True,
        archived_at=None,
        **row_data,
    )
    _sync_legacy_name_row(broker)
    db.add(broker)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(broker)
    return broker


async def _broker_exists(db: AsyncSession, tenant_id: int, broker_id: int) -> bool:
    bid = await db.scalar(select(Broker.id).where(Broker.id == broker_id, Broker.tenant_id == tenant_id))
    return bid is not None


async def get_broker(db: AsyncSession, tenant_id: int, broker_id: int) -> Broker | None:
    result = await db.execute(select(Broker).where(Broker.id == broker_id, Broker.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def get_broker_workspace(
    db: AsyncSession,
    tenant_id: int,
    broker_id: int,
    *,
    include_archived: bool = True,
) -> BrokerWorkspaceOut | None:
    broker = await get_broker(db, tenant_id, broker_id)
    if not broker:
        return None

    def _contact_stmt():
        st = select(BrokerContact).where(
            BrokerContact.tenant_id == tenant_id,
            BrokerContact.broker_id == broker_id,
        )
        if not include_archived:
            st = st.where(BrokerContact.is_active.is_(True))
        return st.order_by(BrokerContact.is_primary.desc(), BrokerContact.id.asc())

    def _domain_stmt():
        st = select(BrokerDomain).where(
            BrokerDomain.tenant_id == tenant_id,
            BrokerDomain.broker_id == broker_id,
        )
        if not include_archived:
            st = st.where(BrokerDomain.is_active.is_(True))
        return st.order_by(BrokerDomain.is_primary.desc(), BrokerDomain.id.asc())

    def _sender_stmt():
        st = select(BrokerKnownSender).where(
            BrokerKnownSender.tenant_id == tenant_id,
            BrokerKnownSender.broker_id == broker_id,
        )
        if not include_archived:
            st = st.where(BrokerKnownSender.is_active.is_(True))
        return st.order_by(BrokerKnownSender.id.asc())

    contacts = list((await db.execute(_contact_stmt())).scalars().all())
    domains = list((await db.execute(_domain_stmt())).scalars().all())
    alias_stmt = select(BrokerAlias).where(
        BrokerAlias.tenant_id == tenant_id,
        BrokerAlias.broker_id == broker_id,
    )
    if not include_archived:
        alias_stmt = alias_stmt.where(BrokerAlias.is_active.is_(True))
    alias_stmt = alias_stmt.order_by(BrokerAlias.id.asc())
    aliases = list((await db.execute(alias_stmt)).scalars().all())
    senders = list((await db.execute(_sender_stmt())).scalars().all())

    return BrokerWorkspaceOut(
        broker=BrokerResponse.model_validate(broker),
        contacts=[BrokerContactOut.model_validate(c) for c in contacts],
        domains=[BrokerDomainOut.model_validate(d) for d in domains],
        aliases=[BrokerAliasOut.model_validate(a) for a in aliases],
        known_senders=[BrokerKnownSenderOut.model_validate(s) for s in senders],
    )


async def list_brokers(
    db: AsyncSession,
    tenant_id: int,
    *,
    page: int = 1,
    size: int = 25,
    q: str | None = None,
    include_archived: bool = False,
    sort: SortKey = "name_asc",
):
    stmt: Select[Any] = select(Broker).where(Broker.tenant_id == tenant_id)
    if not include_archived:
        stmt = stmt.where(Broker.is_active.is_(True))
    text = (q or "").strip()
    if text:
        pat = f"%{text}%"
        dom_exists = exists().where(
            BrokerDomain.broker_id == Broker.id,
            BrokerDomain.tenant_id == tenant_id,
            BrokerDomain.is_active.is_(True),
            BrokerDomain.domain.ilike(pat),
        )
        alias_exists = exists().where(
            BrokerAlias.broker_id == Broker.id,
            BrokerAlias.tenant_id == tenant_id,
            BrokerAlias.is_active.is_(True),
            BrokerAlias.alias.ilike(pat),
        )
        sender_exists = exists().where(
            BrokerKnownSender.broker_id == Broker.id,
            BrokerKnownSender.tenant_id == tenant_id,
            BrokerKnownSender.is_active.is_(True),
            BrokerKnownSender.email_normalized.ilike(pat),
        )
        contact_exists = exists().where(
            BrokerContact.broker_id == Broker.id,
            BrokerContact.tenant_id == tenant_id,
            BrokerContact.is_active.is_(True),
            or_(
                BrokerContact.name.ilike(pat),
                BrokerContact.first_name.ilike(pat),
                BrokerContact.last_name.ilike(pat),
                BrokerContact.email.ilike(pat),
                BrokerContact.phone.ilike(pat),
                BrokerContact.role.ilike(pat),
                BrokerContact.department.ilike(pat),
            ),
        )
        stmt = stmt.where(
            or_(
                _BROKER_SORT_LABEL.ilike(pat),
                Broker.name.ilike(pat),
                Broker.legal_name.ilike(pat),
                Broker.display_name.ilike(pat),
                Broker.mc_number.ilike(pat),
                Broker.dot_number.ilike(pat),
                Broker.scac.ilike(pat),
                Broker.phone.ilike(pat),
                Broker.phone_secondary.ilike(pat),
                Broker.email.ilike(pat),
                Broker.email_secondary.ilike(pat),
                Broker.website.ilike(pat),
                dom_exists,
                alias_exists,
                sender_exists,
                contact_exists,
            )
        )
    if sort == "name_asc":
        stmt = stmt.order_by(_BROKER_SORT_LABEL.asc(), Broker.id.asc())
    elif sort == "name_desc":
        stmt = stmt.order_by(_BROKER_SORT_LABEL.desc(), Broker.id.desc())
    else:
        stmt = stmt.order_by(Broker.id.desc())
    return await paginate(db, stmt, page=page, size=size)


async def update_broker(db: AsyncSession, tenant_id: int, broker_id: int, payload: BrokerUpdate) -> Broker:
    broker = await get_broker(db, tenant_id, broker_id)
    if not broker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(broker, key, value)
    _sync_legacy_name_row(broker)

    await db.commit()
    await db.refresh(broker)
    return broker


async def archive_broker(db: AsyncSession, tenant_id: int, broker_id: int) -> Broker:
    broker = await get_broker(db, tenant_id, broker_id)
    if not broker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    now = datetime.now(timezone.utc)
    if not broker.is_active:
        return broker
    broker.is_active = False
    broker.archived_at = now
    await db.execute(
        update(BrokerDomain)
        .where(
            BrokerDomain.tenant_id == tenant_id,
            BrokerDomain.broker_id == broker_id,
            BrokerDomain.is_active.is_(True),
        )
        .values(is_active=False, archived_at=now)
    )
    await db.execute(
        update(BrokerAlias)
        .where(
            BrokerAlias.tenant_id == tenant_id,
            BrokerAlias.broker_id == broker_id,
            BrokerAlias.is_active.is_(True),
        )
        .values(is_active=False, archived_at=now)
    )
    await db.execute(
        update(BrokerKnownSender)
        .where(
            BrokerKnownSender.tenant_id == tenant_id,
            BrokerKnownSender.broker_id == broker_id,
            BrokerKnownSender.is_active.is_(True),
        )
        .values(is_active=False, archived_at=now)
    )
    await db.commit()
    await db.refresh(broker)
    return broker


async def unarchive_broker(db: AsyncSession, tenant_id: int, broker_id: int) -> Broker:
    broker = await get_broker(db, tenant_id, broker_id)
    if not broker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    if broker.is_active and broker.archived_at is None:
        return broker
    broker.is_active = True
    broker.archived_at = None
    await db.commit()
    await db.refresh(broker)
    return broker


async def delete_broker(db: AsyncSession, tenant_id: int, broker_id: int) -> None:
    broker = await get_broker(db, tenant_id, broker_id)
    if not broker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    cnt = await db.scalar(
        select(func.count()).select_from(Load).where(Load.tenant_id == tenant_id, Load.broker_id == broker_id)
    )
    if cnt and int(cnt) > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_REFERENCED_DETAIL)
    await db.delete(broker)
    await db.commit()


# --- Contacts ---


async def list_contacts(
    db: AsyncSession,
    tenant_id: int,
    broker_id: int,
    *,
    page: int = 1,
    size: int = 25,
    include_archived: bool = False,
):
    if not await _broker_exists(db, tenant_id, broker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    stmt = select(BrokerContact).where(
        BrokerContact.tenant_id == tenant_id,
        BrokerContact.broker_id == broker_id,
    )
    if not include_archived:
        stmt = stmt.where(BrokerContact.is_active.is_(True))
    stmt = stmt.order_by(BrokerContact.is_primary.desc(), BrokerContact.id.asc())
    return await paginate(db, stmt, page=page, size=size)


async def get_contact(db: AsyncSession, tenant_id: int, broker_id: int, contact_id: int) -> BrokerContact | None:
    return await db.scalar(
        select(BrokerContact).where(
            BrokerContact.id == contact_id,
            BrokerContact.tenant_id == tenant_id,
            BrokerContact.broker_id == broker_id,
        )
    )


async def _clear_other_primary_contacts(
    db: AsyncSession, tenant_id: int, broker_id: int, except_id: int
) -> None:
    await db.execute(
        update(BrokerContact)
        .where(
            BrokerContact.tenant_id == tenant_id,
            BrokerContact.broker_id == broker_id,
            BrokerContact.id != except_id,
            BrokerContact.is_active.is_(True),
        )
        .values(is_primary=False)
    )


async def create_contact(
    db: AsyncSession, tenant_id: int, broker_id: int, payload: BrokerContactCreateBody
) -> BrokerContact:
    if not await _broker_exists(db, tenant_id, broker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    row = BrokerContact(
        **payload.model_dump(),
        tenant_id=tenant_id,
        broker_id=broker_id,
        is_active=True,
        archived_at=None,
    )
    db.add(row)
    await db.flush()
    if row.is_primary:
        await _clear_other_primary_contacts(db, tenant_id, broker_id, row.id)
    await db.commit()
    await db.refresh(row)
    return row


async def update_contact(
    db: AsyncSession, tenant_id: int, broker_id: int, contact_id: int, payload: BrokerContactUpdate
) -> BrokerContact:
    row = await get_contact(db, tenant_id, broker_id, contact_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker contact not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    await db.flush()
    if row.is_primary:
        await _clear_other_primary_contacts(db, tenant_id, broker_id, row.id)
    await db.commit()
    await db.refresh(row)
    return row


async def archive_contact(db: AsyncSession, tenant_id: int, broker_id: int, contact_id: int) -> BrokerContact:
    row = await get_contact(db, tenant_id, broker_id, contact_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker contact not found")
    if not row.is_active:
        return row
    now = datetime.now(timezone.utc)
    row.is_active = False
    row.archived_at = now
    await db.commit()
    await db.refresh(row)
    return row


async def unarchive_contact(db: AsyncSession, tenant_id: int, broker_id: int, contact_id: int) -> BrokerContact:
    row = await get_contact(db, tenant_id, broker_id, contact_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker contact not found")
    if row.is_active:
        return row
    row.is_active = True
    row.archived_at = None
    await db.commit()
    await db.refresh(row)
    return row


# --- Domains ---


async def _clear_other_primary_domains(
    db: AsyncSession, tenant_id: int, broker_id: int, except_id: int
) -> None:
    await db.execute(
        update(BrokerDomain)
        .where(
            BrokerDomain.tenant_id == tenant_id,
            BrokerDomain.broker_id == broker_id,
            BrokerDomain.id != except_id,
            BrokerDomain.is_active.is_(True),
        )
        .values(is_primary=False)
    )


async def list_domains(
    db: AsyncSession,
    tenant_id: int,
    broker_id: int,
    *,
    page: int = 1,
    size: int = 25,
    include_archived: bool = False,
):
    if not await _broker_exists(db, tenant_id, broker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    stmt = select(BrokerDomain).where(
        BrokerDomain.tenant_id == tenant_id,
        BrokerDomain.broker_id == broker_id,
    )
    if not include_archived:
        stmt = stmt.where(BrokerDomain.is_active.is_(True))
    stmt = stmt.order_by(BrokerDomain.is_primary.desc(), BrokerDomain.id.asc())
    return await paginate(db, stmt, page=page, size=size)


async def get_domain(db: AsyncSession, tenant_id: int, broker_id: int, domain_id: int) -> BrokerDomain | None:
    return await db.scalar(
        select(BrokerDomain).where(
            BrokerDomain.id == domain_id,
            BrokerDomain.tenant_id == tenant_id,
            BrokerDomain.broker_id == broker_id,
        )
    )


async def create_domain(
    db: AsyncSession, tenant_id: int, broker_id: int, payload: BrokerDomainCreate
) -> BrokerDomain:
    if not await _broker_exists(db, tenant_id, broker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    try:
        dom = normalize_domain(payload.domain)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid domain") from None
    row = BrokerDomain(
        tenant_id=tenant_id,
        broker_id=broker_id,
        domain=dom,
        is_primary=payload.is_primary,
        notes=payload.notes,
        is_active=True,
        archived_at=None,
    )
    db.add(row)
    try:
        await db.flush()
        if row.is_primary:
            await _clear_other_primary_domains(db, tenant_id, broker_id, row.id)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if _is_unique_violation(e):
            raise _domain_conflict() from e
        raise
    await db.refresh(row)
    return row


async def update_domain(
    db: AsyncSession, tenant_id: int, broker_id: int, domain_id: int, payload: BrokerDomainUpdate
) -> BrokerDomain:
    row = await get_domain(db, tenant_id, broker_id, domain_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker domain not found")
    data = payload.model_dump(exclude_unset=True)
    if "domain" in data:
        try:
            row.domain = normalize_domain(data["domain"])
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid domain") from None
    if "is_primary" in data and data["is_primary"] is not None:
        row.is_primary = bool(data["is_primary"])
    if "notes" in data:
        row.notes = data["notes"]
    try:
        await db.flush()
        if row.is_primary:
            await _clear_other_primary_domains(db, tenant_id, broker_id, row.id)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if _is_unique_violation(e):
            raise _domain_conflict() from e
        raise
    await db.refresh(row)
    return row


async def archive_domain(db: AsyncSession, tenant_id: int, broker_id: int, domain_id: int) -> BrokerDomain:
    row = await get_domain(db, tenant_id, broker_id, domain_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker domain not found")
    if not row.is_active:
        return row
    now = datetime.now(timezone.utc)
    row.is_active = False
    row.archived_at = now
    await db.commit()
    await db.refresh(row)
    return row


async def unarchive_domain(db: AsyncSession, tenant_id: int, broker_id: int, domain_id: int) -> BrokerDomain:
    row = await get_domain(db, tenant_id, broker_id, domain_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker domain not found")
    if row.is_active:
        return row
    row.is_active = True
    row.archived_at = None
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if _is_unique_violation(e):
            raise _domain_conflict() from e
        raise
    await db.refresh(row)
    return row


# --- Aliases ---


async def list_aliases(
    db: AsyncSession,
    tenant_id: int,
    broker_id: int,
    *,
    page: int = 1,
    size: int = 25,
    include_archived: bool = False,
):
    if not await _broker_exists(db, tenant_id, broker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    stmt = select(BrokerAlias).where(
        BrokerAlias.tenant_id == tenant_id,
        BrokerAlias.broker_id == broker_id,
    )
    if not include_archived:
        stmt = stmt.where(BrokerAlias.is_active.is_(True))
    stmt = stmt.order_by(BrokerAlias.id.asc())
    return await paginate(db, stmt, page=page, size=size)


async def get_alias(db: AsyncSession, tenant_id: int, broker_id: int, alias_id: int) -> BrokerAlias | None:
    return await db.scalar(
        select(BrokerAlias).where(
            BrokerAlias.id == alias_id,
            BrokerAlias.tenant_id == tenant_id,
            BrokerAlias.broker_id == broker_id,
        )
    )


async def create_alias(
    db: AsyncSession, tenant_id: int, broker_id: int, payload: BrokerAliasCreate
) -> BrokerAlias:
    if not await _broker_exists(db, tenant_id, broker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    try:
        als = normalize_alias(payload.alias)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid alias") from None
    row = BrokerAlias(
        tenant_id=tenant_id,
        broker_id=broker_id,
        alias=als,
        alias_type=(payload.alias_type or "display")[:32],
        is_active=True,
        archived_at=None,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if _is_unique_violation(e):
            raise _alias_conflict() from e
        raise
    await db.refresh(row)
    return row


async def update_alias(
    db: AsyncSession, tenant_id: int, broker_id: int, alias_id: int, payload: BrokerAliasUpdate
) -> BrokerAlias:
    row = await get_alias(db, tenant_id, broker_id, alias_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker alias not found")
    data = payload.model_dump(exclude_unset=True)
    if "alias" in data:
        try:
            row.alias = normalize_alias(data["alias"])
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid alias") from None
    if "alias_type" in data and data["alias_type"] is not None:
        row.alias_type = str(data["alias_type"])[:32]
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if _is_unique_violation(e):
            raise _alias_conflict() from e
        raise
    await db.refresh(row)
    return row


async def archive_alias(db: AsyncSession, tenant_id: int, broker_id: int, alias_id: int) -> BrokerAlias:
    row = await get_alias(db, tenant_id, broker_id, alias_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker alias not found")
    if not row.is_active:
        return row
    now = datetime.now(timezone.utc)
    row.is_active = False
    row.archived_at = now
    await db.commit()
    await db.refresh(row)
    return row


async def unarchive_alias(db: AsyncSession, tenant_id: int, broker_id: int, alias_id: int) -> BrokerAlias:
    row = await get_alias(db, tenant_id, broker_id, alias_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker alias not found")
    if row.is_active:
        return row
    row.is_active = True
    row.archived_at = None
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if _is_unique_violation(e):
            raise _alias_conflict() from e
        raise
    await db.refresh(row)
    return row


# --- Known senders ---


async def list_known_senders(
    db: AsyncSession,
    tenant_id: int,
    broker_id: int,
    *,
    page: int = 1,
    size: int = 25,
    include_archived: bool = False,
):
    if not await _broker_exists(db, tenant_id, broker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    stmt = select(BrokerKnownSender).where(
        BrokerKnownSender.tenant_id == tenant_id,
        BrokerKnownSender.broker_id == broker_id,
    )
    if not include_archived:
        stmt = stmt.where(BrokerKnownSender.is_active.is_(True))
    stmt = stmt.order_by(BrokerKnownSender.id.asc())
    return await paginate(db, stmt, page=page, size=size)


async def get_known_sender(
    db: AsyncSession, tenant_id: int, broker_id: int, known_sender_id: int
) -> BrokerKnownSender | None:
    return await db.scalar(
        select(BrokerKnownSender).where(
            BrokerKnownSender.id == known_sender_id,
            BrokerKnownSender.tenant_id == tenant_id,
            BrokerKnownSender.broker_id == broker_id,
        )
    )


async def create_known_sender(
    db: AsyncSession, tenant_id: int, broker_id: int, payload: BrokerKnownSenderCreate
) -> BrokerKnownSender:
    if not await _broker_exists(db, tenant_id, broker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    try:
        em = normalize_known_sender_email(str(payload.email))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email") from None
    row = BrokerKnownSender(
        tenant_id=tenant_id,
        broker_id=broker_id,
        email_normalized=em,
        notes=payload.notes,
        is_active=True,
        archived_at=None,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if _is_unique_violation(e):
            raise _known_sender_conflict() from e
        raise
    await db.refresh(row)
    return row


async def update_known_sender(
    db: AsyncSession,
    tenant_id: int,
    broker_id: int,
    known_sender_id: int,
    payload: BrokerKnownSenderUpdate,
) -> BrokerKnownSender:
    row = await get_known_sender(db, tenant_id, broker_id, known_sender_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Known sender not found")
    data = payload.model_dump(exclude_unset=True)
    if "email" in data and data["email"] is not None:
        try:
            row.email_normalized = normalize_known_sender_email(str(data["email"]))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email") from None
    if "notes" in data:
        row.notes = data["notes"]
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if _is_unique_violation(e):
            raise _known_sender_conflict() from e
        raise
    await db.refresh(row)
    return row


async def archive_known_sender(
    db: AsyncSession, tenant_id: int, broker_id: int, known_sender_id: int
) -> BrokerKnownSender:
    row = await get_known_sender(db, tenant_id, broker_id, known_sender_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Known sender not found")
    if not row.is_active:
        return row
    now = datetime.now(timezone.utc)
    row.is_active = False
    row.archived_at = now
    await db.commit()
    await db.refresh(row)
    return row


async def unarchive_known_sender(
    db: AsyncSession, tenant_id: int, broker_id: int, known_sender_id: int
) -> BrokerKnownSender:
    row = await get_known_sender(db, tenant_id, broker_id, known_sender_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Known sender not found")
    if row.is_active:
        return row
    row.is_active = True
    row.archived_at = None
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if _is_unique_violation(e):
            raise _known_sender_conflict() from e
        raise
    await db.refresh(row)
    return row
