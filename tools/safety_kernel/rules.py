"""
Rules skeleton (dry-run).

Defines what WOULD be allowed.
No enforcement yet.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RuleCheck:
    allowed: bool
    reason: str


def check(context_name: str, tenant_slug: Optional[str]) -> RuleCheck:
    """
    Dry-run rule evaluation.
    """
    if context_name == "platform":
        return RuleCheck(
            allowed=True,
            reason="platform context allowed (dry-run)",
        )

    if context_name == "tenant":
        if not tenant_slug:
            return RuleCheck(
                allowed=False,
                reason="tenant context requires --tenant=<slug>",
            )
        return RuleCheck(
            allowed=True,
            reason="tenant context allowed (dry-run)",
        )

    return RuleCheck(
        allowed=False,
        reason="unknown context",
    )
