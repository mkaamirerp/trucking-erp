from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

# Paths that do not require tenant context (public/health/docs/platform)
_SKIP_PREFIXES = {
    "/",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/api/v1/health",
    "/api/v1/healthz",
    "/healthz",
    "/api/v1/public",
    "/api/v1/platform",
}


def _should_skip(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in _SKIP_PREFIXES)


async def tenant_context_middleware(request: Request, call_next):
    path = request.url.path
    if _should_skip(path):
        return await call_next(request)

    raw_tid = request.headers.get("x-tenant-id")
    if raw_tid is None:
        return JSONResponse(status_code=401, content={"detail": "X-Tenant-ID header required"})

    try:
        tenant_id = int(raw_tid)
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"detail": "X-Tenant-ID must be an integer"})

    request.state.tenant_id = tenant_id
    return await call_next(request)
