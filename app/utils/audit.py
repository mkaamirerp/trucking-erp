"""
Audit logging helper for TruckERP.

Goal:
- Give us ONE place to emit audit events (who did what, to which object, when).
- Keep it safe: audit failures should never break the main request flow.

This module is intentionally lightweight and defensive.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(obj: Any) -> Any:
    """
    Best-effort convert to JSON-safe value.
    """
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


def emit_audit_event(
    db: Any,
    *,
    tenant_id: int,
    actor_user_id: Optional[int],
    action: str,
    object_type: str,
    object_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """
    Writes an audit event into the tenant DB.

    Assumptions (matches our TruckERP architecture):
    - Audit table/model lives in TENANT DB (business data).
    - We do NOT want audit write errors to break the main flow.

    This function tries to import the tenant audit model lazily to avoid circular imports.
    If the model/table isn't present yet, it will log a warning and return.
    """
    details = details or {}
    safe_details = {k: _jsonable(v) for k, v in details.items()}

    try:
        # Lazy import to avoid circular dependency at import-time
        from app.models.tenant import TenantAuditLog  # type: ignore
    except Exception as e:
        logger.warning("Audit model missing/unimportable; skipping audit event. err=%r", e)
        return

    try:
        row = TenantAuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            details_json=safe_details,
            ip=ip,
            user_agent=user_agent,
            created_at=_utc_now(),
        )
        db.add(row)
        # Do not commit here: caller owns transaction boundaries.
        # Flush so that failures show up early but still rollback with caller if needed.
        db.flush()
    except Exception as e:
        logger.exception("Audit write failed; continuing without audit. err=%r", e)
        try:
            db.rollback()
        except Exception:
            # Ignore rollback failures; never raise from audit
            pass
        return
