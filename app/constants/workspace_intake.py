"""Locked package identities for public workspace intake (architecture-level, not UI labels)."""

from __future__ import annotations

from typing import Final

WORKSPACE_INTAKE_PACKAGE_CODES: Final[frozenset[str]] = frozenset(
    {"FREE_TRIAL", "BASIC", "PRO", "ENTERPRISE"}
)

WORKSPACE_INTAKE_STATUS_PENDING: Final[str] = "pending"
WORKSPACE_INTAKE_STATUS_EMAILED: Final[str] = "emailed"
WORKSPACE_INTAKE_STATUS_CONSUMED: Final[str] = "consumed"
WORKSPACE_INTAKE_STATUS_EXPIRED: Final[str] = "expired"

WORKSPACE_INTAKE_COOKIE_NAME: Final[str] = "workspace_intake_session"
WORKSPACE_INTAKE_CONTINUATION_TTL_SEC: Final[int] = 2 * 60 * 60
WORKSPACE_INTAKE_LINK_TTL_SEC: Final[int] = 24 * 60 * 60
