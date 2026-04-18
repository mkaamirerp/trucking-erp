from __future__ import annotations

import pytest

from app.services.audit_events import write_audit_event
from app.utils.audit_redaction import classify_visibility, redact_changed_fields, redact_snapshot


class FakeAsyncSession:
    def __init__(self, *, fail_add: bool = False):
        self.fail_add = fail_add
        self.added = []
        self.flushed = False

    def add(self, row):
        if self.fail_add:
            raise RuntimeError("db add failed")
        self.added.append(row)

    async def flush(self):
        self.flushed = True


def test_redact_changed_fields_redacts_sensitive_keys():
    redacted, keys = redact_changed_fields(
        {
            "email": {"before": "a@x.com", "after": "b@x.com"},
            "ssn": {"before": "111-11-1111", "after": "222-22-2222"},
            "api_token": "abc",
        }
    )
    assert "ssn" in keys
    assert "api_token" in keys
    assert redacted["ssn"]["redacted"] is True
    assert redacted["api_token"]["redacted"] is True
    assert redacted["email"]["before"] == "a@x.com"
    assert redacted["email"]["after"] == "b@x.com"


def test_redact_snapshot_redacts_top_level_sensitive_keys():
    redacted, keys = redact_snapshot({"name": "X", "password": "pw", "token": "t"})
    assert redacted["name"] == "X"
    assert redacted["password"] is None
    assert redacted["token"] is None
    assert keys == {"password", "token"}


def test_visibility_upgrades_to_sensitive_when_redaction_occurs():
    assert classify_visibility(base_visibility="normal", redacted_fields={"ssn"}) == "sensitive"
    assert classify_visibility(base_visibility="admin_sensitive", redacted_fields={"ssn"}) == "admin_sensitive"


@pytest.mark.asyncio
async def test_write_audit_event_defaults_actor_type_and_correlation():
    db = FakeAsyncSession()
    row = await write_audit_event(
        db,
        tenant_id=1,
        module="people",
        entity_type="person",
        entity_id=123,
        entity_label="Jane Driver",
        action="people_core_patch",
        source="api",
        actor_user_id=7,
        request_id="req-1",
        changed_fields={"email": {"before": "a@x.com", "after": "b@x.com"}},
        best_effort=False,
    )
    assert row is not None
    assert row.actor_type == "user"
    assert row.request_id == "req-1"
    assert row.correlation_id == "req-1"
    assert row.entity_id == "123"
    assert row.entity_label == "Jane Driver"
    assert db.flushed is True


@pytest.mark.asyncio
async def test_write_audit_event_allows_changed_fields_and_snapshots_together():
    db = FakeAsyncSession()
    row = await write_audit_event(
        db,
        tenant_id=1,
        module="loads",
        entity_type="load",
        entity_id="55",
        action="load_updated",
        source="ui",
        changed_fields={"status": {"before": "draft", "after": "assigned"}},
        snapshot_after={"status": "assigned", "token": "should_redact"},
        best_effort=False,
    )
    assert row is not None
    assert row.changed_fields["status"]["after"] == "assigned"
    assert row.snapshot_after["token"] is None


@pytest.mark.asyncio
async def test_write_audit_event_rejects_missing_payload_when_strict():
    db = FakeAsyncSession()
    with pytest.raises(ValueError):
        await write_audit_event(
            db,
            tenant_id=1,
            module="people",
            entity_type="person",
            entity_id="1",
            action="updated",
            source="api",
            best_effort=False,
        )


@pytest.mark.asyncio
async def test_write_audit_event_best_effort_swallows_db_failure():
    db = FakeAsyncSession(fail_add=True)
    row = await write_audit_event(
        db,
        tenant_id=1,
        module="people",
        entity_type="person",
        entity_id="1",
        action="updated",
        source="api",
        changed_fields={"token": {"before": "a", "after": "b"}},
        best_effort=True,
    )
    assert row is None


@pytest.mark.asyncio
async def test_write_audit_event_strict_raises_db_failure():
    db = FakeAsyncSession(fail_add=True)
    with pytest.raises(RuntimeError):
        await write_audit_event(
            db,
            tenant_id=1,
            module="people",
            entity_type="person",
            entity_id="1",
            action="updated",
            source="api",
            changed_fields={"email": {"before": "a", "after": "b"}},
            best_effort=False,
        )

