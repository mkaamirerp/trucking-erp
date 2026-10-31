"""Shared tenant audit actor for Load mutations (display name + tenant user id)."""

from __future__ import annotations

from app.deps.auth import CurrentUser


def signed_in_actor_label(user: CurrentUser) -> str | None:
    """Name of the logged-in account, for audit display. Email is not stored."""
    tu = user.tenant_user
    platform = user.user
    first = ((tu.first_name if tu is not None else None) or platform.first_name or "").strip()
    last = ((tu.last_name if tu is not None else None) or platform.last_name or "").strip()
    name = " ".join(part for part in (first, last) if part)
    if not name:
        return None
    return name[:128]


def load_audit_actor(user: CurrentUser) -> tuple[int | None, str | None]:
    """Tenant audit_events.actor_user_id is tenant-scoped int — not platform UUID."""
    actor_user_id = int(user.tenant_user.id) if user.tenant_user else None
    return actor_user_id, signed_in_actor_label(user)
