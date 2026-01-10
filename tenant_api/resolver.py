from __future__ import annotations
from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

def _extract_slug(host: str) -> str | None:
    host = (host or "").split(":")[0].lower()
    if host in ("localhost", "127.0.0.1"):
        return "dev-tenant"
    if host.endswith(".truckerp.me"):
        parts = host.split(".")
        if len(parts) >= 3:
            return parts[0]
    return None

class TenantResolverMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        slug = _extract_slug(request.headers.get("host", ""))
        request.state.tenant_slug = slug
        response = await call_next(request)
        return response
