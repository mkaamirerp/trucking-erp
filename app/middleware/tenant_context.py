from __future__ import annotations

import os
import uuid
import logging
from typing import Callable, Iterable, Optional, Set

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.platform import PlatformTenant, TenantMembership
from app.utils.jwt_auth import get_token_from_request, decode_token, TokenType

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
    "/api/v1/auth/logout",  # no tenant/token needed; just clear cookies
    "/api/v1/auth/reset-password",
    "/api/v1/auth/signup/plan-options",
    "/api/v1/tools/unlock",  # dev-only tools unlock (no tenant)
    "/api/v1/tools/ping",  # dev-only tools ping (no tenant)
    "/api/v1/tools/send-test-email",  # dev-only SMTP test (no tenant)
    # /api/v1/tools/db/* intentionally not allowed — requires tenant context
}

REQUEST_ID_HEADER = "X-Request-ID"
TENANT_ID_HEADER = "X-Tenant-ID"
TENANT_SLUG_HEADER = "X-Tenant-Slug"


# Subdomains that must NOT be treated as tenant slugs (main, api, app)
RESERVED_SUBDOMAINS: Set[str] = {"www", "api", "app"}

# Paths that resolve tenant but skip membership gate (unauthenticated: login, forgot/reset password, accept-invite)
PUBLIC_AUTH_PATHS: Set[str] = {
    "/api/v1/auth/login",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/accept-invite",
}

# Prefix for applicant (invite-link token) routes: resolve tenant but skip membership (auth is token in query)
APPLICANT_ROUTE_PREFIX = "/api/v1/driver-onboarding/applicant/"


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Enforces tenant context for tenant-scoped routes.
    Single-source-of-truth order: host/subdomain (authoritative for browser) → headers → JWT (fallback for internal).
    - Platform routes and allowlist paths do NOT require tenant.
    - All other /api/v1/* routes resolve tenant and set request.state.tenant_id.
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

    def _slug_from_host(self, request: Request) -> Optional[str]:
        """Derive tenant slug from Host (subdomain). e.g. demo.truckerp.me → demo. Returns None if not a tenant subdomain."""
        host = (request.headers.get("host") or request.url.hostname or "").lower().split(":")[0]
        base = (settings.base_domain or "").lower()
        if not host or not base:
            return None
        if host == base:
            return None
        if not host.endswith("." + base):
            return None
        sub = host[: -(len(base) + 1)]
        if not sub or sub in RESERVED_SUBDOMAINS:
            return None
        if not sub.replace("-", "").isalnum():
            return None
        return sub

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

        # JWT: set user_id and roles when token present (don't fail yet if no token)
        prefer_refresh = path.startswith("/api/v1/auth/refresh")
        try:
            token, _ = get_token_from_request(request, prefer_refresh=prefer_refresh)
        except HTTPException as exc:
            response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            set_request_id(response)
            log("token_invalid", level="warning")
            return response
        jwt_tenant_id = None
        if token:
            try:
                payload = decode_token(token, expected_type=TokenType.REFRESH if prefer_refresh else TokenType.ACCESS)
                request.state.user_id = payload.get("sub")
                request.state.roles = payload.get("roles") or []
                jwt_tenant_id = payload.get("tenant_id")
            except HTTPException as exc:
                response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
                set_request_id(response)
                log("token_invalid", level="warning")
                return response

        # Test bypass: when TEST_BYPASS_AUTH=1 and X-Tenant-ID or X-Tenant-Slug present, skip JWT/membership (integration tests only)
        if os.environ.get("TEST_BYPASS_AUTH") == "1":
            raw_tid = request.headers.get(TENANT_ID_HEADER)
            raw_slug = request.headers.get(TENANT_SLUG_HEADER)
            if raw_tid is not None or (raw_slug and raw_slug.strip()):
                try:
                    async with AsyncSessionLocal() as session:
                        if raw_tid is not None:
                            row = await session.scalar(
                                select(PlatformTenant).where(PlatformTenant.id == int(raw_tid)).limit(1)
                            )
                        else:
                            row = await session.scalar(
                                select(PlatformTenant).where(PlatformTenant.slug == raw_slug.strip().lower()).limit(1)
                            )
                    if row and row.status == "ACTIVE" and row.db_status == "READY":
                        request.state.tenant_id = int(row.id)
                        request.state.tenant_slug = row.slug
                        request.state.user_id = "test-bypass-user"
                        response = await call_next(request)
                        set_request_id(response)
                        log("test_bypass", tenant_id=request.state.tenant_id)
                        return response
                except (ValueError, SQLAlchemyError):
                    pass

        # Forgot-password from main domain (no tenant): allow through without tenant_id
        if path.rstrip("/") == "/api/v1/auth/forgot-password":
            slug_from_host = self._slug_from_host(request)
            has_tenant_header = request.headers.get(TENANT_ID_HEADER) is not None or request.headers.get(TENANT_SLUG_HEADER) is not None
            if slug_from_host is None and not has_tenant_header and jwt_tenant_id is None:
                response = await call_next(request)
                set_request_id(response)
                log("forgot_password_main_domain")
                return response

        # Single-source-of-truth: host (authoritative for browser) → headers (match/override) → JWT (fallback for internal)
        try:
            tenant_id, tenant_slug = await self._resolve_tenant_from_request(request, path, jwt_tenant_id)
            request.state.tenant_id = tenant_id
            request.state.tenant_slug = tenant_slug
        except HTTPException as exc:
            response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            set_request_id(response)
            log("resolve_error", level="warning")
            return response

        response = await call_next(request)
        set_request_id(response)
        log("success", tenant_id=request.state.tenant_id)
        return response

    async def _resolve_tenant_from_request(
        self, request: Request, path: str, jwt_tenant_id: Optional[int]
    ) -> tuple[int, str]:
        """
        Resolve tenant in order: host subdomain (authoritative for browser) → headers → JWT (fallback for internal).
        Returns (tenant_id, tenant_slug) or raises HTTPException.
        """
        slug_from_host = self._slug_from_host(request)
        raw_tid = request.headers.get(TENANT_ID_HEADER)
        raw_slug = request.headers.get(TENANT_SLUG_HEADER)
        has_header = raw_tid is not None or raw_slug is not None

        # Resolve to (tenant_id or slug) for DB lookup: state (callback) > header > host > JWT
        tenant_id_from_request: Optional[int] = None
        tenant_slug_from_request: Optional[str] = None

        # Gmail OAuth callback: tenant from signed state (platform URL has no subdomain)
        if path.rstrip("/") == "/api/v1/admin/email-config/gmail/callback":
            state = request.query_params.get("state")
            if state:
                from app.services.gmail_oauth import parse_state
                parsed = parse_state(state)
                if parsed:
                    tenant_id_from_request, tenant_slug_from_request = parsed

        if tenant_id_from_request is None and tenant_slug_from_request is None:
            if has_header:
                if raw_tid is not None:
                    try:
                        tenant_id_from_request = int(raw_tid)
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid tenant header: X-Tenant-ID must be int",
                        )
                elif raw_slug:
                    s = raw_slug.strip()
                    if not s:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid tenant header: X-Tenant-Slug is empty",
                        )
                    tenant_slug_from_request = s
            elif slug_from_host:
                tenant_slug_from_request = slug_from_host
            elif jwt_tenant_id is not None:
                tenant_id_from_request = int(jwt_tenant_id)
            else:
                # Dev tools DB: allow default tenant so you can inspect DB from main domain (no subdomain)
                default_tid = os.environ.get("TOOLS_DEFAULT_TENANT_ID")
                default_slug = os.environ.get("TOOLS_DEFAULT_TENANT_SLUG")
                if path.startswith("/api/v1/tools/db/") and (default_tid or default_slug):
                    if default_tid:
                        try:
                            tenant_id_from_request = int(default_tid)
                        except ValueError:
                            tenant_id_from_request = None
                    if tenant_id_from_request is None and default_slug:
                        tenant_slug_from_request = default_slug.strip()
                if tenant_id_from_request is None and tenant_slug_from_request is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Tenant context required: use tenant subdomain (e.g. demo.truckerp.me) or X-Tenant-Slug / X-Tenant-ID header",
                    )

        # Lookup in platform tenant registry and enforce membership gate
        try:
            async with AsyncSessionLocal() as session:
                if tenant_id_from_request is not None:
                    row = await session.scalar(
                        select(PlatformTenant).where(PlatformTenant.id == tenant_id_from_request).limit(1)
                    )
                else:
                    row = await session.scalar(
                        select(PlatformTenant).where(PlatformTenant.slug == tenant_slug_from_request).limit(1)
                    )

                if not row:
                    detail = "Tenant not found in registry (check subdomain, X-Tenant-Slug/X-Tenant-ID, or TOOLS_DEFAULT_TENANT_SLUG/ID for dev tools)."
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

                # Dev tools DB: only require tenant to exist; skip ACTIVE/READY and membership
                if path.startswith("/api/v1/tools/db/"):
                    return (int(row.id), row.slug)

                if row.status != "ACTIVE" or row.db_status != "READY":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Tenant not ready",
                    )

                # Public auth paths: resolve tenant but skip membership gate (user is not authenticated yet)
                path_normalized = path.rstrip("/")
                if path_normalized in PUBLIC_AUTH_PATHS:
                    logger.info(
                        "tenant_context tenant_resolved membership_skipped_public_auth path=%s tenant_id=%s request_id=%s",
                        path_normalized,
                        int(row.id),
                        request.headers.get(REQUEST_ID_HEADER, ""),
                    )
                    return (int(row.id), row.slug)

                # Applicant (invite-link token) routes: resolve tenant but skip membership; auth is token in query
                if path.startswith(APPLICANT_ROUTE_PREFIX):
                    logger.info(
                        "tenant_context tenant_resolved membership_skipped_applicant path=%s tenant_id=%s request_id=%s",
                        path[:80],
                        int(row.id),
                        request.headers.get(REQUEST_ID_HEADER, ""),
                    )
                    return (int(row.id), row.slug)

                # Membership gate: user must have active membership (do not trust client headers for user_id)
                user_id = getattr(request.state, "user_id", None)
                if not user_id:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Not authenticated",
                    )
                membership = await session.scalar(
                    select(TenantMembership).where(
                        TenantMembership.user_id == user_id,
                        TenantMembership.tenant_id == row.id,
                        TenantMembership.status == "active",
                    ).limit(1)
                )
                if not membership:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="User does not have access to this tenant",
                    )
                return (int(row.id), row.slug)
        except HTTPException:
            raise
        except SQLAlchemyError as exc:
            logger.warning("tenant_lookup_failed error=%s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Tenant lookup unavailable; retry later",
            ) from exc
