"""
Record login failure diagnostics for operators (platform DB only).

Public HTTP responses stay generic. Logs + platform_login_failure_events carry reason codes;
no raw email, password, or hash in the row (email_fingerprint only).
"""

from __future__ import annotations

import hashlib
import logging

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

LOGIN_FAIL_NO_TENANT_USER = "login_fail_no_tenant_user"
LOGIN_FAIL_NO_WORKSPACE_MEMBER = "login_fail_no_workspace_member"
LOGIN_FAIL_VERIFY_TENANT_PASSWORD = "login_fail_verify_tenant_password"
LOGIN_FAIL_TENANT_AUTH_INCOMPLETE = "login_fail_tenant_auth_incomplete"
LOGIN_FAIL_NO_PLATFORM_USER = "login_fail_no_platform_user"
LOGIN_FAIL_NO_PLATFORM_MEMBERSHIP = "login_fail_no_platform_membership"
LOGIN_FAIL_VERIFY_PLATFORM_PASSWORD = "login_fail_verify_platform_password"
LOGIN_FAIL_APEX_NO_PLATFORM_TENANT = "login_fail_apex_no_platform_tenant"


def email_fingerprint(email_norm: str) -> str:
    h = hashlib.sha256(f"truckerp_login_fp:v1:{email_norm or ''}".encode("utf-8")).hexdigest()
    return h[:16]


async def log_and_persist_login_failure(
    *,
    request: Request,
    tenant_id: int,
    tenant_slug: str,
    tenant_auth_mode: str,
    email_norm: str,
    reason_code: str,
) -> None:
    """Structured WARNING log + best-effort insert into platform_login_failure_events."""
    fp = email_fingerprint(email_norm)
    host = (request.headers.get("host") or "").split(":")[0][:255] or None
    rid = request.headers.get("X-Request-ID") or getattr(request.state, "request_id", None)
    rid_str = (str(rid)[:64] if rid else None)

    logger.warning(
        "event=login_failed reason=%s tenant_id=%s tenant_slug=%s tenant_auth_mode=%s "
        "email_fingerprint=%s request_id=%s request_host=%s path=%s",
        reason_code,
        tenant_id,
        tenant_slug,
        tenant_auth_mode,
        fp,
        rid_str,
        host,
        request.url.path,
    )

    try:
        from app.core.database import AsyncSessionLocal
        from app.models.platform import PlatformLoginFailureEvent

        async with AsyncSessionLocal() as adb:
            row = PlatformLoginFailureEvent(
                tenant_id=int(tenant_id),
                tenant_slug=tenant_slug[:63],
                tenant_auth_mode=(tenant_auth_mode or "platform")[:20],
                reason_code=reason_code[:64],
                email_fingerprint=fp[:32],
                request_id=rid_str,
                request_host=host,
            )
            adb.add(row)
            await adb.commit()
    except SQLAlchemyError as exc:
        logger.warning("login_failure_audit_persist_failed reason=%s err=%s", reason_code, exc)
