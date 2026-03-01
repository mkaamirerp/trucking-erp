from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant_db import get_tenant_db_for_tools

Severity = Literal["INFO", "WARN", "CRITICAL"]

router = APIRouter(prefix="/api/v1/admin/diagnostics", tags=["Admin Diagnostics"])


def _require_platform_admin(current: CurrentUser) -> None:
    role = (current.role or "").upper()
    if role not in {"OWNER", "ADMIN", "TENANT_OWNER", "TENANT_ADMIN"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


async def _scalar(db: AsyncSession, sql: str) -> Any:
    return await db.scalar(text(sql))


async def _rows(db: AsyncSession, sql: str) -> list[dict[str, Any]]:
    res = await db.execute(text(sql))
    keys = list(res.keys())
    return [dict(zip(keys, row)) for row in res.fetchall()]


def _signal(
    severity: Severity,
    title: str,
    what_it_means: str,
    why_we_care: str,
    how_to_fix: str,
    data: Any | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "severity": severity,
        "title": title,
        "what_it_means": what_it_means,
        "why_we_care": why_we_care,
        "how_to_fix": how_to_fix,
    }
    if data is not None:
        out["data"] = data
    return out


@router.get("/db")
async def db_diagnostics(
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    platform_db: AsyncSession = Depends(get_db),
    tenant_db: AsyncSession = Depends(get_tenant_db_for_tools),
) -> dict[str, Any]:
    """Read-only DB diagnostics for the admin UI."""
    _require_platform_admin(current)

    platform_version = await _scalar(platform_db, "select version_num from alembic_version limit 1;")
    tenant_version = await _scalar(tenant_db, "select version_num from alembic_version limit 1;")

    platform_guardrail = await _scalar(
        platform_db, "select to_regclass('public.platform_forbidden_tables') as regclass;"
    )
    tenant_guardrail = await _scalar(
        tenant_db, "select to_regclass('public.tenant_forbidden_tables') as regclass;"
    )

    signals: list[dict[str, Any]] = []
    if tenant_guardrail is None:
        signals.append(
            _signal(
                "WARN",
                "Tenant guardrail view missing",
                "The informational view public.tenant_forbidden_tables is missing in the tenant DB.",
                "This guardrail improves visibility. Without it, audits can’t quickly detect platform-only tables leaking into a tenant DB.",
                "Apply the tenant migration that creates public.tenant_forbidden_tables (CREATE OR REPLACE VIEW).",
            )
        )

    platform_forbidden_found: list[str] = []
    if platform_guardrail is not None:
        rows = await _rows(platform_db, "select tablename from public.platform_forbidden_tables order by tablename;")
        platform_forbidden_found = [r["tablename"] for r in rows if r.get("tablename")]

    tenant_forbidden_found: list[str] = []
    if tenant_guardrail is not None:
        rows = await _rows(tenant_db, "select tablename from public.tenant_forbidden_tables order by tablename;")
        tenant_forbidden_found = [r["tablename"] for r in rows if r.get("tablename")]

    return {
        "versions": {
            "platform_db": {"alembic_version": platform_version},
            "tenant_db": {"alembic_version": tenant_version},
        },
        "guardrails": {
            "platform_forbidden_tables_view": platform_guardrail,
            "tenant_forbidden_tables_view": tenant_guardrail,
        },
        "forbidden_tables": {
            "platform_found": platform_forbidden_found,
            "tenant_found": tenant_forbidden_found,
        },
        "signals": signals,
        "incidents": {"tenant": [], "platform": []},
        "context": {
            "tenant_id": getattr(request.state, "tenant_id", None),
            "tenant_slug": getattr(request.state, "tenant_slug", None),
            "user_id": current.user_id,
            "role": current.role,
        },
    }

