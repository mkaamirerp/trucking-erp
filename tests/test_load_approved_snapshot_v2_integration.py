"""S1 snapshot behavior on disposable PostgreSQL databases only.

Requires TRUCKERP_S1_DISPOSABLE_ADMIN_URL. Creates tenant_clone_* databases,
upgrades one to each S1 sibling, and drops them. Refuses tenant_demo.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock, patch

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@db.example.invalid:5432/test")

from app.core.db_url import to_async_pg_url, to_sync_pg_url
from app.models.dispatch_trip import TenantDispatchNumbering
from app.models.driver import Driver
from app.models.load_commercial_evidence import LoadCommercialEvidence
from app.schemas.load import LoadCreate, LoadStopCreate
from app.schemas.load_document_parse import LoadParseReferenceItem
from app.schemas.load_workspace_draft import LoadWorkspaceDraftCreate, LoadWorkspaceDraftPromote
from app.services.load_approved_commercial_snapshot import insert_creation_snapshot_uncommitted
from app.services.load_workspace_draft import create_workspace_draft
from app.services.load_workspace_draft_promotion import promote_workspace_draft
from app.services.loads import (
    _insert_commercial_load_uncommitted,
    _write_load_audit,
    create_load,
    get_load,
)
from app.services.trips import create_planned_trip

ROOT = Path(__file__).resolve().parents[1]
CLONE_NAME_RE = re.compile(r"^tenant_clone_[0-9]{8}t[0-9]{6}z_[a-z0-9]{6}$")
FORBIDDEN = frozenset({"tenant_demo", "trucking_erp", "postgres", "tenant_pytest"})
LINEAGE = {
    "fmp": "s1_load_approved_snapshot_fmp",
    "x5": "s1_load_approved_snapshot_x5",
}
SECRET = "NESTED-SECRET-RC"
PDF_SHA = "ab" * 32


def _database_name(url: str) -> str:
    return (urlparse(url).path or "").lstrip("/").split("?")[0]


def _swap(url: str, database: str) -> str:
    if database in FORBIDDEN or not CLONE_NAME_RE.fullmatch(database):
        raise RuntimeError(f"refusing database name {database}")
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{database}"))


def _clone_name(suffix: str) -> str:
    moment = datetime.now(timezone.utc)
    name = f"tenant_clone_{moment.strftime('%Y%m%d')}t{moment.strftime('%H%M%S')}z_{suffix}"
    if not CLONE_NAME_RE.fullmatch(name):
        raise RuntimeError(f"refusing database name {name}")
    return name


async def _exec_admin(admin_async: str, sql: str) -> None:
    engine = create_async_engine(admin_async, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(sql))
    await engine.dispose()


def _upgrade(async_url: str, revision: str) -> None:
    if _database_name(async_url) in FORBIDDEN:
        raise RuntimeError("refusing to migrate a shared database")
    env = os.environ.copy()
    env["ALEMBIC_TENANT_DATABASE_URL"] = async_url
    env["DATABASE_URL"] = os.environ.get("DATABASE_URL", "postgresql://test:test@db.example.invalid:5432/test")
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic_tenant.ini", "upgrade", revision],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "alembic upgrade failed")


@pytest.fixture(scope="session")
def s1_databases():
    admin = (os.environ.get("TRUCKERP_S1_DISPOSABLE_ADMIN_URL") or "").strip()
    if not admin:
        pytest.skip("TRUCKERP_S1_DISPOSABLE_ADMIN_URL is required")
    if _database_name(admin) == "tenant_demo":
        pytest.fail("disposable admin URL must not be tenant_demo")
    admin_async = to_async_pg_url(admin)
    created: list[str] = []
    urls: dict[str, str] = {}
    try:
        for key, suffix in (("fmp", "s1fmp1"), ("x5", "s1x5aa")):
            name = _clone_name(suffix)
            asyncio.run(_exec_admin(admin_async, f'CREATE DATABASE "{name}"'))
            created.append(name)
            async_url = to_async_pg_url(_swap(to_sync_pg_url(admin), name))
            _upgrade(async_url, LINEAGE[key])
            urls[key] = async_url
        yield urls
    finally:
        for name in created:
            asyncio.run(_exec_admin(admin_async, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture(params=["fmp", "x5"])
def lineage_db(request, s1_databases):
    key = request.param
    url = s1_databases[key]
    if _database_name(url) in FORBIDDEN or not CLONE_NAME_RE.fullmatch(_database_name(url)):
        pytest.fail(f"refusing database {_database_name(url)}")
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield key, LINEAGE[key], factory
    asyncio.run(engine.dispose())


@pytest.fixture(autouse=True)
def _utc_load_numbers(monkeypatch):
    async def _tz(_tenant_id: int) -> ZoneInfo:
        return ZoneInfo("UTC")

    monkeypatch.setattr("app.services.load_numbering.company_timezone_for_tenant", _tz)


def _stops():
    return [
        LoadStopCreate(stop_type="pickup", sequence=0, city="Chicago", state_or_province="IL"),
        LoadStopCreate(stop_type="delivery", sequence=1, city="Roldsville", state_or_province="NC"),
    ]


def _load_create() -> LoadCreate:
    return LoadCreate(
        broker_load_reference="ARM-100",
        rate=Decimal("1800"),
        customer_rate=Decimal("1600"),
        internal_notes="private note",
        references=[LoadParseReferenceItem(kind="po", value="PO-9")],
        stops=_stops(),
    )


def _accepted_parse() -> dict:
    return {
        "document": {"filename": "rc.pdf"},
        "extracted": {
            "broker_load_reference": "ARM-100",
            "commodity": "steel",
            "references": [{"kind": "po", "value": "PO-9", "raw_text": SECRET, "llm_prompt": SECRET}],
            "stops": [{"city": "Chicago", "appointment_type": "FCFS", "handoff": SECRET, "diagnostic_blob": SECRET}],
        },
        "field_confidence": {"rate": {"score": "high", "raw_text": SECRET}},
    }


async def _require_current_load_model(factory) -> None:
    """x5 stops before the workspace columns the current Load model selects."""
    async with factory() as db:
        present = await db.scalar(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'loads'
                  AND column_name = 'promotion_origin_workspace_draft_id'
                """
            )
        )
    if int(present or 0) == 0:
        pytest.skip("this lineage does not have the workspace load columns the Load model reads")


async def _require_table(factory, name: str) -> None:
    async with factory() as db:
        present = await db.scalar(text("SELECT to_regclass(:qualified) IS NOT NULL"), {"qualified": f"public.{name}"})
    if not present:
        pytest.skip(f"{name} is not on this S1 lineage")


async def _count(factory, sql: str, params: dict) -> int:
    async with factory() as db:
        value = await db.scalar(text(sql), params)
    return int(value or 0)


async def _seed_trip_numbering(factory, tenant_id: int) -> None:
    async with factory() as db:
        db.add(
            TenantDispatchNumbering(
                tenant_id=tenant_id,
                trip_number_prefix="T1E",
                prefix_locked_at=datetime.now(timezone.utc),
                next_numeric=10001,
            )
        )
        await db.commit()


async def _seed_driver(factory, tenant_id: int) -> int:
    async with factory() as db:
        driver = Driver(tenant_id=tenant_id, first_name="Snapshot", last_name="Driver", is_active=True)
        db.add(driver)
        await db.commit()
        await db.refresh(driver)
        return int(driver.id)


@pytest.mark.asyncio
async def test_each_lineage_has_snapshot_constraints(lineage_db):
    _key, revision, factory = lineage_db
    async with factory() as db:
        versions = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
        assert versions == [revision]
        checks = (
            await db.execute(
                text(
                    """
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'load_approved_commercial_snapshots'::regclass
                    """
                )
            )
        ).scalars().all()
        triggers = (
            await db.execute(
                text(
                    """
                    SELECT tgname FROM pg_trigger
                    WHERE tgrelid = 'load_approved_commercial_snapshots'::regclass
                      AND NOT tgisinternal
                    """
                )
            )
        ).scalars().all()
        evidence_table = await db.scalar(text("SELECT to_regclass('public.load_commercial_evidence') IS NOT NULL"))
        evidence_unique = await db.scalar(
            text(
                """
                SELECT COUNT(*) FROM pg_constraint
                WHERE conname = 'uq_load_commercial_evidence_tenant_id'
                """
            )
        )
    assert "uq_load_approved_snapshots_tenant_load_milestone_rev" in checks
    assert "ck_load_approved_snapshots_milestone_creation" in checks
    assert "ck_load_approved_snapshots_claim_matches_source" in checks
    assert "ck_load_approved_snapshots_evidence_on_promotion" in checks
    assert "fk_load_approved_snapshots_load_tenant" in checks
    assert "load_approved_commercial_snapshots_append_only" in triggers
    if evidence_table:
        assert "fk_load_approved_snapshots_evidence_tenant" in checks
        assert int(evidence_unique or 0) == 1
    else:
        assert "fk_load_approved_snapshots_evidence_tenant" not in checks
        assert int(evidence_unique or 0) == 0


@pytest.mark.asyncio
async def test_direct_create_snapshot_matches_persisted_load(lineage_db):
    _key, _revision, factory = lineage_db
    await _require_current_load_model(factory)
    tenant_id = 8101
    async with factory() as db:
        load = await create_load(db, tenant_id, _load_create())
        load_id = int(load.id)
    async with factory() as db:
        stored = await get_load(db, tenant_id, load_id)
        payload = await db.scalar(
            text(
                """
                SELECT payload_json FROM load_approved_commercial_snapshots
                WHERE tenant_id = :t AND load_id = :lid AND milestone = 'creation'
                """
            ),
            {"t": tenant_id, "lid": load_id},
        )
    assert stored is not None
    fields = payload["approved_db_fields"]
    assert fields["load_number"] == stored.load_number
    assert fields["broker_load_reference"] == "ARM-100"
    assert fields["references"] == [{"kind": "po", "value": "PO-9"}]
    assert fields["rate"] == "1800.00"
    assert fields["customer_rate"] == "1600.00"
    assert [(stop["city"], stop["state_or_province"]) for stop in fields["stops"]] == [
        (stop.city, stop.state_or_province) for stop in stored.stops
    ]
    assert payload["original_rc_reference"]["association_status"] == "pdf_missing"
    assert payload["metadata"]["creation_source"] == "direct_create"
    assert "driver_id" not in fields


@pytest.mark.asyncio
async def test_promotion_snapshot_matches_load_and_drops_nested_secrets(lineage_db):
    _key, _revision, factory = lineage_db
    await _require_current_load_model(factory)
    await _require_table(factory, "load_workspace_drafts")
    await _require_table(factory, "load_commercial_evidence")
    tenant_id = 8102
    async with factory() as db:
        draft = await create_workspace_draft(
            db,
            tenant_id,
            LoadWorkspaceDraftCreate(
                source_channel="manual",
                draft_json={
                    "brokerLoadReference": "ARM-100",
                    "rate": "1800",
                    "customerRate": "1600",
                    "internalNotes": "private note",
                    "loadReferences": [{"kind": "po", "value": "PO-9"}],
                    "draftStops": [
                        {"stopType": "PICKUP", "city": "Chicago", "stateOrProvince": "IL"},
                        {"stopType": "DELIVERY", "city": "Roldsville", "stateOrProvince": "NC"},
                    ],
                },
            ),
            created_by_platform_user_id="platform-user-s1",
        )
        draft.pdf_upload_state = "ready"
        draft.pdf_storage_key = "s1/rc.pdf"
        draft.pdf_sha256 = PDF_SHA
        draft.pdf_filename = "rc.pdf"
        draft.accepted_parse_json = _accepted_parse()
        draft.accepted_parse_schema_version = "v1"
        draft.accepted_parse_pdf_sha256 = PDF_SHA
        await db.commit()
        draft_id = draft.id
    async with factory() as db:
        result = await promote_workspace_draft(
            db,
            tenant_id,
            draft_id,
            LoadWorkspaceDraftPromote(
                expected_concurrency_version=1,
                promotion_idempotency_key=f"s1-{uuid.uuid4().hex}",
            ),
            promoted_by_platform_user_id="platform-user-s1",
        )
        load_id = result.load_id
    async with factory() as db:
        stored = await get_load(db, tenant_id, load_id)
        payload = await db.scalar(
            text(
                """
                SELECT payload_json FROM load_approved_commercial_snapshots
                WHERE tenant_id = :t AND load_id = :lid
                """
            ),
            {"t": tenant_id, "lid": load_id},
        )
    assert stored is not None and stored.status == "ready"
    fields = payload["approved_db_fields"]
    assert fields["broker_load_reference"] == stored.broker_load_reference == "ARM-100"
    assert fields["references"] == [{"kind": "po", "value": "PO-9"}]
    assert [stop.city for stop in stored.stops] == ["Chicago", "Roldsville"]
    assert [stop["city"] for stop in fields["stops"]] == ["Chicago", "Roldsville"]
    original = payload["original_rc_reference"]
    assert original["association_status"] == "usable"
    assert SECRET not in str(original)
    assert original["document_references"]["value"] == [{"kind": "po", "value": "PO-9"}]
    assert original["document_stops"]["value"][0]["appointment_type"] == "FCFS"
    assert "handoff" not in original["document_stops"]["value"][0]


@pytest.mark.asyncio
async def test_promotion_replay_keeps_one_creation_snapshot(lineage_db):
    _key, _revision, factory = lineage_db
    await _require_current_load_model(factory)
    await _require_table(factory, "load_workspace_drafts")
    tenant_id = 8103
    key = f"replay-{uuid.uuid4().hex}"
    async with factory() as db:
        draft = await create_workspace_draft(
            db,
            tenant_id,
            LoadWorkspaceDraftCreate(
                source_channel="manual",
                draft_json={
                    "brokerLoadReference": f"REPLAY-{uuid.uuid4().hex[:8]}",
                    "draftStops": [
                        {"stopType": "PICKUP", "city": "Austin", "stateOrProvince": "TX"},
                        {"stopType": "DELIVERY", "city": "Dallas", "stateOrProvince": "TX"},
                    ],
                },
            ),
            created_by_platform_user_id="platform-user-s1",
        )
        draft_id = draft.id
    async with factory() as db:
        first = await promote_workspace_draft(
            db,
            tenant_id,
            draft_id,
            LoadWorkspaceDraftPromote(expected_concurrency_version=1, promotion_idempotency_key=key),
            promoted_by_platform_user_id="platform-user-s1",
        )
    async with factory() as db:
        second = await promote_workspace_draft(
            db,
            tenant_id,
            draft_id,
            LoadWorkspaceDraftPromote(expected_concurrency_version=2, promotion_idempotency_key=key),
            promoted_by_platform_user_id="platform-user-s1",
        )
    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert second.load_id == first.load_id
    assert await _count(
        factory,
        "SELECT COUNT(*) FROM load_approved_commercial_snapshots WHERE tenant_id = :t AND load_id = :lid",
        {"t": tenant_id, "lid": first.load_id},
    ) == 1


@pytest.mark.asyncio
async def test_snapshot_failure_rolls_back_load_evidence_audit_and_trip(lineage_db):
    _key, _revision, factory = lineage_db
    await _require_current_load_model(factory)
    await _require_table(factory, "load_workspace_drafts")
    await _require_table(factory, "load_commercial_evidence")
    tenant_id = 8104
    await _seed_trip_numbering(factory, tenant_id)
    driver_id = await _seed_driver(factory, tenant_id)
    async with factory() as db:
        draft = await create_workspace_draft(
            db,
            tenant_id,
            LoadWorkspaceDraftCreate(
                source_channel="manual",
                draft_json={
                    "brokerLoadReference": f"FAIL-{uuid.uuid4().hex[:8]}",
                    "driverId": driver_id,
                    "draftStops": [
                        {"stopType": "PICKUP", "city": "Austin", "stateOrProvince": "TX"},
                        {"stopType": "DELIVERY", "city": "Dallas", "stateOrProvince": "TX"},
                    ],
                },
            ),
            created_by_platform_user_id="platform-user-s1",
        )
        draft.pdf_upload_state = "ready"
        draft.pdf_storage_key = "s1/fail.pdf"
        draft.pdf_sha256 = PDF_SHA
        draft.accepted_parse_json = {"extracted": {"commodity": "steel"}}
        draft.accepted_parse_pdf_sha256 = PDF_SHA
        await db.commit()
        draft_id = draft.id
    with patch(
        "app.services.load_workspace_draft_promotion.insert_creation_snapshot_uncommitted",
        new=AsyncMock(side_effect=RuntimeError("snapshot failed")),
    ):
        async with factory() as db:
            with pytest.raises(RuntimeError, match="snapshot failed"):
                await promote_workspace_draft(
                    db,
                    tenant_id,
                    draft_id,
                    LoadWorkspaceDraftPromote(
                        expected_concurrency_version=1,
                        promotion_idempotency_key=f"fail-{uuid.uuid4().hex}",
                    ),
                    promoted_by_platform_user_id="platform-user-s1",
                )
            await db.rollback()
    assert await _count(factory, "SELECT COUNT(*) FROM loads WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM load_commercial_evidence WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM load_approved_commercial_snapshots WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM audit_events WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM trips WHERE tenant_id = :t", {"t": tenant_id}) == 0
    async with factory() as db:
        status_name = await db.scalar(
            text("SELECT status FROM load_workspace_drafts WHERE tenant_id = :t AND id = :id"),
            {"t": tenant_id, "id": draft_id},
        )
    assert status_name == "draft"


@pytest.mark.asyncio
async def test_snapshot_update_and_delete_are_rejected(lineage_db):
    _key, _revision, factory = lineage_db
    await _require_current_load_model(factory)
    tenant_id = 8105
    async with factory() as db:
        load = await create_load(db, tenant_id, _load_create())
        load_id = int(load.id)
    async with factory() as db:
        with pytest.raises(DBAPIError, match="append_only:load_approved_commercial_snapshots"):
            await db.execute(
                text(
                    """
                    UPDATE load_approved_commercial_snapshots
                    SET schema_version = 'changed'
                    WHERE tenant_id = :t AND load_id = :lid
                    """
                ),
                {"t": tenant_id, "lid": load_id},
            )
        await db.rollback()
    async with factory() as db:
        with pytest.raises(DBAPIError, match="append_only:load_approved_commercial_snapshots"):
            await db.execute(
                text(
                    """
                    DELETE FROM load_approved_commercial_snapshots
                    WHERE tenant_id = :t AND load_id = :lid
                    """
                ),
                {"t": tenant_id, "lid": load_id},
            )
        await db.rollback()
    assert await _count(
        factory,
        "SELECT COUNT(*) FROM load_approved_commercial_snapshots WHERE tenant_id = :t AND load_id = :lid",
        {"t": tenant_id, "lid": load_id},
    ) == 1


@pytest.mark.asyncio
async def test_snapshot_mutation_failure_rolls_back_staged_load_evidence_audit_and_trip(lineage_db):
    _key, _revision, factory = lineage_db
    await _require_current_load_model(factory)
    await _require_table(factory, "load_workspace_drafts")
    await _require_table(factory, "load_commercial_evidence")
    tenant_id = 8106
    async with factory() as db:
        try:
            draft = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json={"brokerNameSnapshot": "Rollback"},
                ),
                created_by_platform_user_id="platform-user-s1",
            )
            draft_id = draft.id
            db.add(
                TenantDispatchNumbering(
                    tenant_id=tenant_id,
                    trip_number_prefix="T1E",
                    prefix_locked_at=datetime.now(timezone.utc),
                    next_numeric=10001,
                )
            )
            driver = Driver(tenant_id=tenant_id, first_name="Rollback", last_name="Driver", is_active=True)
            db.add(driver)
            await db.flush()
            load, _diff = await _insert_commercial_load_uncommitted(
                db,
                tenant_id,
                _load_create(),
                promotion_origin_workspace_draft_id=draft_id,
                insert_as_ready=True,
            )
            evidence = LoadCommercialEvidence(
                tenant_id=tenant_id,
                load_id=int(load.id),
                workspace_draft_id=draft_id,
                file_sha256=PDF_SHA,
                storage_key="s1/rollback.pdf",
                accepted_parse_json={"extracted": {"commodity": "steel"}},
                promoted_at=datetime.now(timezone.utc),
            )
            db.add(evidence)
            await db.flush()
            hydrated = await get_load(db, tenant_id, int(load.id))
            await insert_creation_snapshot_uncommitted(
                db,
                hydrated,
                creation_source="workspace_promotion",
                dispatcher_review_claim="workspace_promotion_reviewed",
                created_by_platform_user_id="platform-user-s1",
                evidence=evidence,
                workspace_draft_id=draft_id,
                accepted_parse_pdf_sha256=PDF_SHA,
            )
            await _write_load_audit(
                db,
                tenant_id=tenant_id,
                load=hydrated,
                action="load_created",
                actor_user_id=None,
                request_id=None,
                correlation_id=None,
                source="ui",
                changed_fields={"status": {"before": None, "after": "ready"}},
                context_json={"origin": "s1-rollback-probe"},
                best_effort=False,
            )
            await create_planned_trip(
                db,
                tenant_id,
                driver_id=int(driver.id),
                load_ids=[int(load.id)],
            )
            with pytest.raises(DBAPIError, match="append_only:load_approved_commercial_snapshots"):
                await db.execute(
                    text(
                        """
                        UPDATE load_approved_commercial_snapshots
                        SET schema_version = 'changed'
                        WHERE tenant_id = :t
                        """
                    ),
                    {"t": tenant_id},
                )
            await db.rollback()
        except Exception:
            await db.rollback()
            raise
    assert await _count(factory, "SELECT COUNT(*) FROM loads WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM load_commercial_evidence WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM load_approved_commercial_snapshots WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM audit_events WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM trips WHERE tenant_id = :t", {"t": tenant_id}) == 0


@pytest.mark.asyncio
async def test_direct_create_snapshot_failure_rolls_back_load_and_audit(lineage_db):
    _key, _revision, factory = lineage_db
    await _require_current_load_model(factory)
    tenant_id = 8109
    with patch(
        "app.services.loads.insert_creation_snapshot_uncommitted",
        new=AsyncMock(side_effect=RuntimeError("snapshot failed")),
    ):
        async with factory() as db:
            with pytest.raises(RuntimeError, match="snapshot failed"):
                await create_load(db, tenant_id, _load_create())
            await db.rollback()
    assert await _count(factory, "SELECT COUNT(*) FROM loads WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM load_approved_commercial_snapshots WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM audit_events WHERE tenant_id = :t", {"t": tenant_id}) == 0


@pytest.mark.asyncio
async def test_snapshot_update_failure_rolls_back_load_audit_and_trip(lineage_db):
    _key, _revision, factory = lineage_db
    await _require_current_load_model(factory)
    tenant_id = 8110
    async with factory() as db:
        try:
            db.add(
                TenantDispatchNumbering(
                    tenant_id=tenant_id,
                    trip_number_prefix="T1E",
                    prefix_locked_at=datetime.now(timezone.utc),
                    next_numeric=10001,
                )
            )
            driver = Driver(tenant_id=tenant_id, first_name="Rollback", last_name="Driver", is_active=True)
            db.add(driver)
            await db.flush()
            load, _diff = await _insert_commercial_load_uncommitted(
                db, tenant_id, _load_create(), insert_as_ready=True
            )
            hydrated = await get_load(db, tenant_id, int(load.id))
            await insert_creation_snapshot_uncommitted(
                db,
                hydrated,
                creation_source="direct_create",
                dispatcher_review_claim="none",
                created_by_platform_user_id=None,
                evidence=None,
                workspace_draft_id=None,
                accepted_parse_pdf_sha256=None,
            )
            await _write_load_audit(
                db,
                tenant_id=tenant_id,
                load=hydrated,
                action="load_created",
                actor_user_id=None,
                request_id=None,
                correlation_id=None,
                source="ui",
                changed_fields={"status": {"before": None, "after": "draft"}},
                context_json={"origin": "s1-rollback-probe"},
                best_effort=False,
            )
            await create_planned_trip(db, tenant_id, driver_id=int(driver.id), load_ids=[int(load.id)])
            with pytest.raises(DBAPIError, match="append_only:load_approved_commercial_snapshots"):
                await db.execute(
                    text("UPDATE load_approved_commercial_snapshots SET schema_version = 'changed' WHERE tenant_id = :t"),
                    {"t": tenant_id},
                )
            await db.rollback()
        except Exception:
            await db.rollback()
            raise
    assert await _count(factory, "SELECT COUNT(*) FROM loads WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM load_approved_commercial_snapshots WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM audit_events WHERE tenant_id = :t", {"t": tenant_id}) == 0
    assert await _count(factory, "SELECT COUNT(*) FROM trips WHERE tenant_id = :t", {"t": tenant_id}) == 0


@pytest.mark.asyncio
async def test_snapshots_are_tenant_isolated(lineage_db):
    _key, _revision, factory = lineage_db
    await _require_current_load_model(factory)
    async with factory() as db:
        first = await create_load(db, 8107, _load_create())
        first_id = int(first.id)
    async with factory() as db:
        second = await create_load(
            db,
            8108,
            LoadCreate(
                broker_load_reference="OTHER-1",
                stops=[LoadStopCreate(stop_type="pickup", sequence=0, city="Dallas", state_or_province="TX")],
            ),
        )
        second_id = int(second.id)
    assert await _count(
        factory,
        """
        SELECT COUNT(*) FROM load_approved_commercial_snapshots
        WHERE tenant_id = 8108 AND load_id = :lid
        """,
        {"lid": first_id},
    ) == 0
    async with factory() as db:
        payload = await db.scalar(
            text(
                """
                SELECT payload_json FROM load_approved_commercial_snapshots
                WHERE tenant_id = 8107 AND load_id = :lid
                """
            ),
            {"lid": first_id},
        )
        other = await db.scalar(
            text(
                """
                SELECT payload_json FROM load_approved_commercial_snapshots
                WHERE tenant_id = 8108 AND load_id = :lid
                """
            ),
            {"lid": second_id},
        )
    assert payload["approved_db_fields"]["broker_load_reference"] == "ARM-100"
    assert other["approved_db_fields"]["broker_load_reference"] == "OTHER-1"
    async with factory() as db:
        with pytest.raises(DBAPIError):
            await db.execute(
                text(
                    """
                    INSERT INTO load_approved_commercial_snapshots (
                      tenant_id, load_id, milestone, revision, schema_version,
                      load_concurrency_version, creation_source, load_status_at_snapshot,
                      dispatcher_review_claim, snapshot_taken_at, payload_json
                    )
                    SELECT 8108, id, 'creation', 1, 'load_approved_snapshot_v2',
                           1, 'direct_create', 'draft', 'none', NOW(), '{}'::jsonb
                    FROM loads WHERE tenant_id = 8107 AND id = :lid
                    """
                ),
                {"lid": first_id},
            )
        await db.rollback()
