from __future__ import annotations

import uuid
import logging
from typing import Callable, Iterable, Optional, Set

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.database import AsyncSessionLocal
from app.models.platform import PlatformTenant

logger = logging.getLogger(__name__)

DEFAULT_ALLOW_PATHS: Set[str] = {
    "/",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/api/v1/health",
    "/api/v1/healthz",
    "/healthz",
    "/api/v1/public",
}

REQUEST_ID_HEADER = "X-Request-ID"
TENANT_ID_HEADER = "X-Tenant-ID"
TENANT_SLUG_HEADER = "X-Tenant-Slug"


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Enforces tenant context for tenant-scoped routes.
    - Platform routes: platform_prefix (default /api/v1/platform/) do NOT require tenant.
    - Allowlist paths do NOT require tenant.
    - All other /api/v1/* routes REQUIRE tenant context (id or slug) and set request.state.tenant_id.
    Also adds/propagates X-Request-ID.
    """

    def __init__(
        self,
        app,
        *,
        allow_paths: Optional[Iterable[str]] = None,
        platform_prefix: str = "/api/v1/platform/",
        api_prefix: str = "/api/v1/",
    ):
        super().__init__(app)
        self.allow_paths: Set[str] = set(allow_paths or DEFAULT_ALLOW_PATHS)
        self.platform_prefix = platform_prefix
        self.api_prefix = api_prefix

    def _is_allowed_path(self, path: str) -> bool:
        return any(path == p or path.startswith(f"{p}/") for p in self.allow_paths)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Request ID
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())

        def set_request_id(response: Response) -> None:
            response.headers[REQUEST_ID_HEADER] = request_id

        def log(outcome: str, tenant_id: Optional[int] = None, level: str = "info") -> None:
            msg = (
                f"tenant_context outcome={outcome} method={request.method} path={path} "
                f"tenant_id={tenant_id} request_id={request_id}"
            )
            getattr(logger, level, logger.info)(msg)

        # Allowlist (health/docs/root)
        if self._is_allowed_path(path):
            response = await call_next(request)
            set_request_id(response)
            log("allowed_no_tenant")
            return response

        # Only enforce on API routes
        if not path.startswith(self.api_prefix):
            response = await call_next(request)
            set_request_id(response)
            log("non_api")
            return response

        # Platform routes do not require tenant
        if self.platform_prefix and path.startswith(self.platform_prefix):
            response = await call_next(request)
            set_request_id(response)
            log("platform_no_tenant")
            return response

        # Tenant-scoped route: require tenant header
        try:
            tenant_id = await self._resolve_tenant(request)
        except HTTPException as exc:
            # Convert to response so BaseHTTPMiddleware doesn't swallow it as 500
            response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            set_request_id(response)
            log("resolve_error", level="warning")
            return response

        request.state.tenant_id = tenant_id

        response = await call_next(request)
        set_request_id(response)
        log("success", tenant_id=tenant_id)
        return response

    async def _resolve_tenant(self, request: Request) -> int:
        raw_tid = request.headers.get(TENANT_ID_HEADER)
        raw_slug = request.headers.get(TENANT_SLUG_HEADER)

        if raw_tid is None and raw_slug is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Tenant-ID (or X-Tenant-Slug) required for tenant-scoped operations",
            )

        tenant_id: Optional[int] = None
        tenant_slug: Optional[str] = None

        if raw_tid is not None:
            try:
                tenant_id = int(raw_tid)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant header: X-Tenant-ID must be int"
                )
        elif raw_slug:
            tenant_slug = raw_slug.strip()
            if not tenant_slug:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant header: X-Tenant-Slug is empty"
                )

        # Validate against platform tenant registry when available
        try:
            async with AsyncSessionLocal() as session:
                if tenant_id is not None:
                    row = await session.scalar(
                        select(PlatformTenant).where(PlatformTenant.id == tenant_id).limit(1)
                    )
                else:
                    row = await session.scalar(
                        select(PlatformTenant).where(PlatformTenant.slug == tenant_slug).limit(1)
                    )
        except SQLAlchemyError as exc:  # schema drift or connectivity issue
            logger.warning("tenant_lookup_failed error=%s", exc)
            # Fallback: accept provided id when DB lookup is unavailable
            if tenant_id is not None:
                return tenant_id
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Tenant lookup unavailable; retry later",
            )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Tenant inactive or not found"
            )

        allowed_statuses = {"ACTIVE", "PROVISIONING"}
        if row.status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Tenant inactive or not found"
            )

        return int(row.id)
