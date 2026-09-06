from __future__ import annotations

import os
import uuid
import logging
from typing import Callable, FrozenSet, Iterable, Optional, Set

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.deps.tenant_db import open_tenant_session_by_id
from app.models.platform import PlatformTenant, TenantMembership
from app.services.tenant_auth_constants import tenant_uses_tenant_db_auth
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
    "/api/v1/webhooks/gmail/pubsub",
    "/api/v1/webhooks/microsoft-graph",
    "/api/v1/auth/logout",  # no tenant/token needed; just clear cookies
    "/api/v1/auth/reset-password",
    "/api/v1/auth/signup/plan-options",
    # /api/v1/tools/*: see tenant_middleware_allow_paths() — only in dev-like envs when routers are mounted
    # /api/v1/tools/db/* intentionally not allowed — requires tenant context
}


def tenant_middleware_allow_paths() -> Set[str]:
    """
    Paths that skip tenant resolution. Dev-only /api/v1/tools/* (no tenant) is allowlisted only when
    Settings.allows_tenant_resolution_shortcuts() is true, matching main.py mounting of dev_tools routers.
    """
    paths = set(DEFAULT_ALLOW_PATHS)
    if settings.allows_tenant_resolution_shortcuts():
        paths.update(
            {
                "/api/v1/tools/unlock",
                "/api/v1/tools/ping",
                "/api/v1/tools/send-test-email",
            }
        )
    return paths

REQUEST_ID_HEADER = "X-Request-ID"

# Subdomains that must NOT be treated as tenant slugs (main, api, app)
RESERVED_SUBDOMAINS: Set[str] = {"www", "api", "app"}

# Paths that resolve tenant but skip membership gate (unauthenticated: login, forgot/reset password, accept-invite)
PUBLIC_AUTH_PATHS: Set[str] = {
    "/api/v1/auth/login",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/accept-invite",
    "/api/v1/auth/login-step-up/issue",
    "/api/v1/auth/login-step-up/verify",
}

# Prefix for applicant (invite-link token) routes: resolve tenant but skip membership (auth is token in query)
APPLICANT_ROUTE_PREFIX = "/api/v1/driver-onboarding/applicant/"

# Apex/marketing host has no tenant subdomain; session probes must still work. Tenant id comes only from the
# signed JWT issued at login (not from client headers), same trust model as subdomain requests.
JWT_TENANT_FALLBACK_PATHS: FrozenSet[str] = frozenset({
    "/api/v1/auth/me",
    "/api/v1/auth/refresh",
})


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Enforces tenant context for tenant-scoped routes.
    Tenant resolution (browser/API): trusted Host subdomain → OAuth signed state (Gmail callback) →
    dev/CI only (explicit ALLOW_TENANT_RESOLUTION_SHORTCUTS + safe ENVIRONMENT; see Settings): JWT tenant_id when Host has no tenant slug,
    or TOOLS_DEFAULT_* for /tools/db only.
    X-Tenant-ID / X-Tenant-Slug are not used for resolution (browser cannot choose tenant).
    Platform routes and allowlist paths do NOT require tenant.
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

        # Test bypass: requires ALLOW_TENANT_RESOLUTION_SHORTCUTS + safe ENVIRONMENT + TEST_BYPASS_AUTH=1 (startup-validated).
        if os.environ.get("TEST_BYPASS_AUTH") == "1" and settings.allows_tenant_resolution_shortcuts():
            bypass_slug = self._slug_from_host(request)
            if bypass_slug:
                # Hard isolation: never bind TEST_BYPASS to the live demo tenant.
                from app.core.integration_db_guard import (
                    IntegrationIsolationError,
                    assert_integration_tenant_slug_allowed,
                )

                try:
                    assert_integration_tenant_slug_allowed(
                        bypass_slug, context="TEST_BYPASS_AUTH host resolution"
                    )
                except IntegrationIsolationError as exc:
                    response = JSONResponse(
                        status_code=403,
                        content={"detail": str(exc), "code": "INTEGRATION_ISOLATION_FORBIDDEN_TENANT"},
                    )
                    set_request_id(response)
                    log("test_bypass_forbidden_tenant", level="error")
                    return response
                try:
                    async with AsyncSessionLocal() as session:
                        row = await session.scalar(
                            select(PlatformTenant).where(PlatformTenant.slug == bypass_slug.lower()).limit(1)
                        )
                    if row and row.status == "ACTIVE" and row.db_status == "READY":
                        from app.core.integration_db_guard import assert_integration_db_name_allowed

                        try:
                            assert_integration_db_name_allowed(
                                row.db_name, context="TEST_BYPASS_AUTH tenant db_name"
                            )
                        except IntegrationIsolationError as exc:
                            response = JSONResponse(
                                status_code=403,
                                content={
                                    "detail": str(exc),
                                    "code": "INTEGRATION_ISOLATION_FORBIDDEN_TENANT_DB",
                                },
                            )
                            set_request_id(response)
                            log("test_bypass_forbidden_db", level="error")
                            return response

                        request.state.tenant_id = int(row.id)
                        request.state.tenant_slug = row.slug
                        request.state.user_id = "test-bypass-user"
                        response = await call_next(request)
                        set_request_id(response)
                        log("test_bypass", tenant_id=request.state.tenant_id)
                        return response
                except SQLAlchemyError:
                    logger.exception(
                        "tenant_context test_bypass platform tenant lookup failed tenant_slug=%s request_id=%s",
                        bypass_slug,
                        request_id,
                    )
                    # Fail closed: do not grant bypass; fall through to normal resolution.

        # Forgot-password from main domain (no tenant): allow through without tenant_id
        if path.rstrip("/") == "/api/v1/auth/forgot-password":
            slug_from_host = self._slug_from_host(request)
            if slug_from_host is None and jwt_tenant_id is None:
                response = await call_next(request)
                set_request_id(response)
                log("forgot_password_main_domain")
                return response

        # Login from marketing apex (no subdomain): tenant is chosen in the handler from email + memberships.
        if request.method == "POST" and path.rstrip("/") == "/api/v1/auth/login":
            slug_from_host = self._slug_from_host(request)
            if slug_from_host is None and jwt_tenant_id is None:
                response = await call_next(request)
                set_request_id(response)
                log("login_main_domain")
                return response

        # Login step-up OTP must use the same workspace host as sign-in (tenant binding at request edge).
        if request.method == "POST" and path.rstrip("/") in (
            "/api/v1/auth/login-step-up/issue",
            "/api/v1/auth/login-step-up/verify",
        ):
            slug_from_host = self._slug_from_host(request)
            if slug_from_host is None and jwt_tenant_id is None:
                response = JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Use your company sign-in URL to continue."},
                )
                set_request_id(response)
                log("login_step_up_requires_workspace_host", level="warning")
                return response

        # Create workspace: platform JWT only; do not require tenant resolution or membership in an existing tenant.
        if request.method == "POST" and path.rstrip("/") == "/api/v1/auth/workspaces":
            user_id = getattr(request.state, "user_id", None)
            if not user_id:
                response = JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Not authenticated"},
                )
                set_request_id(response)
                log("workspaces_no_auth", level="warning")
                return response
            response = await call_next(request)
            set_request_id(response)
            log("workspaces_platform_context")
            return response

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
        Resolve tenant from Host subdomain, Gmail OAuth state, optional JWT fallback, or tools defaults when shortcuts are enabled.
        Never from X-Tenant-ID / X-Tenant-Slug.
        """
        slug_from_host = self._slug_from_host(request)

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
            if slug_from_host:
                tenant_slug_from_request = slug_from_host
            else:
                path_norm = path.rstrip("/")
                if jwt_tenant_id is not None and path_norm in JWT_TENANT_FALLBACK_PATHS:
                    tenant_id_from_request = int(jwt_tenant_id)
                elif settings.allows_tenant_resolution_shortcuts() and jwt_tenant_id is not None:
                    tenant_id_from_request = int(jwt_tenant_id)
                else:
                    default_tid = os.environ.get("TOOLS_DEFAULT_TENANT_ID")
                    default_slug = os.environ.get("TOOLS_DEFAULT_TENANT_SLUG")
                    if (
                        settings.allows_tenant_resolution_shortcuts()
                        and path.startswith("/api/v1/tools/db/")
                        and (default_tid or default_slug)
                    ):
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
                            detail="Tenant context required: open the app from your workspace subdomain (e.g. https://demo.truckerp.me).",
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
                        select(PlatformTenant)
                        .where(PlatformTenant.slug == (tenant_slug_from_request or "").lower())
                        .limit(1)
                    )

                if not row:
                    detail = "Tenant not found in registry (check workspace subdomain or provisioning)."
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

                # Membership gate: user must have active workspace access (do not trust client headers for user_id)
                user_id = getattr(request.state, "user_id", None)
                if not user_id:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Not authenticated",
                    )
                mode = getattr(row, "tenant_auth_mode", None) or "platform"
                if tenant_uses_tenant_db_auth(mode):
                    # JWT `sub` is tenant_users.id; TenantWorkspaceMember + session parity are enforced in
                    # get_current_user (same tenant DB session as credential lookup). Avoid a second tenant
                    # session here that can race or drift from deps.
                    try:
                        int(str(user_id))
                    except (TypeError, ValueError):
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid session",
                        ) from None
                    return (int(row.id), row.slug)

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
