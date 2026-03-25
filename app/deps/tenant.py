from fastapi import HTTPException, Request, status

from app.core.config import settings

RESERVED_SUBDOMAINS = {"www", "api", "app"}


def _slug_from_host(request: Request) -> str | None:
    """Derive tenant slug from Host (subdomain). demo.truckerp.me → demo."""
    host = (request.headers.get("host") or getattr(request.url, "hostname", "") or "").lower().split(":")[0]
    base = (settings.base_domain or "").lower()
    if not host or not base or host == base or not host.endswith("." + base):
        return None
    sub = host[: -(len(base) + 1)]
    if not sub or sub in RESERVED_SUBDOMAINS or not sub.replace("-", "").isalnum():
        return None
    return sub


def tenant_slug_from_request(request: Request) -> str | None:
    """Tenant slug from Host subdomain only (trusted). Public routes do not use X-Tenant-Slug."""
    return _slug_from_host(request)


def require_tenant(request: Request) -> int:
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing tenant context",
        )
    return int(tenant_id)


def require_tenant_slug(request: Request) -> str:
    slug = getattr(request.state, "tenant_slug", None)
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing tenant slug (required for storage)",
        )
    return str(slug)
