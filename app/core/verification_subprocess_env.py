"""Sanitized subprocess environments for disposable verification (no prod secret inheritance)."""

from __future__ import annotations

import os
from typing import Mapping

from app.core.verification_host_guard import (
    VerificationHostDenied,
    assert_verification_database_url,
)

# Keys never copied from the parent process into verification children.
_STRIP_PREFIXES = (
    "AWS_",
    "SSM_",
    "SMTP_",
    "STRIPE_",
    "SENDGRID_",
    "TWILIO_",
    "OPENAI_",
    "GOOGLE_",
    "MICROSOFT_",
    "GMAIL_",
)

_STRIP_EXACT = frozenset(
    {
        "DATABASE_URL",
        "TENANT_DATABASE_URL",
        "ALEMBIC_TENANT_DATABASE_URL",
        "ALEMBIC_PLATFORM_DATABASE_URL",
        "POSTGRES_ADMIN_URL",
        "POSTGRES_PASSWORD",
        "DEMO_CLONE_EXECUTE",
        "TEST_BYPASS_AUTH",
        "TRUCKERP_SKIP_VERIFICATION_HOST_GUARD",
        "SKIP_VERIFICATION_HOST_GUARD",
        "TRUCKERP_ALLOW_PROD_VERIFICATION",
    }
)

_BASE_CHILD = {
    "LANG": "C.UTF-8",
    "ENVIRONMENT": "test",
    "JWT_SECRET": "verification-local-jwt-secret",
    "STORAGE_PROVIDER": "local",
    "DEMO_CLONE_EXTERNAL_EFFECTS": "disabled",
    "HTTP_PROXY": "",
    "HTTPS_PROXY": "",
    "ALL_PROXY": "",
    "NO_PROXY": "*",
}


def _parent_keys_to_drop() -> set[str]:
    drop: set[str] = set()
    for key in os.environ:
        upper = key.upper()
        if upper in _STRIP_EXACT:
            drop.add(key)
            continue
        if any(upper.startswith(prefix) for prefix in _STRIP_PREFIXES):
            drop.add(key)
        if "SECRET" in upper or "PASSWORD" in upper or "TOKEN" in upper:
            drop.add(key)
    return drop


def build_verification_subprocess_env(
    updates: Mapping[str, str],
    *,
    allow_test_bypass_auth: bool = False,
) -> dict[str, str]:
    """Build a child env for psql, alembic, pg_restore, or pytest."""
    child = {
        "PATH": os.environ.get("PATH", "/usr/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        **{k: v for k, v in os.environ.items() if k not in _parent_keys_to_drop()},
        **_BASE_CHILD,
    }
    child.update({k: str(v) for k, v in updates.items()})

    if not allow_test_bypass_auth:
        child.pop("TEST_BYPASS_AUTH", None)
    elif updates.get("TEST_BYPASS_AUTH") == "1":
        child["TEST_BYPASS_AUTH"] = "1"

    for url_key in (
        "DATABASE_URL",
        "TENANT_DATABASE_URL",
        "ALEMBIC_TENANT_DATABASE_URL",
        "TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL",
    ):
        raw = (child.get(url_key) or "").strip()
        if raw:
            assert_verification_database_url(raw, context=f"subprocess {url_key}")

    return child
