"""Load / rate-confirmation parser: tenant identity exclusion builder + cache.

Runtime-derived from PlatformTenant + PlatformCompanyProfile only.
No broker detection. No hardcoded tenant/company values. No OpenAI payload wiring.

See docs/TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md §4–§5.
This slice returns the flat exclusion object used by future OpenAI input assembly.

Cache key: ``load_parser_tenant_identity:{tenant_id}`` — in-process TTL dict of
already-built flat dicts (never ORM instances). Safe on this host: single uvicorn
process (no ``--workers``). See ``get_load_parser_tenant_identity_exclusion``.
"""

from __future__ import annotations

import copy
import re
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.platform import PlatformCompanyProfile, PlatformTenant

# In-process cache (Slice 1B). Not Redis — single API worker on this deployment.
CACHE_KEY_PREFIX = "load_parser_tenant_identity"
# Safety fallback even when profile write paths invalidate (30 minutes).
DEFAULT_TTL_SECONDS = 30 * 60

_cache_lock = threading.RLock()


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: float
    value: dict[str, Any]


_CACHE: dict[int, _CacheEntry] = {}

# Public mailbox providers — never treat as company-owned email domains.
_PUBLIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "ymail.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "protonmail.com",
        "proton.me",
        "mail.com",
        "gmx.com",
        "gmx.net",
    }
)

_NON_DIGIT_RE = re.compile(r"\D+")
_NON_ALNUM_RE = re.compile(r"[^0-9A-Za-z]+")
_WHITESPACE_RE = re.compile(r"\s+")


def _empty_exclusion() -> dict[str, Any]:
    # Rate-con relevant only (sources: PlatformTenant.name + selected profile fields).
    # Not included: cvor_number, address_region, address_country, operator_license, etc.
    return {
        "names": [],
        "mc_numbers": [],
        "usdot_numbers": [],
        "phones": [],
        "emails": [],
        "email_domains": [],
        "addresses": [],
    }


def normalize_display_name(value: str | None) -> str | None:
    """Collapse whitespace; keep original casing for display. Empty → None."""
    if value is None:
        return None
    collapsed = _WHITESPACE_RE.sub(" ", str(value)).strip()
    return collapsed or None


def normalize_name_key(value: str | None) -> str:
    """Casefold key for dedupe only."""
    n = normalize_display_name(value)
    return n.casefold() if n else ""


def normalize_phone_digits(value: str | None) -> str | None:
    """Comparable phone digits only. No formatting variants."""
    if value is None:
        return None
    digits = _NON_DIGIT_RE.sub("", str(value))
    if not digits:
        return None
    # NANP: drop leading country code 1 when 11 digits.
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) < 7:
        return None
    return digits


def normalize_authority_id(value: str | None) -> str | None:
    """MC / USDOT / CVOR: strip punctuation/spaces; keep digits (and rare alnum)."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    # Prefer pure digits when present (typical MC/DOT).
    digits = _NON_DIGIT_RE.sub("", raw)
    if digits:
        # Drop leading zeros only when leaving at least one digit.
        stripped = digits.lstrip("0")
        return stripped or "0"
    cleaned = _NON_ALNUM_RE.sub("", raw).upper()
    return cleaned or None


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    e = str(value).strip().casefold()
    if not e or "@" not in e:
        return None
    local, _, domain = e.partition("@")
    if not local or not domain or "." not in domain:
        return None
    return f"{local}@{domain}"


def email_domain(value: str | None) -> str | None:
    e = normalize_email(value)
    if not e:
        return None
    return e.rsplit("@", 1)[-1]


def is_public_email_domain(domain: str | None) -> bool:
    if not domain:
        return False
    return domain.casefold().strip() in _PUBLIC_EMAIL_DOMAINS


def normalize_address_field(value: str | None, *, upper: bool = False) -> str | None:
    if value is None:
        return None
    v = _WHITESPACE_RE.sub(" ", str(value)).strip()
    if not v:
        return None
    return v.upper() if upper else v


def normalize_postal(value: str | None) -> str | None:
    """Collapse spaces; uppercase (CA postal style)."""
    v = normalize_address_field(value, upper=True)
    if not v:
        return None
    return v.replace(" ", "")


def _dedupe_preserve(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        key = v.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def build_address_dict(
    *,
    street: str | None = None,
    city: str | None = None,
    postal: str | None = None,
) -> dict[str, str] | None:
    """Rate-con address: street / city / postal only. None if unusable."""
    s = normalize_address_field(street)
    c = normalize_address_field(city)
    p = normalize_postal(postal)
    addr: dict[str, str] = {}
    if s:
        addr["street"] = s
    if c:
        addr["city"] = c
    if p:
        addr["postal"] = p
    if not addr.get("street") and not addr.get("city"):
        return None
    return addr


def build_load_parser_tenant_identity_exclusion(
    *,
    tenant: PlatformTenant | None = None,
    profile: PlatformCompanyProfile | None = None,
    tenant_name: str | None = None,
    legal_name: str | None = None,
    mc_number: str | None = None,
    usdot_number: str | None = None,
    company_phone: str | None = None,
    company_email: str | None = None,
    address_street: str | None = None,
    address_city: str | None = None,
    address_postal: str | None = None,
) -> dict[str, Any]:
    """Build flat tenant_identity_exclusion for the Load rate-con parser.

    Profile sources (only):
      legal_name, mc_number, usdot_number, company_phone, company_email,
      address_street, address_city, address_postal
    Plus PlatformTenant.name → names[].

    Accepts ORM objects and/or explicit field overrides (tests).
    Does not invent formatting variants. No broker logic.
    """
    out = _empty_exclusion()

    t_name = tenant_name
    if t_name is None and tenant is not None:
        t_name = getattr(tenant, "name", None)

    p = profile
    if legal_name is None and p is not None:
        legal_name = getattr(p, "legal_name", None)
    if mc_number is None and p is not None:
        mc_number = getattr(p, "mc_number", None)
    if usdot_number is None and p is not None:
        usdot_number = getattr(p, "usdot_number", None)
    if company_phone is None and p is not None:
        company_phone = getattr(p, "company_phone", None)
    if company_email is None and p is not None:
        company_email = getattr(p, "company_email", None)

    if address_street is None and p is not None:
        address_street = getattr(p, "address_street", None)
    if address_city is None and p is not None:
        address_city = getattr(p, "address_city", None)
    if address_postal is None and p is not None:
        address_postal = getattr(p, "address_postal", None)

    names: list[str] = []
    for candidate in (t_name, legal_name):
        n = normalize_display_name(candidate)
        if n:
            names.append(n)
    by_key: dict[str, str] = {}
    for n in names:
        key = normalize_name_key(n)
        if key and key not in by_key:
            by_key[key] = n
    out["names"] = list(by_key.values())

    mc = normalize_authority_id(mc_number)
    if mc:
        out["mc_numbers"] = [mc]
    usdot = normalize_authority_id(usdot_number)
    if usdot:
        out["usdot_numbers"] = [usdot]

    phone = normalize_phone_digits(company_phone)
    if phone:
        out["phones"] = [phone]

    email = normalize_email(company_email)
    if email:
        out["emails"] = [email]
        domain = email_domain(email)
        if domain and not is_public_email_domain(domain):
            out["email_domains"] = [domain]

    addr = build_address_dict(
        street=address_street,
        city=address_city,
        postal=address_postal,
    )
    if addr:
        out["addresses"] = [addr]

    for key in ("names", "mc_numbers", "usdot_numbers", "phones", "emails", "email_domains"):
        out[key] = _dedupe_preserve([str(v) for v in out[key] if v is not None and str(v).strip()])
    return out


async def load_platform_tenant_with_company_profile(
    platform_db: AsyncSession,
    *,
    tenant_id: int,
) -> tuple[PlatformTenant | None, PlatformCompanyProfile | None]:
    """Read PlatformTenant + company_profile from the platform DB session.

    Same query pattern as ``company_contact.get_canonical_company_contact_for_documents``.
    Caller must pass a **platform** AsyncSession (``get_db`` / ``AsyncSessionLocal``),
    not the tenant business DB.
    """
    tenant = await platform_db.scalar(
        select(PlatformTenant)
        .options(selectinload(PlatformTenant.company_profile))
        .where(PlatformTenant.id == int(tenant_id))
    )
    if not tenant:
        return None, None
    profile = tenant.company_profile
    return tenant, profile


async def build_load_parser_tenant_identity_exclusion_for_tenant(
    platform_db: AsyncSession,
    *,
    tenant_id: int,
) -> dict[str, Any]:
    """Load platform tenant/profile and build exclusion. Missing profile → empty arrays.

    Uncached loader. Prefer ``get_load_parser_tenant_identity_exclusion`` at request time.
    """
    tenant, profile = await load_platform_tenant_with_company_profile(
        platform_db, tenant_id=tenant_id
    )
    if tenant is None:
        return _empty_exclusion()
    return build_load_parser_tenant_identity_exclusion(tenant=tenant, profile=profile)


def cache_key_for_tenant(tenant_id: int) -> str:
    """Logical cache key string (for docs/tests). Storage is keyed by int tenant_id."""
    return f"{CACHE_KEY_PREFIX}:{int(tenant_id)}"


def invalidate_load_parser_tenant_identity_cache(tenant_id: int | None = None) -> None:
    """Drop one tenant's entry, or all entries when ``tenant_id`` is None.

    Call after PlatformCompanyProfile create/update (identity fields) and after any
    future PlatformTenant.name change (name contributes to ``names[]``).
    """
    with _cache_lock:
        if tenant_id is None:
            _CACHE.clear()
            return
        _CACHE.pop(int(tenant_id), None)


def _cache_get(tenant_id: int, *, now: float) -> dict[str, Any] | None:
    tid = int(tenant_id)
    with _cache_lock:
        entry = _CACHE.get(tid)
        if entry is None:
            return None
        if entry.expires_at <= now:
            _CACHE.pop(tid, None)
            return None
        # Defensive copy so callers cannot mutate the stored object.
        return copy.deepcopy(entry.value)


def _cache_set(tenant_id: int, value: dict[str, Any], *, expires_at: float) -> None:
    tid = int(tenant_id)
    with _cache_lock:
        _CACHE[tid] = _CacheEntry(expires_at=expires_at, value=copy.deepcopy(value))


async def get_load_parser_tenant_identity_exclusion(
    platform_db: AsyncSession | None,
    *,
    tenant_id: int,
    loader: Callable[[AsyncSession | None, int], Awaitable[dict[str, Any]]] | None = None,
    ttl_seconds: float | None = None,
    now_fn: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Return flat tenant_identity_exclusion, preferring in-process TTL cache.

    On miss: calls ``loader`` (default: ``build_load_parser_tenant_identity_exclusion_for_tenant``)
    then stores a deep copy. Always returns a deep copy so one caller cannot contaminate
    later parses.

    Not wired into OpenAI / parse-document yet (Slice 2).
    """
    tid = int(tenant_id)
    clock = now_fn or time.monotonic
    now = float(clock())
    hit = _cache_get(tid, now=now)
    if hit is not None:
        return hit

    async def _default_loader(db: AsyncSession | None, tenant_id_: int) -> dict[str, Any]:
        if db is None:
            raise ValueError("platform_db is required when loader is not injected")
        return await build_load_parser_tenant_identity_exclusion_for_tenant(
            db, tenant_id=tenant_id_
        )

    use_loader = loader or _default_loader
    built = await use_loader(platform_db, tid)
    # Normalize to a plain dict shape; never store ORM.
    if not isinstance(built, dict):
        raise TypeError("loader must return a dict (flat exclusion), not ORM objects")
    ttl = DEFAULT_TTL_SECONDS if ttl_seconds is None else float(ttl_seconds)
    _cache_set(tid, built, expires_at=now + max(0.0, ttl))
    return copy.deepcopy(built)
