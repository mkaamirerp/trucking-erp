"""Authorization harness for disposable verification (no TEST_BYPASS_AUTH for certification)."""

from __future__ import annotations

import os

from app.core.verification_host_guard import (
    VerificationHostDenied,
    assert_verification_auth_not_bypassed,
    assert_verification_database_url,
)

CERTIFICATION_AUTH_MODE = "certification"
DEFAULT_CERT_HOST = "pytest.truckerp.me"


def require_certification_auth_mode() -> None:
    mode = (os.environ.get("TRUCKERP_VERIFICATION_AUTH_MODE") or "").strip().lower()
    if mode != CERTIFICATION_AUTH_MODE:
        raise VerificationHostDenied(
            f"TRUCKERP_VERIFICATION_AUTH_MODE must be '{CERTIFICATION_AUTH_MODE}' for this wave"
        )
    assert_verification_auth_not_bypassed()


def assert_disposable_platform_and_tenant_urls() -> None:
    platform = (os.environ.get("DATABASE_URL") or "").strip()
    tenant = (os.environ.get("TENANT_DATABASE_URL") or "").strip()
    if not platform or not tenant:
        raise VerificationHostDenied("DATABASE_URL and TENANT_DATABASE_URL are required for auth certification")
    assert_verification_database_url(platform, context="platform DATABASE_URL")
    assert_verification_database_url(tenant, context="tenant TENANT_DATABASE_URL")


def build_certification_bearer_headers(
    *,
    user_id: str,
    tenant_id: int,
    email: str,
    role: str = "TENANT_ADMIN",
    host: str = DEFAULT_CERT_HOST,
) -> dict[str, str]:
    """Build Host + Bearer headers for certification pytest (real JWT, no TEST_BYPASS_AUTH)."""
    from app.utils.jwt_auth import create_access_token

    token = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        tenant_slug=host.split(".", 1)[0],
        roles=[role],
        sv=1,
    )
    return {
        "Authorization": f"Bearer {token}",
        "host": host,
    }


def certification_auth_checklist() -> list[str]:
    return [
        "Provision disposable platform DB via scripts/disposable_platform_bootstrap.py",
        "Seed registry via scripts/disposable_platform_seed.py",
        "Register platform_tenants slug=pytest ACTIVE with db_name matching TENANT_DATABASE_URL",
        "CASBIN_LOAD_PILOT_ENFORCEMENT=true with prospective policy loaded",
        "Run pytest with build_certification_bearer_headers(); TEST_BYPASS_AUTH unset",
        "Network: verification host cannot reach production Postgres (SG / docker network)",
    ]
