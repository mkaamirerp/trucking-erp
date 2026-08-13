"""Tenant terminals / yards — Slice 1 minimal CRUD (soft-deactivate only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.custody import (
    TerminalCreate,
    TerminalListResponse,
    TerminalResponse,
    TerminalUpdate,
)
from app.services import load_custody as custody_service

router = APIRouter(prefix="/terminals", tags=["terminals"])


@router.get("", response_model=TerminalListResponse)
async def list_terminals(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    active_only: bool = Query(True),
) -> TerminalListResponse:
    return await custody_service.list_terminals(db, tenant_id, active_only=active_only)


@router.post("", response_model=TerminalResponse, status_code=status.HTTP_201_CREATED)
async def create_terminal(
    body: TerminalCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TerminalResponse:
    out = await custody_service.create_terminal(db, tenant_id, body)
    await db.commit()
    return out


@router.get("/{terminal_id}", response_model=TerminalResponse)
async def get_terminal(
    terminal_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TerminalResponse:
    return await custody_service.get_terminal(db, tenant_id, terminal_id)


@router.put("/{terminal_id}", response_model=TerminalResponse)
async def update_terminal(
    terminal_id: int,
    body: TerminalUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TerminalResponse:
    out = await custody_service.update_terminal(db, tenant_id, terminal_id, body)
    await db.commit()
    return out


@router.patch("/{terminal_id}", response_model=TerminalResponse)
async def patch_terminal(
    terminal_id: int,
    body: TerminalUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TerminalResponse:
    out = await custody_service.update_terminal(db, tenant_id, terminal_id, body)
    await db.commit()
    return out
