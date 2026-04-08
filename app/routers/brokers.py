from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
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
    BrokerSort,
    BrokerUpdate,
    BrokerWorkspaceOut,
)
from app.services import brokers as brokers_service

router = APIRouter(prefix="/brokers", tags=["brokers"])


@router.post("", response_model=BrokerResponse, status_code=status.HTTP_201_CREATED)
async def create_broker(
    payload: BrokerCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.create_broker(db, tenant_id, payload)
    return BrokerResponse.model_validate(row)


@router.get("", response_model=dict)
async def list_brokers(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
    q: Optional[str] = Query(None, max_length=120),
    include_archived: bool = Query(False),
    sort: BrokerSort = Query("name_asc"),
):
    paged = await brokers_service.list_brokers(
        db,
        tenant_id,
        page=page,
        size=size,
        q=q,
        include_archived=include_archived,
        sort=sort,
    )
    items = [BrokerResponse.model_validate(item) for item in paged["items"]]
    return {**paged, "items": items}


@router.post("/{broker_id}/archive", response_model=BrokerResponse)
async def archive_broker(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.archive_broker(db, tenant_id, broker_id)
    return BrokerResponse.model_validate(row)


@router.post("/{broker_id}/unarchive", response_model=BrokerResponse)
async def unarchive_broker(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.unarchive_broker(db, tenant_id, broker_id)
    return BrokerResponse.model_validate(row)


@router.get("/{broker_id}/workspace", response_model=BrokerWorkspaceOut)
async def get_broker_workspace(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    include_archived: bool = Query(True),
):
    ws = await brokers_service.get_broker_workspace(
        db, tenant_id, broker_id, include_archived=include_archived
    )
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    return ws


@router.get("/{broker_id}", response_model=BrokerResponse)
async def get_broker(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    broker = await brokers_service.get_broker(db, tenant_id, broker_id)
    if not broker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    return BrokerResponse.model_validate(broker)


@router.patch("/{broker_id}", response_model=BrokerResponse)
async def update_broker(
    broker_id: int,
    payload: BrokerUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.update_broker(db, tenant_id, broker_id, payload)
    return BrokerResponse.model_validate(row)


@router.delete("/{broker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_broker(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await brokers_service.delete_broker(db, tenant_id, broker_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Contacts ---


@router.get("/{broker_id}/contacts", response_model=dict)
async def list_contacts(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
    include_archived: bool = Query(False),
):
    paged = await brokers_service.list_contacts(
        db, tenant_id, broker_id, page=page, size=size, include_archived=include_archived
    )
    items = [BrokerContactOut.model_validate(x) for x in paged["items"]]
    return {**paged, "items": items}


@router.post(
    "/{broker_id}/contacts",
    response_model=BrokerContactOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_contact(
    broker_id: int,
    payload: BrokerContactCreateBody,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.create_contact(db, tenant_id, broker_id, payload)
    return BrokerContactOut.model_validate(row)


@router.get("/{broker_id}/contacts/{contact_id}", response_model=BrokerContactOut)
async def get_contact(
    broker_id: int,
    contact_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.get_contact(db, tenant_id, broker_id, contact_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker contact not found")
    return BrokerContactOut.model_validate(row)


@router.patch("/{broker_id}/contacts/{contact_id}", response_model=BrokerContactOut)
async def update_contact(
    broker_id: int,
    contact_id: int,
    payload: BrokerContactUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.update_contact(db, tenant_id, broker_id, contact_id, payload)
    return BrokerContactOut.model_validate(row)


@router.post("/{broker_id}/contacts/{contact_id}/archive", response_model=BrokerContactOut)
async def archive_contact(
    broker_id: int,
    contact_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.archive_contact(db, tenant_id, broker_id, contact_id)
    return BrokerContactOut.model_validate(row)


@router.post("/{broker_id}/contacts/{contact_id}/unarchive", response_model=BrokerContactOut)
async def unarchive_contact(
    broker_id: int,
    contact_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.unarchive_contact(db, tenant_id, broker_id, contact_id)
    return BrokerContactOut.model_validate(row)


# --- Domains ---


@router.get("/{broker_id}/domains", response_model=dict)
async def list_domains(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
    include_archived: bool = Query(False),
):
    paged = await brokers_service.list_domains(
        db, tenant_id, broker_id, page=page, size=size, include_archived=include_archived
    )
    items = [BrokerDomainOut.model_validate(x) for x in paged["items"]]
    return {**paged, "items": items}


@router.post(
    "/{broker_id}/domains",
    response_model=BrokerDomainOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_domain(
    broker_id: int,
    payload: BrokerDomainCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.create_domain(db, tenant_id, broker_id, payload)
    return BrokerDomainOut.model_validate(row)


@router.get("/{broker_id}/domains/{domain_id}", response_model=BrokerDomainOut)
async def get_domain(
    broker_id: int,
    domain_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.get_domain(db, tenant_id, broker_id, domain_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker domain not found")
    return BrokerDomainOut.model_validate(row)


@router.patch("/{broker_id}/domains/{domain_id}", response_model=BrokerDomainOut)
async def update_domain(
    broker_id: int,
    domain_id: int,
    payload: BrokerDomainUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.update_domain(db, tenant_id, broker_id, domain_id, payload)
    return BrokerDomainOut.model_validate(row)


@router.post("/{broker_id}/domains/{domain_id}/archive", response_model=BrokerDomainOut)
async def archive_domain(
    broker_id: int,
    domain_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.archive_domain(db, tenant_id, broker_id, domain_id)
    return BrokerDomainOut.model_validate(row)


@router.post("/{broker_id}/domains/{domain_id}/unarchive", response_model=BrokerDomainOut)
async def unarchive_domain(
    broker_id: int,
    domain_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.unarchive_domain(db, tenant_id, broker_id, domain_id)
    return BrokerDomainOut.model_validate(row)


# --- Aliases ---


@router.get("/{broker_id}/aliases", response_model=dict)
async def list_aliases(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
    include_archived: bool = Query(False),
):
    paged = await brokers_service.list_aliases(
        db, tenant_id, broker_id, page=page, size=size, include_archived=include_archived
    )
    items = [BrokerAliasOut.model_validate(x) for x in paged["items"]]
    return {**paged, "items": items}


@router.post(
    "/{broker_id}/aliases",
    response_model=BrokerAliasOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_alias(
    broker_id: int,
    payload: BrokerAliasCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.create_alias(db, tenant_id, broker_id, payload)
    return BrokerAliasOut.model_validate(row)


@router.get("/{broker_id}/aliases/{alias_id}", response_model=BrokerAliasOut)
async def get_alias(
    broker_id: int,
    alias_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.get_alias(db, tenant_id, broker_id, alias_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker alias not found")
    return BrokerAliasOut.model_validate(row)


@router.patch("/{broker_id}/aliases/{alias_id}", response_model=BrokerAliasOut)
async def update_alias(
    broker_id: int,
    alias_id: int,
    payload: BrokerAliasUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.update_alias(db, tenant_id, broker_id, alias_id, payload)
    return BrokerAliasOut.model_validate(row)


@router.post("/{broker_id}/aliases/{alias_id}/archive", response_model=BrokerAliasOut)
async def archive_alias(
    broker_id: int,
    alias_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.archive_alias(db, tenant_id, broker_id, alias_id)
    return BrokerAliasOut.model_validate(row)


@router.post("/{broker_id}/aliases/{alias_id}/unarchive", response_model=BrokerAliasOut)
async def unarchive_alias(
    broker_id: int,
    alias_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.unarchive_alias(db, tenant_id, broker_id, alias_id)
    return BrokerAliasOut.model_validate(row)


# --- Known senders (exact From email) ---


@router.get("/{broker_id}/known-senders", response_model=dict)
async def list_known_senders(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
    include_archived: bool = Query(False),
):
    paged = await brokers_service.list_known_senders(
        db, tenant_id, broker_id, page=page, size=size, include_archived=include_archived
    )
    items = [BrokerKnownSenderOut.model_validate(x) for x in paged["items"]]
    return {**paged, "items": items}


@router.post(
    "/{broker_id}/known-senders",
    response_model=BrokerKnownSenderOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_known_sender(
    broker_id: int,
    payload: BrokerKnownSenderCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.create_known_sender(db, tenant_id, broker_id, payload)
    return BrokerKnownSenderOut.model_validate(row)


@router.get("/{broker_id}/known-senders/{known_sender_id}", response_model=BrokerKnownSenderOut)
async def get_known_sender(
    broker_id: int,
    known_sender_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.get_known_sender(db, tenant_id, broker_id, known_sender_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Known sender not found")
    return BrokerKnownSenderOut.model_validate(row)


@router.patch("/{broker_id}/known-senders/{known_sender_id}", response_model=BrokerKnownSenderOut)
async def update_known_sender(
    broker_id: int,
    known_sender_id: int,
    payload: BrokerKnownSenderUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.update_known_sender(db, tenant_id, broker_id, known_sender_id, payload)
    return BrokerKnownSenderOut.model_validate(row)


@router.post("/{broker_id}/known-senders/{known_sender_id}/archive", response_model=BrokerKnownSenderOut)
async def archive_known_sender(
    broker_id: int,
    known_sender_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.archive_known_sender(db, tenant_id, broker_id, known_sender_id)
    return BrokerKnownSenderOut.model_validate(row)


@router.post("/{broker_id}/known-senders/{known_sender_id}/unarchive", response_model=BrokerKnownSenderOut)
async def unarchive_known_sender(
    broker_id: int,
    known_sender_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await brokers_service.unarchive_known_sender(db, tenant_id, broker_id, known_sender_id)
    return BrokerKnownSenderOut.model_validate(row)
