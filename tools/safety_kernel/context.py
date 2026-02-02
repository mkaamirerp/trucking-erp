"""
Context detection (dry-run).

Figures out WHAT the user is trying to do,
without enforcing or executing anything.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class DetectedContext:
    name: str                 # platform | tenant | unknown
    action: str               # e.g. "migrate", "alembic", etc.
    tenant_slug: Optional[str]
    notes: str


def detect(argv: list[str]) -> DetectedContext:
    """
    Pattern:
      kernel status
      kernel platform <action>
      kernel tenant <action> --tenant=<slug>

    No inference, no defaults.
    """
    if len(argv) < 2:
        return DetectedContext(
            name="unknown",
            action="",
            tenant_slug=None,
            notes="no command provided",
        )

    # "status" is a special top-level command.
    if argv[1] == "status":
        return DetectedContext(
            name="unknown",
            action="status",
            tenant_slug=None,
            notes="status requested",
        )

    context = argv[1]
    action = argv[2] if len(argv) >= 3 else ""

    tenant_slug = None
    for arg in argv:
        if arg.startswith("--tenant="):
            tenant_slug = arg.split("=", 1)[1]

    if context == "platform":
        return DetectedContext(
            name="platform",
            action=action,
            tenant_slug=None,
            notes="platform context requested",
        )

    if context == "tenant":
        return DetectedContext(
            name="tenant",
            action=action,
            tenant_slug=tenant_slug,
            notes="tenant context requested",
        )

    return DetectedContext(
        name="unknown",
        action=" ".join(argv[1:]),
        tenant_slug=tenant_slug,
        notes="unrecognized context",
    )
