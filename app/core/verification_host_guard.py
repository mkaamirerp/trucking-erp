"""Fail-closed host and URL checks for TruckERP verification runs.

Disposable execution requires **positive proof** of an approved verification host.
Unknown AWS instances are denied even when they are absent from the production denylist.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from app.core.integration_db_guard import (
    PRODUCTION_PLATFORM_DB_NAMES,
    PRODUCTION_PLATFORM_HOSTS,
    database_host_from_url,
)

KNOWN_PRODUCTION_EC2_INSTANCE_IDS = frozenset(
    {
        "i-0126f0dc65891ca63",
    }
)

# Optional allowlist for owner-provisioned disposable EC2 (empty until owner adds ids).
ALLOWED_DISPOSABLE_EC2_INSTANCE_IDS: frozenset[str] = frozenset()

VERIFICATION_HOST_CLASS_FILE = Path("/etc/truckerp/verification-host-class")
ALLOWED_HOST_CLASS = "disposable"

DISPOSABLE_CI_MARKER = "workflow:verification-disposable"

FORBIDDEN_BYPASS_ENV_VARS = frozenset(
    {
        "TRUCKERP_SKIP_VERIFICATION_HOST_GUARD",
        "SKIP_VERIFICATION_HOST_GUARD",
        "DEMO_CLONE_EXECUTE_OVERRIDE",
        "TRUCKERP_ALLOW_PROD_VERIFICATION",
        "TRUCKERP_VERIFICATION_ALLOW_PRODUCTION_HOST",
    }
)

URL_ENV_VARS = (
    "DATABASE_URL",
    "TENANT_DATABASE_URL",
    "ALEMBIC_TENANT_DATABASE_URL",
    "POSTGRES_ADMIN_URL",
    "ALEMBIC_PLATFORM_DATABASE_URL",
    "TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL",
)

ALLOWED_VERIFICATION_DB_HOSTS = frozenset(
    {
        "db.example.invalid",
        "localhost",
        "127.0.0.1",
        "truckerp-phase4c-postgres",
        "172.24.0.2",
        "postgres",
        "verification-postgres",
    }
)

FORBIDDEN_VERIFICATION_DB_NAMES = frozenset(
    {"tenant_demo", "trucking_erp"} | PRODUCTION_PLATFORM_DB_NAMES
)

SUPPORTED_VERIFICATION_ENTRYPOINTS = frozenset(
    {
        "scripts/verification_host_preflight.py",
        "scripts/disposable_tenant_bootstrap.py",
        "scripts/disposable_platform_bootstrap.py",
        "scripts/disposable_platform_seed.py",
        "scripts/disposable_verification_runner.py",
        "scripts/demo_clone_runner.py",
    }
)


class VerificationHostDenied(RuntimeError):
    """Raised when verification must not run on this host or with these URLs."""


def _fetch_ec2_instance_id(timeout_seconds: float = 2.0) -> str | None:
    try:
        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
        )
        with urllib.request.urlopen(token_req, timeout=timeout_seconds) as resp:
            token = resp.read().decode("utf-8").strip()
        id_req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(id_req, timeout=timeout_seconds) as resp:
            return resp.read().decode("utf-8").strip() or None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def read_verification_host_class_file() -> str | None:
    try:
        if not VERIFICATION_HOST_CLASS_FILE.is_file():
            return None
        value = VERIFICATION_HOST_CLASS_FILE.read_text(encoding="utf-8").strip().lower()
        return value or None
    except OSError:
        return None


def has_disposable_host_proof() -> bool:
    if read_verification_host_class_file() == ALLOWED_HOST_CLASS:
        return True
    if (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("CI") == "true"
        and os.environ.get("TRUCKERP_VERIFICATION_DISPOSABLE_CI") == DISPOSABLE_CI_MARKER
    ):
        return True
    instance_id = _fetch_ec2_instance_id()
    if instance_id and instance_id in ALLOWED_DISPOSABLE_EC2_INSTANCE_IDS:
        return True
    return False


def collect_verification_denial_reasons() -> list[str]:
    reasons: list[str] = []

    for key in FORBIDDEN_BYPASS_ENV_VARS:
        if os.environ.get(key):
            reasons.append(f"forbidden environment variable {key} is set")

    instance_id = _fetch_ec2_instance_id()
    if instance_id and instance_id in KNOWN_PRODUCTION_EC2_INSTANCE_IDS:
        reasons.append(f"EC2 instance {instance_id} is a known production host")

    if not has_disposable_host_proof():
        reasons.append(
            "missing disposable host proof: require "
            f"{VERIFICATION_HOST_CLASS_FILE}='{ALLOWED_HOST_CLASS}', "
            f"GitHub Actions CI marker '{DISPOSABLE_CI_MARKER}', "
            "or an instance id on ALLOWED_DISPOSABLE_EC2_INSTANCE_IDS"
        )

    for key in URL_ENV_VARS:
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        host = database_host_from_url(raw).lower()
        db_name = (urlparse(raw).path or "").lstrip("/").split("?", 1)[0].lower()
        if host in PRODUCTION_PLATFORM_HOSTS:
            reasons.append(f"{key} targets production database host {host}")
        if db_name in FORBIDDEN_VERIFICATION_DB_NAMES:
            reasons.append(f"{key} targets forbidden database name {db_name}")

    return reasons


def assert_disposable_verification_host() -> None:
    reasons = collect_verification_denial_reasons()
    if reasons:
        raise VerificationHostDenied("; ".join(reasons))


def assert_verification_database_url(url: str, *, context: str) -> None:
    host = database_host_from_url(url).lower()
    db_name = (urlparse(url).path or "").lstrip("/").split("?", 1)[0].lower()
    if host in PRODUCTION_PLATFORM_HOSTS:
        raise VerificationHostDenied(f"{context}: production database host {host}")
    if db_name in FORBIDDEN_VERIFICATION_DB_NAMES:
        raise VerificationHostDenied(f"{context}: forbidden database name {db_name}")
    if host and host not in ALLOWED_VERIFICATION_DB_HOSTS:
        raise VerificationHostDenied(f"{context}: host {host} not in verification allowlist")


def assert_no_live_production_dump_source(source_host: str, source_database: str) -> None:
    host = (source_host or "").strip().lower()
    if source_database == "tenant_demo" and host in PRODUCTION_PLATFORM_HOSTS:
        raise VerificationHostDenied(
            "live pg_dump from production tenant_demo is not permitted for certification; "
            "use disposable_verification_runner with migrations or a sanitized offline artifact"
        )


def assert_verification_auth_not_bypassed() -> None:
    if os.environ.get("TEST_BYPASS_AUTH") == "1":
        raise VerificationHostDenied(
            "TEST_BYPASS_AUTH=1 is not permitted for authorization certification waves"
        )


def refuse_live_demo_clone_ports(sql: object, commands: object) -> None:
    """Block any live demo_clone_runner path (including direct run_clone(LiveSql(), ...))."""
    if sql.__class__.__name__ != "LiveSql" or commands.__class__.__name__ != "LiveCommands":
        return
    raise VerificationHostDenied(
        "demo_clone_runner live execution is disabled; "
        "use scripts/disposable_verification_runner.py"
    )
