from __future__ import annotations

import asyncio
import os
import unittest
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db_url import to_async_pg_url
from app.schemas.load import LoadCreate, LoadUpdate
from app.services import loads as loads_service


def _tenant_async_engine():
  url = os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
  if not url:
    raise RuntimeError("ALEMBIC_TENANT_DATABASE_URL is required for this runtime test")
  return create_async_engine(to_async_pg_url(url), pool_pre_ping=True)


class TestLoadAuditEvents(unittest.TestCase):
  def test_create_and_update_writes_audit_events(self):
    async def run():
      engine = _tenant_async_engine()
      Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

      tenant_id = 53
      suffix = uuid.uuid4().hex[:8]
      load_number = f"AUDT-{suffix}"

      async with Session() as db:
        # Create load
        created = await loads_service.create_load(
          db,
          tenant_id,
          LoadCreate(
            load_number=load_number,
            status="draft",
            broker_name_snapshot="Test Broker",
            broker_load_reference=f"REF-{suffix}",
            stops=[],
          ),
        )
        load_id = int(created.id)

        # Update load status and driver assignment (writes multiple audit events)
        updated = await loads_service.update_load(
          db,
          tenant_id,
          load_id,
          payload=LoadUpdate(expected_concurrency_version=int(created.concurrency_version), status="ready"),
          actor_user_id=1,
          request_id=f"test-req-{suffix}",
          source="ui",
        )
        _ = updated

      async with Session() as db:
        rows = (await db.execute(text("""
          select action
          from audit_events
          where tenant_id=:tid and entity_type='load' and entity_id=:eid
          order by event_at desc, id desc
          limit 50
        """), {"tid": tenant_id, "eid": str(load_id)})).all()
        actions = [r[0] for r in rows]
        assert "load_created" in actions
        assert "load_updated" in actions or "load_status_changed" in actions

      await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
  unittest.main()

