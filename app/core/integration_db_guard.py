"""Hard isolation rules for DB-mutating integration tests.

Production runtime does not import these checks into normal request paths except
when TEST_BYPASS_AUTH is active (already restricted to safe ENVIRONMENT).

Do not weaken these rules to “skip” on misconfiguration — fail loudly.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

# Live shared demo workspace — never a mutation target for integration tests.
FORBIDDEN_INTEGRATION_TENANT_SLUGS = frozenset({"demo"})
FORBIDDEN_INTEGRATION_TENANT_DB_NAMES = frozenset({"tenant_demo"})

# Dedicated disposable integration tenant (override via env; never hardcode credentials).
DEFAULT_INTEGRATION_TENANT_SLUG = "pytest"
DEFAULT_INTEGRATION_TENANT_DB_NAME = "tenant_pytest"

ENV_INTEGRATION_SLUG = "TRUCKERP_INTEGRATION_TENANT_SLUG"
ENV_INTEGRATION_DB = "TRUCKERP_INTEGRATION_TENANT_DB"
ENV_ALLOWED_DB_NAMES = "TRUCKERP_INTEGRATION_ALLOWED_DB_NAMES"


class IntegrationIsolationError(RuntimeError):
    """Raised when an integration test would touch demo/production shared tenant data."""


def integration_tenant_slug() -> str:
    return (os.environ.get(ENV_INTEGRATION_SLUG) or DEFAULT_INTEGRATION_TENANT_SLUG).strip().lower()


def integration_tenant_db_name() -> str:
    return (os.environ.get(ENV_INTEGRATION_DB) or DEFAULT_INTEGRATION_TENANT_DB_NAME).strip().lower()


def allowed_integration_db_names() -> frozenset[str]:
    names = {integration_tenant_db_name()}
    extra = os.environ.get(ENV_ALLOWED_DB_NAMES) or ""
    for part in extra.split(","):
        p = part.strip().lower()
        if p:
            names.add(p)
    return frozenset(names)


def allowed_integration_slugs() -> frozenset[str]:
    return frozenset({integration_tenant_slug()})


def database_name_from_url(url: str) -> str:
    """Return PostgreSQL database name from a URL (no credentials returned)."""
    if not url or not str(url).strip():
        return ""
    parsed = urlparse(str(url).strip())
    path = (parsed.path or "").lstrip("/")
    # path may be "dbname" or "dbname?params" depending on parser
    return path.split("?", 1)[0].strip().lower()


def assert_integration_db_name_allowed(db_name: str | None, *, context: str) -> None:
    name = (db_name or "").strip().lower()
    if not name:
        raise IntegrationIsolationError(
            f"Integration isolation: empty tenant database name ({context}). "
            f"Configure {ENV_INTEGRATION_DB} / TENANT_DATABASE_URL to "
            f"{DEFAULT_INTEGRATION_TENANT_DB_NAME}."
        )
    if name in FORBIDDEN_INTEGRATION_TENANT_DB_NAMES:
        raise IntegrationIsolationError(
            f"Integration isolation: refusing tenant DB {name!r} ({context}). "
            f"Mutating {sorted(FORBIDDEN_INTEGRATION_TENANT_DB_NAMES)} is forbidden. "
            f"Point TENANT_DATABASE_URL / ALEMBIC_TENANT_DATABASE_URL at "
            f"{integration_tenant_db_name()!r}."
        )
    allowed = allowed_integration_db_names()
    if name not in allowed:
        raise IntegrationIsolationError(
            f"Integration isolation: tenant DB {name!r} is not an allowed integration "
            f"database ({context}). Allowed: {sorted(allowed)}. "
            f"Refusing non-dedicated / production tenant DBs."
        )


def assert_integration_tenant_slug_allowed(slug: str | None, *, context: str) -> None:
    s = (slug or "").strip().lower()
    if not s:
        raise IntegrationIsolationError(
            f"Integration isolation: empty tenant slug ({context}). "
            f"Use Host {integration_tenant_slug()}.truckerp.me."
        )
    if s in FORBIDDEN_INTEGRATION_TENANT_SLUGS:
        raise IntegrationIsolationError(
            f"Integration isolation: refusing tenant slug {s!r} ({context}). "
            f"Host must not resolve to the live demo tenant. "
            f"Use slug {integration_tenant_slug()!r}."
        )
    if s not in allowed_integration_slugs():
        raise IntegrationIsolationError(
            f"Integration isolation: tenant slug {s!r} is not the dedicated "
            f"integration tenant ({context}). Allowed: {sorted(allowed_integration_slugs())}."
        )


def assert_integration_host_allowed(host: str | None, *, context: str) -> None:
    h = (host or "").strip().lower()
    if not h:
        raise IntegrationIsolationError(f"Integration isolation: empty Host ({context}).")
    # Strip port if present
    h = h.split(":", 1)[0]
    if h == "demo.truckerp.me" or h.startswith("demo."):
        raise IntegrationIsolationError(
            f"Integration isolation: refusing Host {h!r} ({context}). "
            f"demo.truckerp.me maps to the live demo tenant. "
            f"Use {integration_tenant_slug()}.truckerp.me."
        )
    expected = f"{integration_tenant_slug()}.truckerp.me"
    if h != expected and not h.startswith(f"{integration_tenant_slug()}."):
        raise IntegrationIsolationError(
            f"Integration isolation: Host {h!r} is not the dedicated integration "
            f"host ({context}). Expected {expected!r}."
        )


def assert_tenant_database_url_allowed(url: str | None, *, context: str) -> None:
    if not url or not str(url).strip():
        raise IntegrationIsolationError(
            f"Integration isolation: TENANT_DATABASE_URL / ALEMBIC_TENANT_DATABASE_URL "
            f"missing ({context}). Set it to database {integration_tenant_db_name()!r}."
        )
    assert_integration_db_name_allowed(database_name_from_url(url), context=context)


def assert_environment_allows_integration_mutation(*, context: str) -> None:
    """Fail if caller still looks like production shared-demo (beyond URL checks)."""
    env = (os.environ.get("ENVIRONMENT") or "").strip().lower()
    # conftest forces ENVIRONMENT=test for pytest; production runtime must not mutate via these helpers.
    if env in {"production", "prod"}:
        raise IntegrationIsolationError(
            f"Integration isolation: ENVIRONMENT={env!r} ({context}). "
            f"DB-mutating integration helpers refuse production/shared-demo environments."
        )
