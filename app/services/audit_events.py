from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import AuditEvent
from app.utils.audit_redaction import classify_visibility, redact_changed_fields, redact_snapshot


ALLOWED_ACTOR_TYPES = {"user", "system", "api", "webhook", "job", "import"}
ALLOWED_SOURCES = {"ui", "api", "background_job", "webhook", "import", "system_rule"}
ALLOWED_VISIBILITY = {"normal", "sensitive", "admin_sensitive", "finance_sensitive"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_entity_id(entity_id: str | int) -> str:
    if isinstance(entity_id, int):
        return str(entity_id)
    s = str(entity_id).strip()
    if not s:
        raise ValueError("entity_id must be non-empty")
    return s


def _require_nonempty(name: str, value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValueError(f"{name} must be non-empty")
    return v


async def write_audit_event(
    db: AsyncSession,
    *,
    tenant_id: int,
    module: str,
    entity_type: str,
    entity_id: str | int,
    action: str,
    source: str,
    # Optional display snapshot
    entity_label: str | None = None,
    # Actor
    actor_type: str | None = None,
    actor_user_id: int | None = None,
    actor_label: str | None = None,
    # Correlation
    request_id: str | None = None,
    correlation_id: str | None = None,
    # Payload (any combination allowed; must have at least one non-empty)
    changed_fields: dict[str, Any] | None = None,
    snapshot_before: dict[str, Any] | None = None,
    snapshot_after: dict[str, Any] | None = None,
    context_json: dict[str, Any] | None = None,
    # Reason
    reason_code: str | None = None,
    reason_note: str | None = None,
    # Meta
    visibility: str = "normal",
    event_at: datetime | None = None,
    best_effort: bool = True,
) -> AuditEvent | None:
    """Write one append-only tenant audit event.

    Slice 1 contract:
    - Enforce allowed enums in code (actor_type/source/visibility).
    - Enforce payload presence: at least one of changed_fields/snapshot_before/snapshot_after/context_json.
    - Allow changed_fields together with snapshots.
    - Default correlation_id to request_id when absent.
    - Redact sensitive fields and upgrade visibility when redaction occurs.
    - best_effort=True never raises; best_effort=False raises.
    """

    try:
        module = _require_nonempty("module", module)
        entity_type = _require_nonempty("entity_type", entity_type)
        action = _require_nonempty("action", action)
        source = _require_nonempty("source", source)

        if source not in ALLOWED_SOURCES:
            raise ValueError(f"source must be one of {sorted(ALLOWED_SOURCES)}")

        vis = (visibility or "normal").strip()
        if vis not in ALLOWED_VISIBILITY:
            raise ValueError(f"visibility must be one of {sorted(ALLOWED_VISIBILITY)}")

        if actor_type is None:
            actor_type = "user" if actor_user_id is not None else "system"
        actor_type = actor_type.strip()
        if actor_type not in ALLOWED_ACTOR_TYPES:
            raise ValueError(f"actor_type must be one of {sorted(ALLOWED_ACTOR_TYPES)}")

        if not any([changed_fields, snapshot_before, snapshot_after, context_json]):
            raise ValueError("At least one of changed_fields, snapshot_before, snapshot_after, context_json is required")

        eid = _normalize_entity_id(entity_id)

        # Correlation defaults
        request_id = (request_id or None) if request_id else None
        correlation_id = correlation_id or request_id

        # Redact payloads
        redacted_keys: set[str] = set()
        redacted_changed: dict[str, Any] | None = None
        if changed_fields is not None:
            redacted_changed, red = redact_changed_fields(changed_fields)
            redacted_keys |= red

        red_before, red = redact_snapshot(snapshot_before)
        redacted_keys |= red
        red_after, red = redact_snapshot(snapshot_after)
        redacted_keys |= red

        vis = classify_visibility(base_visibility=vis, redacted_fields=redacted_keys)

        row = AuditEvent(
            tenant_id=int(tenant_id),
            event_at=event_at or _utcnow(),
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            actor_label=(actor_label[:128] if actor_label else None),
            module=module[:32],
            entity_type=entity_type[:64],
            entity_id=eid[:128],
            entity_label=(entity_label[:256] if entity_label else None),
            action=action[:64],
            subaction=None,
            request_id=(request_id[:64] if request_id else None),
            correlation_id=(correlation_id[:64] if correlation_id else None),
            source=source[:32],
            reason_code=(reason_code[:64] if reason_code else None),
            reason_note=reason_note,
            visibility=vis,
            changed_fields=redacted_changed,
            snapshot_before=red_before,
            snapshot_after=red_after,
            context_json=context_json,
        )
        db.add(row)
        await db.flush()
        return row
    except Exception:
        if best_effort:
            return None
        raise

