"""Issue 26 — Load PATCH money + load_updated audit atomicity."""
from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from decimal import Decimal
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db_url import to_async_pg_url
from app.models.tenant import AuditEvent
from app.schemas.load import LoadCreate, LoadUpdate, LoadStopCreate
from app.services import audit_events as audit_events_service
from app.services import loads as loads_service


def _tenant_async_engine():
    url = os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not url:
        raise RuntimeError("ALEMBIC_TENANT_DATABASE_URL is required for this runtime test")
    return create_async_engine(to_async_pg_url(url), pool_pre_ping=True)


@contextmanager
def _flush_fail_on_loads_load_updated_audit():
    """Fail inside write_audit_event flush for required money load_updated rows only."""

    real_flush = AsyncSession.flush

    async def flush_wrapper(self, *args, **kwargs):
        for obj in list(self.new):
            if (
                isinstance(obj, AuditEvent)
                and obj.module == "loads"
                and obj.action == "load_updated"
            ):
                raise RuntimeError("issue26 injected required audit flush failure")
        return await real_flush(self, *args, **kwargs)

    with patch.object(AsyncSession, "flush", flush_wrapper):
        yield


@contextmanager
def _flush_fail_on_any_audit_event():
    real_flush = AsyncSession.flush

    async def flush_wrapper(self, *args, **kwargs):
        for obj in list(self.new):
            if isinstance(obj, AuditEvent):
                raise RuntimeError("issue26 injected best-effort audit flush failure")
        return await real_flush(self, *args, **kwargs)

    with patch.object(AsyncSession, "flush", flush_wrapper):
        yield


class TestLoadMoneyAuditAtomicityIssue26(unittest.TestCase):
    def test_rate_patch_persists_decimal_and_audit_decimal_strings(self):
        async def run():
            engine = _tenant_async_engine()
            Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            tenant_id = 53
            suffix = uuid.uuid4().hex[:8]
            load_number = f"I26OK-{suffix}"

            async with Session() as db:
                created = await loads_service.create_load(
                    db,
                    tenant_id,
                    LoadCreate(
                        load_number=load_number,
                        status="draft",
                        rate=1000.00,
                        customer_rate=1100.00,
                        broker_name_snapshot="Issue26",
                        broker_load_reference=f"REF-{suffix}",
                        stops=[
                            LoadStopCreate(
                                sequence=0,
                                stop_type="pickup",
                                city="Toronto",
                                state="ON",
                                country="CA",
                            )
                        ],
                    ),
                )
                load_id = int(created.id)
                cv = int(created.concurrency_version)

                updated = await loads_service.update_load(
                    db,
                    tenant_id,
                    load_id,
                    LoadUpdate(rate=1500.50, expected_concurrency_version=cv),
                    actor_user_id=1,
                    request_id=f"i26-ok-{suffix}",
                    source="api",
                )
                assert updated.rate == Decimal("1500.50")
                assert int(updated.concurrency_version) == cv + 1

            async with Session() as db:
                row = (
                    await db.execute(
                        text(
                            "select rate, concurrency_version from loads where tenant_id=:t and id=:id"
                        ),
                        {"t": tenant_id, "id": load_id},
                    )
                ).one()
                assert row[0] == Decimal("1500.50")
                assert int(row[1]) == cv + 1

                audit = (
                    await db.execute(
                        text(
                            """
                            select changed_fields
                            from audit_events
                            where tenant_id=:t and entity_type='load' and entity_id=:eid
                              and action='load_updated'
                            order by id desc
                            limit 1
                            """
                        ),
                        {"t": tenant_id, "eid": str(load_id)},
                    )
                ).one()
                cf = audit[0]
                assert cf["rate"]["before"] == "1000.00"
                assert cf["rate"]["after"] == "1500.50"
                assert isinstance(cf["rate"]["before"], str)
                assert isinstance(cf["rate"]["after"], str)

                await _cleanup_load(db, tenant_id, load_id)

            await engine.dispose()

        asyncio.run(run())

    def test_audit_failure_rolls_back_rate_and_concurrency_version(self):
        async def run():
            engine = _tenant_async_engine()
            Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            tenant_id = 53
            suffix = uuid.uuid4().hex[:8]
            load_number = f"I26RB-{suffix}"

            async with Session() as db:
                created = await loads_service.create_load(
                    db,
                    tenant_id,
                    LoadCreate(
                        load_number=load_number,
                        status="draft",
                        rate=800.00,
                        broker_name_snapshot="Issue26",
                        broker_load_reference=f"REF-{suffix}",
                        stops=[],
                    ),
                )
                load_id = int(created.id)
                before_rate = created.rate
                before_cv = int(created.concurrency_version)

                real_audit = loads_service._write_load_audit

                async def _audit_bomb(*args, **kwargs):
                    if kwargs.get("action") == "load_updated":
                        raise RuntimeError("forced audit failure")
                    return await real_audit(*args, **kwargs)

                with patch.object(loads_service, "_write_load_audit", _audit_bomb):
                    with self.assertRaises(RuntimeError):
                        await loads_service.update_load(
                            db,
                            tenant_id,
                            load_id,
                            LoadUpdate(rate=999.99, expected_concurrency_version=before_cv),
                            request_id=f"i26-fail-{suffix}",
                            source="api",
                        )

            async with Session() as db:
                row = (
                    await db.execute(
                        text(
                            "select rate, concurrency_version from loads where tenant_id=:t and id=:id"
                        ),
                        {"t": tenant_id, "id": load_id},
                    )
                ).one()
                assert row[0] == before_rate
                assert int(row[1]) == before_cv

                count = (
                    await db.execute(
                        text(
                            """
                            select count(*) from audit_events
                            where tenant_id=:t and entity_type='load' and entity_id=:eid
                              and action='load_updated'
                            """
                        ),
                        {"t": tenant_id, "eid": str(load_id)},
                    )
                ).scalar_one()
                assert count == 0

                await _cleanup_load(db, tenant_id, load_id)

            await engine.dispose()

        asyncio.run(run())

    def test_required_audit_flush_failure_rolls_back_through_write_audit_event(self):
        """Money PATCH fails in real write_audit_event flush (not _write_load_audit stub)."""

        async def run():
            engine = _tenant_async_engine()
            Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            tenant_id = 53
            suffix = uuid.uuid4().hex[:8]
            load_number = f"I26FL-{suffix}"

            async with Session() as db:
                created = await loads_service.create_load(
                    db,
                    tenant_id,
                    LoadCreate(
                        load_number=load_number,
                        status="draft",
                        rate=800.00,
                        broker_name_snapshot="Issue26",
                        broker_load_reference=f"REF-{suffix}",
                        stops=[],
                    ),
                )
                load_id = int(created.id)
                before_rate = created.rate
                before_cv = int(created.concurrency_version)

                with _flush_fail_on_loads_load_updated_audit():
                    with self.assertRaises(RuntimeError) as ctx:
                        await loads_service.update_load(
                            db,
                            tenant_id,
                            load_id,
                            LoadUpdate(rate=999.99, expected_concurrency_version=before_cv),
                            request_id=f"i26-flush-{suffix}",
                            source="api",
                        )
                self.assertIn("issue26 injected required audit flush failure", str(ctx.exception))

                row = (
                    await db.execute(
                        text(
                            "select rate, concurrency_version from loads where tenant_id=:t and id=:id"
                        ),
                        {"t": tenant_id, "id": load_id},
                    )
                ).one()
                assert row[0] == before_rate
                assert int(row[1]) == before_cv

                audit_count = (
                    await db.execute(
                        text(
                            """
                            select count(*) from audit_events
                            where tenant_id=:t and entity_type='load' and entity_id=:eid
                              and action='load_updated'
                            """
                        ),
                        {"t": tenant_id, "eid": str(load_id)},
                    )
                ).scalar_one()
                assert audit_count == 0

                # Session remains usable after write_audit_event rollback (best_effort=False).
                ping = (await db.execute(text("select 1"))).scalar_one()
                assert ping == 1

                await _cleanup_load(db, tenant_id, load_id)

            await engine.dispose()

        asyncio.run(run())

    def test_write_audit_event_rollback_only_when_best_effort_false(self):
        async def run():
            engine = _tenant_async_engine()
            Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            tenant_id = 53
            rollback_calls: list[int] = []
            real_rollback = AsyncSession.rollback

            async def counting_rollback(self):
                rollback_calls.append(1)
                return await real_rollback(self)

            async with Session() as db:
                with patch.object(AsyncSession, "rollback", counting_rollback):
                    with _flush_fail_on_any_audit_event():
                        row = await audit_events_service.write_audit_event(
                            db,
                            tenant_id=tenant_id,
                            module="loads",
                            entity_type="load",
                            entity_id="0",
                            action="load_updated",
                            source="api",
                            changed_fields={"rate": {"before": "1.00", "after": "2.00"}},
                            best_effort=True,
                        )
                        assert row is None
                        assert rollback_calls == []
                        assert (await db.execute(text("select 1"))).scalar_one() == 1

                    rollback_calls.clear()
                    with _flush_fail_on_any_audit_event():
                        with self.assertRaises(RuntimeError):
                            await audit_events_service.write_audit_event(
                                db,
                                tenant_id=tenant_id,
                                module="loads",
                                entity_type="load",
                                entity_id="0",
                                action="load_updated",
                                source="api",
                                changed_fields={"rate": {"before": "1.00", "after": "2.00"}},
                                best_effort=False,
                            )
                        assert rollback_calls == [1]
                        assert (await db.execute(text("select 1"))).scalar_one() == 1

            await engine.dispose()

        asyncio.run(run())

    def test_customer_rate_patch_atomic(self):
        async def run():
            engine = _tenant_async_engine()
            Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            tenant_id = 53
            suffix = uuid.uuid4().hex[:8]
            load_number = f"I26CR-{suffix}"

            async with Session() as db:
                created = await loads_service.create_load(
                    db,
                    tenant_id,
                    LoadCreate(
                        load_number=load_number,
                        status="draft",
                        customer_rate=100.00,
                        broker_name_snapshot="Issue26",
                        broker_load_reference=f"REF-{suffix}",
                        stops=[],
                    ),
                )
                load_id = int(created.id)
                cv = int(created.concurrency_version)

                updated = await loads_service.update_load(
                    db,
                    tenant_id,
                    load_id,
                    LoadUpdate(customer_rate=333.33, expected_concurrency_version=cv),
                    source="api",
                )
                assert updated.customer_rate == Decimal("333.33")

            async with Session() as db:
                audit = (
                    await db.execute(
                        text(
                            """
                            select changed_fields
                            from audit_events
                            where tenant_id=:t and entity_type='load' and entity_id=:eid
                              and action='load_updated'
                            order by id desc
                            limit 1
                            """
                        ),
                        {"t": tenant_id, "eid": str(load_id)},
                    )
                ).one()
                assert audit[0]["customer_rate"]["after"] == "333.33"

                await _cleanup_load(db, tenant_id, load_id)

            await engine.dispose()

        asyncio.run(run())


class TestLoadMoneyAuditReviewGate(unittest.TestCase):
    """Independent review gate — audit accuracy, txn, concurrency, decimals."""

    def _session(self):
        engine = _tenant_async_engine()
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        return engine, Session

    def test_audit_accuracy_matrix(self):
        async def run():
            engine, Session = self._session()
            tenant_id = 53
            suffix = uuid.uuid4().hex[:8]

            async def audit_cf(db, load_id: int):
                row = (
                    await db.execute(
                        text(
                            """
                            select changed_fields from audit_events
                            where tenant_id=:t and entity_type='load' and entity_id=:e
                              and action='load_updated'
                            order by id desc limit 1
                            """
                        ),
                        {"t": tenant_id, "e": str(load_id)},
                    )
                ).one_or_none()
                return row[0] if row else None

            async with Session() as db:
                base = await loads_service.create_load(
                    db,
                    tenant_id,
                    LoadCreate(
                        load_number=f"RG-{suffix}",
                        status="draft",
                        rate=1000.00,
                        customer_rate=2000.00,
                        broker_name_snapshot="BeforeName",
                        broker_load_reference=f"REF-{suffix}",
                        stops=[],
                    ),
                )
                lid = int(base.id)
                cv = int(base.concurrency_version)

                # rate only
                await loads_service.update_load(
                    db,
                    tenant_id,
                    lid,
                    LoadUpdate(rate=2800.10, expected_concurrency_version=cv),
                    source="api",
                )
                cf = await audit_cf(db, lid)
                assert cf == {"rate": {"before": "1000.00", "after": "2800.10"}}
                cv += 1

                # customer_rate only
                await loads_service.update_load(
                    db,
                    tenant_id,
                    lid,
                    LoadUpdate(customer_rate=0.01, expected_concurrency_version=cv),
                    source="api",
                )
                cf = await audit_cf(db, lid)
                assert cf == {"customer_rate": {"before": "2000.00", "after": "0.01"}}
                cv += 1

                # both money fields
                await loads_service.update_load(
                    db,
                    tenant_id,
                    lid,
                    LoadUpdate(rate=123456789.99, customer_rate=50.25, expected_concurrency_version=cv),
                    source="api",
                )
                cf = await audit_cf(db, lid)
                assert cf["rate"]["before"] == "2800.10"
                assert cf["rate"]["after"] == "123456789.99"
                assert cf["customer_rate"]["before"] == "0.01"
                assert cf["customer_rate"]["after"] == "50.25"
                cv += 1

                # unrelated commercial field + rate
                await loads_service.update_load(
                    db,
                    tenant_id,
                    lid,
                    LoadUpdate(
                        rate=123456789.99,
                        broker_name_snapshot="AfterName",
                        expected_concurrency_version=cv,
                    ),
                    source="api",
                )
                cf = await audit_cf(db, lid)
                assert "rate" not in cf
                assert cf["broker_name_snapshot"] == {
                    "before": "BeforeName",
                    "after": "AfterName",
                }
                cv += 1

                # unchanged rate (sent explicitly) — no money residual
                row = (
                    await db.execute(
                        text("select rate, concurrency_version from loads where id=:i"),
                        {"i": lid},
                    )
                ).one()
                same_rate = float(row[0])
                cv = int(row[1])
                before_count = (
                    await db.execute(
                        text(
                            "select count(*) from audit_events where entity_id=:e and action='load_updated'"
                        ),
                        {"e": str(lid)},
                    )
                ).scalar_one()
                await loads_service.update_load(
                    db,
                    tenant_id,
                    lid,
                    LoadUpdate(rate=same_rate, expected_concurrency_version=cv),
                    source="api",
                )
                after_count = (
                    await db.execute(
                        text(
                            "select count(*) from audit_events where entity_id=:e and action='load_updated'"
                        ),
                        {"e": str(lid)},
                    )
                ).scalar_one()
                assert after_count == before_count

                # nullable customer_rate clear
                await loads_service.update_load(
                    db,
                    tenant_id,
                    lid,
                    LoadUpdate(
                        customer_rate=None,
                        expected_concurrency_version=int(
                            (
                                await db.execute(
                                    text("select concurrency_version from loads where id=:i"),
                                    {"i": lid},
                                )
                            ).scalar_one()
                        ),
                    ),
                    source="api",
                )
                cf = await audit_cf(db, lid)
                assert cf["customer_rate"]["before"] == "50.25"
                assert cf["customer_rate"]["after"] is None

                await _cleanup_load(db, tenant_id, lid)

            await engine.dispose()

        asyncio.run(run())

    def test_stale_concurrency_no_money_or_audit_change(self):
        async def run():
            engine, Session = self._session()
            tenant_id = 53
            suffix = uuid.uuid4().hex[:8]

            async with Session() as db:
                created = await loads_service.create_load(
                    db,
                    tenant_id,
                    LoadCreate(
                        load_number=f"RG-CV-{suffix}",
                        status="draft",
                        rate=500.00,
                        broker_name_snapshot="x",
                        broker_load_reference=f"r-{suffix}",
                        stops=[],
                    ),
                )
                lid = int(created.id)
                stale_cv = int(created.concurrency_version) - 1
                with self.assertRaises(Exception):
                    await loads_service.update_load(
                        db,
                        tenant_id,
                        lid,
                        LoadUpdate(rate=999.99, expected_concurrency_version=stale_cv),
                        source="api",
                    )

            async with Session() as db:
                row = (
                    await db.execute(
                        text("select rate, concurrency_version from loads where id=:i"),
                        {"i": lid},
                    )
                ).one()
                assert row[0] == Decimal("500.00")
                assert int(row[1]) == 1
                n = (
                    await db.execute(
                        text(
                            "select count(*) from audit_events where entity_id=:e and action='load_updated'"
                        ),
                        {"e": str(lid)},
                    )
                ).scalar_one()
                assert n == 0
                await _cleanup_load(db, tenant_id, lid)

            await engine.dispose()

        asyncio.run(run())

    def test_single_commit_per_successful_patch(self):
        async def run():
            engine, Session = self._session()
            tenant_id = 53
            suffix = uuid.uuid4().hex[:8]
            commits = 0
            real_commit = AsyncSession.commit

            async def counting_commit(self):
                nonlocal commits
                commits += 1
                return await real_commit(self)

            AsyncSession.commit = counting_commit  # type: ignore[method-assign]
            try:
                async with Session() as db:
                    created = await loads_service.create_load(
                        db,
                        tenant_id,
                        LoadCreate(
                            load_number=f"RG-CM-{suffix}",
                            status="draft",
                            rate=10.00,
                            broker_name_snapshot="x",
                            broker_load_reference=f"r-{suffix}",
                            stops=[],
                        ),
                    )
                    commits = 0
                    await loads_service.update_load(
                        db,
                        tenant_id,
                        int(created.id),
                        LoadUpdate(rate=20.00, expected_concurrency_version=int(created.concurrency_version)),
                        source="api",
                    )
                    assert commits == 1
                    await _cleanup_load(db, tenant_id, int(created.id))
            finally:
                AsyncSession.commit = real_commit  # type: ignore[method-assign]
            await engine.dispose()

        asyncio.run(run())

    def test_other_load_unchanged_when_audit_fails(self):
        async def run():
            engine, Session = self._session()
            tenant_id = 53
            suffix = uuid.uuid4().hex[:8]
            real_audit = loads_service._write_load_audit

            async def _audit_bomb(*args, **kwargs):
                if kwargs.get("action") == "load_updated":
                    raise RuntimeError("forced audit failure")
                return await real_audit(*args, **kwargs)

            async with Session() as db:
                a = await loads_service.create_load(
                    db,
                    tenant_id,
                    LoadCreate(
                        load_number=f"RG-A-{suffix}",
                        status="draft",
                        rate=1.00,
                        broker_name_snapshot="x",
                        broker_load_reference=f"a-{suffix}",
                        stops=[],
                    ),
                )
                aid = int(a.id)
                a_cv = int(a.concurrency_version)
                await loads_service.create_load(
                    db,
                    tenant_id,
                    LoadCreate(
                        load_number=f"RG-B-{suffix}",
                        status="draft",
                        rate=2.00,
                        broker_name_snapshot="x",
                        broker_load_reference=f"b-{suffix}",
                        stops=[],
                    ),
                )
                bid = (
                    await db.execute(
                        text("select id from loads where tenant_id=:t and load_number=:n"),
                        {"t": tenant_id, "n": f"RG-B-{suffix}"},
                    )
                ).scalar_one()
                b_rate_before = Decimal("2.00")

                with patch.object(loads_service, "_write_load_audit", _audit_bomb):
                    with self.assertRaises(RuntimeError):
                        await loads_service.update_load(
                            db,
                            tenant_id,
                            aid,
                            LoadUpdate(rate=9.99, expected_concurrency_version=a_cv),
                            source="api",
                        )

            async with Session() as db:
                a_row = (
                    await db.execute(text("select rate from loads where id=:i"), {"i": aid})
                ).one()
                b_row = (
                    await db.execute(text("select rate from loads where id=:i"), {"i": bid})
                ).one()
                assert a_row[0] == Decimal("1.00")
                assert b_row[0] == b_rate_before
                await _cleanup_load(db, tenant_id, aid)
                await _cleanup_load(db, tenant_id, bid)

            await engine.dispose()

        asyncio.run(run())

    def test_allowed_status_patch_still_writes_status_audit_best_effort(self):
        """Issue 3 blocks PATCH draft→ready; ready→draft PATCH still emits status audit when permitted."""

        async def run():
            engine, Session = self._session()
            tenant_id = 53
            suffix = uuid.uuid4().hex[:8]

            async with Session() as db:
                created = await loads_service.create_load(
                    db,
                    tenant_id,
                    LoadCreate(
                        load_number=f"RG-ST-{suffix}",
                        status="draft",
                        broker_name_snapshot="x",
                        broker_load_reference=f"r-{suffix}",
                        stops=[
                            {"stop_type": "PICKUP", "sequence": 0, "city": "A", "state_or_province": "TX"},
                            {"stop_type": "DROP", "sequence": 1, "city": "B", "state_or_province": "TX"},
                        ],
                    ),
                )
                lid = int(created.id)
                ready = await loads_service.mark_load_ready(
                    db,
                    tenant_id,
                    lid,
                    expected_concurrency_version=int(created.concurrency_version),
                )
                await loads_service.update_load(
                    db,
                    tenant_id,
                    lid,
                    LoadUpdate(status="draft", expected_concurrency_version=int(ready.concurrency_version)),
                    source="api",
                )
                actions = (
                    await db.execute(
                        text(
                            "select action from audit_events where entity_id=:e order by id"
                        ),
                        {"e": str(lid)},
                    )
                ).all()
                acts = [r[0] for r in actions]
                assert "load_status_changed" in acts
                await _cleanup_load(db, tenant_id, lid)

            await engine.dispose()

        asyncio.run(run())


async def _cleanup_load(db: AsyncSession, tenant_id: int, load_id: int) -> None:
    await db.execute(
        text("delete from audit_events where tenant_id=:t and entity_type='load' and entity_id=:e"),
        {"t": tenant_id, "e": str(load_id)},
    )
    await db.execute(
        text("delete from load_stops where tenant_id=:t and load_id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text("delete from loads where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.commit()


if __name__ == "__main__":
    unittest.main()
