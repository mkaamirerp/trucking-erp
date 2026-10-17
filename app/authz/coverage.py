"""Read-only comparison of catalog bindings with registered FastAPI routes.

This module does not attach dependencies and does not import the application
at import time.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.authz.routes import ROUTE_BINDINGS

_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})

# Infrastructure, public auth, platform control-plane, and webhook paths.
# Business modules are not listed here. Brokers, terminals, load lab, and
# email intake stay unmapped until a later catalog change.
_EXACT_EXCLUSIONS = frozenset(
    {
        ("GET", "/"),
        ("GET", "/dashboard"),
        ("GET", "/healthz"),
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/healthz"),
        ("GET", "/api/v1/dashboard"),
        ("GET", "/openapi.json"),
        ("GET", "/docs"),
        ("GET", "/docs/oauth2-redirect"),
        ("GET", "/redoc"),
    }
)


@dataclass(frozen=True)
class RouteCoverage:
    mapped: tuple[tuple[str, str], ...]
    intentionally_excluded: tuple[tuple[str, str], ...]
    unmapped: tuple[tuple[str, str], ...]
    stale: tuple[tuple[str, str], ...]


def registered_operations(app: object) -> tuple[tuple[str, str], ...]:
    """Return method/path pairs from a FastAPI application's route table."""
    from fastapi.routing import APIRoute

    found: list[tuple[str, str]] = []
    for route in getattr(app, "routes", ()):
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods or ()):
            if method not in _HTTP_METHODS:
                continue
            found.append((method, route.path))
    return tuple(found)


def intentionally_excluded(method: str, path: str) -> bool:
    if (method, path) in _EXACT_EXCLUSIONS:
        return True
    return path.startswith(
        (
            "/api/v1/public/",
            "/api/v1/platform/",
            "/api/v1/auth/",
            "/webhooks/",
        )
    ) or path in {"/api/v1/public", "/api/v1/platform", "/api/v1/auth"}


def audit_route_coverage(app: object) -> RouteCoverage:
    """Classify every registered operation. Does not change the application."""
    registered = set(registered_operations(app))
    mapped_keys = set(ROUTE_BINDINGS)
    mapped = tuple(sorted(registered & mapped_keys))
    remaining = registered - mapped_keys
    excluded = tuple(sorted(key for key in remaining if intentionally_excluded(*key)))
    unmapped = tuple(sorted(remaining - set(excluded)))
    stale = tuple(sorted(mapped_keys - registered))
    return RouteCoverage(
        mapped=mapped,
        intentionally_excluded=excluded,
        unmapped=unmapped,
        stale=stale,
    )
