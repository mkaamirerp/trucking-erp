from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db_url import to_async_pg_url
from app.models.tenant import AuditEvent, TenantAuditLog
from app.services.people_workspace import list_people_maintenance_audit_entries

# Ensure SQLAlchemy registry includes relationship targets referenced by string name.
import app.models.application_access_token  # noqa: F401
import app.models.person_application  # noqa: F401


def _tenant_async_engine():
    url = os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not url:
        raise RuntimeError("ALEMBIC_TENANT_DATABASE_URL is required for this runtime test")
    return create_async_engine(to_async_pg_url(url), pool_pre_ping=True)


class TestPeopleAuditReadCutover(unittest.TestCase):
    def test_new_only_legacy_only_mixed_and_ordering(self):
        async def run():
            engine = _tenant_async_engine()
            Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with Session() as db:
                # Use an uncommitted transaction so we don't persist proof rows.
                async with db.begin():
                    tenant_id = 53
                    person_id = 35

                    now = datetime.now(timezone.utc)
                    older = now - timedelta(minutes=5)

                    # 1) legacy-only
                    legacy = TenantAuditLog(
                        tenant_id=tenant_id,
                        actor_user_id=1,
                        action="people_core_patch",
                        object_type="person",
                        object_id=str(person_id),
                        details_json={"changed_keys": ["email"], "snapshot": {"email": {"before": "a", "after": "b"}}},
                        ip="1.1.1.1",
                        user_agent="legacy",
                        created_at=older,
                    )
                    db.add(legacy)
                    await db.flush()

                    rows = await list_people_maintenance_audit_entries(
                        db, tenant_id=tenant_id, person_id=person_id, limit=50, offset=0
                    )
                    # In mixed mode we might also see other existing rows in DB.
                    # Assert at least one legacy-shaped row exists.
                    assert any(getattr(r, "details_json", {}).get("snapshot", {}).get("email") for r in rows)

                    # 2) new-only (audit_events)
                    ev = AuditEvent(
                        tenant_id=tenant_id,
                        event_at=now,
                        actor_type="user",
                        actor_user_id=1,
                        actor_label=None,
                        module="people",
                        entity_type="person",
                        entity_id=str(person_id),
                        entity_label=None,
                        action="people_core_patch",
                        subaction=None,
                        request_id="test-req-1",
                        correlation_id="test-req-1",
                        source="ui",
                        reason_code=None,
                        reason_note=None,
                        visibility="normal",
                        changed_fields={"phone": {"before": None, "after": "555"}},
                        snapshot_before=None,
                        snapshot_after=None,
                        context_json={"legacy": {"ip": "2.2.2.2", "user_agent": "new"}},
                    )
                    db.add(ev)
                    await db.flush()

                    rows2 = await list_people_maintenance_audit_entries(
                        db, tenant_id=tenant_id, person_id=person_id, limit=50, offset=0
                    )
                    # Mixed rows should include both payloads
                    has_phone = any(getattr(r, "details_json", {}).get("snapshot", {}).get("phone") for r in rows2)
                    has_email = any(getattr(r, "details_json", {}).get("snapshot", {}).get("email") for r in rows2)
                    assert has_phone and has_email

                    # Ordering: newest event_at (audit_events) should come first.
                    # We check that the first matching row has phone snapshot (newer).
                    first_snapshot = None
                    for r in rows2:
                        snap = getattr(r, "details_json", {}).get("snapshot")
                        if isinstance(snap, dict) and snap:
                            first_snapshot = snap
                            break
                    assert first_snapshot is not None
                    assert "phone" in first_snapshot

                await engine.dispose()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()

