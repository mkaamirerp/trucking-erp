"""
Environment sanitization (dry-run plan).

Purpose:
- Identify "leaked" DB env vars (DATABASE_URL, *_URL, etc.)
- Define a sterile subprocess env where ONLY the correct URL var exists

In v0.2, this module ONLY PLANS what would happen.
It does NOT modify your shell env and does NOT execute subprocesses.
"""

from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class EnvPlan:
    removed_keys: list[str]
    set_key: Optional[str]
    notes: str


def plan(context_name: str, tenant_slug: Optional[str]) -> EnvPlan:
    """
    Returns a plan describing how we would sanitize the environment
    for a subprocess execution.

    IMPORTANT: We do NOT yet resolve real DB URLs here.
    """
    removed: list[str] = []

    for k in os.environ.keys():
        if "DATABASE" in k or k.endswith("_URL") or k.startswith("DB_"):
            removed.append(k)

    removed.sort()

    if context_name == "platform":
        # In final form we may still use DATABASE_URL for platform subprocess,
        # but we keep a distinct key to avoid accidental tenant fallbacks.
        return EnvPlan(
            removed_keys=removed,
            set_key="PLATFORM_DATABASE_URL",
            notes="would set PLATFORM_DATABASE_URL (sourced from /run/secrets/truckerp.env DATABASE_URL)",
        )

    if context_name == "tenant":
        if not tenant_slug:
            return EnvPlan(
                removed_keys=removed,
                set_key=None,
                notes="no tenant slug; would refuse to prepare env until --tenant=<slug> provided (later enforcement)",
            )
        return EnvPlan(
            removed_keys=removed,
            set_key="ALEMBIC_TENANT_DATABASE_URL",
            notes=f"would set ALEMBIC_TENANT_DATABASE_URL for tenant '{tenant_slug}' (registry-resolved URL later)",
        )

    return EnvPlan(
        removed_keys=removed,
        set_key=None,
        notes="unknown context; no env var would be set",
    )
