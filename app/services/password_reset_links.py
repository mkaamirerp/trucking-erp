"""Server-built password-reset URLs. Never take origin from the request body."""

from __future__ import annotations

from urllib.parse import urlparse

from app.core.config import settings

_RESERVED_SUBDOMAINS = frozenset({"www", "api", "app"})


def _safe_tenant_slug(raw: str | None) -> str | None:
    slug = (raw or "").strip().lower()
    if not slug or slug in _RESERVED_SUBDOMAINS:
        return None
    if "." in slug:
        return None
    if not slug.replace("-", "").isalnum():
        return None
    return slug


def _origin_from_override(raw: str) -> str | None:
    parsed = urlparse((raw or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def password_reset_public_origin(*, tenant_slug: str | None, cfg=None) -> str:
    """
    Trusted origin for emailed reset links.

    Production/staging: https://{slug.}base_domain only.
    Test/dev may use password_reset_public_origin from server config (not the client).
    """
    s = cfg or settings
    if not s.is_production_or_staging():
        override = _origin_from_override(getattr(s, "password_reset_public_origin", None) or "")
        if override:
            return override
    domain = (s.base_domain or "truckerp.me").strip().lstrip(".").lower()
    slug = _safe_tenant_slug(tenant_slug)
    if slug:
        return f"https://{slug}.{domain}"
    return f"https://{domain}"


def build_password_reset_link(*, raw_token: str, tenant_slug: str | None, cfg=None) -> str:
    origin = password_reset_public_origin(tenant_slug=tenant_slug, cfg=cfg)
    token = (raw_token or "").strip()
    return f"{origin}/reset-password?token={token}"
