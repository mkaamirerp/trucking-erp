from __future__ import annotations

import asyncio
import unittest

# Ensure SQLAlchemy class registry includes relationship targets referenced by string name.
# Without these imports, mapper configuration can fail in isolated test contexts.
import app.models.application_access_token  # noqa: F401
import app.models.person_application  # noqa: F401

from app.services.people_workspace import write_people_patch_audit
from app.models.tenant_audit import TenantAuditLog
from app.models.tenant_audit_event import AuditEvent


class FakeAsyncSession:
    def __init__(self):
        self.added = []
        self.flushed = 0

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        self.flushed += 1


class TestPeopleAuditDualWrite(unittest.TestCase):
    def test_dual_write_adds_legacy_and_new_rows(self):
        async def run():
            db = FakeAsyncSession()
            await write_people_patch_audit(
                db,
                tenant_id=53,
                person_id=35,
                actor_user_id=1,
                changed={"email": {"before": "a", "after": "b"}, "ssn": {"before": "x", "after": "y"}},
                ip="1.2.3.4",
                user_agent="ua",
                request_id="req-1",
                action="people_core_patch",
            )
            return db

        db = asyncio.run(run())
        types = {type(x) for x in db.added}
        self.assertIn(TenantAuditLog, types)
        self.assertIn(AuditEvent, types)


if __name__ == "__main__":
    unittest.main()

