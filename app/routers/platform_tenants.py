from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.platform import PlatformTenant

router = APIRouter(prefix="/api/v1/platform", tags=["platform-tenants"])


def require_admin_header(x_platform_admin_key: str | None = Header(None)) -> None:
    expected = None  # set via env if needed later
    if expected and x_platform_admin_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.get("/tenants")
async def list_tenants(db: AsyncSession = Depends(get_db), _: None = Depends(require_admin_header)):
    rows = (await db.execute(select(PlatformTenant))).scalars().all()
    return [{"id": t.id, "name": t.name, "slug": t.slug, "status": t.status, "db_status": t.db_status} for t in rows]


@router.post("/tenants")
async def create_tenant(body: dict, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin_header)):
    name = body.get("company_name") or body.get("name")
    slug = body.get("slug")
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="company_name is required")
    if not slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slug is required")
    exists = await db.scalar(select(PlatformTenant).where(PlatformTenant.slug == slug))
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug already exists")
    tenant = PlatformTenant(
        name=name,
        slug=slug,
        status="PROVISIONING",
        plan=body.get("plan") or body.get("plan_code") or "trial",
        db_status="NOT_PROVISIONED",
    )
    db.add(tenant)
    await db.commit()
    return {"id": tenant.id, "slug": tenant.slug, "status": tenant.status, "db_status": tenant.db_status}


@router.post("/tenants/{tenant_id}/provision")
async def provision_tenant_stub(tenant_id: int, _: None = Depends(require_admin_header)):
    # Stub for B4
    return {"tenant_id": tenant_id, "status": "provisioning_not_implemented_yet"}
