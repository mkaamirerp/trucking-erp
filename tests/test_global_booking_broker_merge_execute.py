"""Global booking broker merge execute (platform DB integration + unit checks)."""

from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.global_booking_broker import (
    GlobalBookingBroker,
    GlobalBookingBrokerAlias,
    GlobalBookingBrokerAuditEvent,
    GlobalBookingBrokerDomain,
    GlobalBookingBrokerKnownSender,
    GlobalBookingBrokerMergePreview,
)
from app.services import global_booking_broker_merge_execute as mex
from app.services.global_booking_broker_merge_preview import build_merge_preview

REQUIRES_DB = not os.environ.get("DATABASE_URL")


def test_regulatory_blocking_unit() -> None:
    s = GlobalBookingBroker(name="A", canonical_status="approved", mc_number="123456")
    z = GlobalBookingBroker(name="B", canonical_status="approved", mc_number="999999")
    assert mex._regulatory_blocking(s, z) is True


def test_regulatory_blocking_false_when_safe_default() -> None:
    s = GlobalBookingBroker(name="A", canonical_status="approved", mc_number="123456")
    z = GlobalBookingBroker(name="B", canonical_status="approved", mc_number=None)
    assert mex._regulatory_blocking(s, z) is False


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL not set")
async def test_merge_execute_success_rehomes_and_audits() -> None:
    suffix = uuid.uuid4().hex[:12]
    dom = f"{suffix}.gbb-merge-test.invalid"

    async with AsyncSessionLocal() as db:
        shared_legal = f"Co Legal {suffix}"
        shared_name = f"Co {suffix}"
        source = GlobalBookingBroker(
            name=shared_name,
            legal_name=shared_legal,
            display_name=None,
            canonical_status="approved",
            mc_number="100001",
            dot_number=None,
            cvor_number=None,
        )
        surv = GlobalBookingBroker(
            name=shared_name,
            legal_name=shared_legal,
            display_name=None,
            canonical_status="approved",
            mc_number=None,
            dot_number=None,
            cvor_number=None,
        )
        db.add(source)
        db.add(surv)
        await db.flush()

        db.add(GlobalBookingBrokerDomain(global_broker_id=source.id, domain=dom, is_active=True))
        db.add(
            GlobalBookingBrokerKnownSender(
                global_broker_id=source.id,
                email_normalized=f"src.{suffix}@gbb-merge-test.invalid",
                is_active=True,
            )
        )
        db.add(
            GlobalBookingBrokerAlias(
                global_broker_id=source.id,
                alias=f"src alias {suffix}".casefold(),
                is_active=True,
            )
        )

        built = build_merge_preview(source=source, survivor=surv, duplicate_candidate_id=None)
        assert built.persist_eligible is True
        mp_row = GlobalBookingBrokerMergePreview(
            source_global_broker_id=source.id,
            survivor_global_broker_id=surv.id,
            duplicate_candidate_id=None,
            preview_hash=built.preview_hash,
            preview_payload=json.dumps(built.preview_body, separators=(",", ":"), ensure_ascii=False),
        )
        db.add(mp_row)
        await db.flush()
        preview_id = mp_row.id
        ph = built.preview_hash
        src_id = source.id
        surv_id = surv.id

        await db.commit()

    async with AsyncSessionLocal() as db:
        out = await mex.execute_global_booking_broker_merge(
            db,
            preview_id=preview_id,
            preview_hash=ph,
            name_resolution=None,
            legal_name_resolution=None,
            display_name_resolution=None,
        )
        assert out.status == "completed"
        assert out.child_stats is not None
        assert out.child_stats["domains_rehomed"] == 1
        assert out.child_stats["aliases_rehomed"] == 1
        assert out.child_stats["senders_rehomed"] == 1

    async with AsyncSessionLocal() as db:
        dom_row = (
            await db.execute(select(GlobalBookingBrokerDomain).where(GlobalBookingBrokerDomain.domain == dom))
        ).scalar_one()
        assert dom_row.global_broker_id == surv_id
        assert dom_row.is_active is True

        src = await db.get(GlobalBookingBroker, src_id)
        assert src is not None
        assert src.merged_into_global_broker_id == surv_id
        assert src.merged_at is not None
        assert src.canonical_status == "rejected"

        evs = (
            (
                await db.execute(
                    select(GlobalBookingBrokerAuditEvent).where(
                        GlobalBookingBrokerAuditEvent.global_broker_id.in_((src_id, surv_id)),
                    )
                )
            )
            .scalars()
            .all()
        )
        actions = sorted({e.action for e in evs})
        assert mex.AUDIT_MERGE_SOURCE in actions
        assert mex.AUDIT_MERGE_SURVIVOR in actions
        for e in evs:
            if e.action == mex.AUDIT_MERGE_SURVIVOR:
                d = json.loads(e.detail or "{}")
                assert d.get("preview_id") == preview_id
                assert d.get("preview_hash") == ph
                assert d.get("duplicate_candidate_id") is None
                assert "child_stats" in d


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL not set")
async def test_merge_preview_hash_mismatch() -> None:
    suffix = uuid.uuid4().hex[:12]
    async with AsyncSessionLocal() as db:
        source = GlobalBookingBroker(name=f"S {suffix}", canonical_status="approved")
        surv = GlobalBookingBroker(name=f"Z {suffix}", canonical_status="approved")
        db.add(source)
        db.add(surv)
        await db.flush()
        built = build_merge_preview(source=source, survivor=surv, duplicate_candidate_id=None)
        mp_row = GlobalBookingBrokerMergePreview(
            source_global_broker_id=source.id,
            survivor_global_broker_id=surv.id,
            duplicate_candidate_id=None,
            preview_hash=built.preview_hash,
            preview_payload=json.dumps(built.preview_body, separators=(",", ":"), ensure_ascii=False),
        )
        db.add(mp_row)
        await db.flush()
        preview_id = mp_row.id
        await db.commit()

    async with AsyncSessionLocal() as db:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as ei:
            await mex.execute_global_booking_broker_merge(
                db,
                preview_id=preview_id,
                preview_hash="0" * 64,
                name_resolution=None,
                legal_name_resolution=None,
                display_name_resolution=None,
            )
        assert ei.value.status_code == 409
        assert ei.value.detail == "merge_preview_hash_mismatch"


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL not set")
async def test_merge_preview_stale_after_broker_change() -> None:
    suffix = uuid.uuid4().hex[:12]
    nm = f"Stable {suffix}"
    async with AsyncSessionLocal() as db:
        source = GlobalBookingBroker(name=nm, canonical_status="approved", mc_number="200001")
        surv = GlobalBookingBroker(name=nm, canonical_status="approved", mc_number=None)
        db.add(source)
        db.add(surv)
        await db.flush()
        built = build_merge_preview(source=source, survivor=surv, duplicate_candidate_id=None)
        mp_row = GlobalBookingBrokerMergePreview(
            source_global_broker_id=source.id,
            survivor_global_broker_id=surv.id,
            duplicate_candidate_id=None,
            preview_hash=built.preview_hash,
            preview_payload=json.dumps(built.preview_body, separators=(",", ":"), ensure_ascii=False),
        )
        db.add(mp_row)
        await db.flush()
        preview_id = mp_row.id
        ph_old = built.preview_hash
        await db.commit()

    async with AsyncSessionLocal() as db:
        mp = await db.get(GlobalBookingBrokerMergePreview, preview_id)
        z = await db.get(GlobalBookingBroker, mp.survivor_global_broker_id)
        z.name = f"{z.name}-stale-mutated"
        await db.commit()

    async with AsyncSessionLocal() as db:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as ei:
            await mex.execute_global_booking_broker_merge(
                db,
                preview_id=preview_id,
                preview_hash=ph_old,
                name_resolution=None,
                legal_name_resolution=None,
                display_name_resolution=None,
            )
        assert ei.value.status_code == 409
        assert ei.value.detail == "merge_preview_stale"


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL not set")
async def test_merge_idempotent_repeat_execute() -> None:
    suffix = uuid.uuid4().hex[:12]
    shared_legal = f"Legal {suffix}"
    async with AsyncSessionLocal() as db:
        source = GlobalBookingBroker(name=f"Same {suffix}", legal_name=shared_legal, canonical_status="approved")
        surv = GlobalBookingBroker(name=f"Same {suffix}", legal_name=shared_legal, canonical_status="approved")
        db.add(source)
        db.add(surv)
        await db.flush()
        built = build_merge_preview(source=source, survivor=surv, duplicate_candidate_id=None)
        mp_row = GlobalBookingBrokerMergePreview(
            source_global_broker_id=source.id,
            survivor_global_broker_id=surv.id,
            duplicate_candidate_id=None,
            preview_hash=built.preview_hash,
            preview_payload=json.dumps(built.preview_body, separators=(",", ":"), ensure_ascii=False),
        )
        db.add(mp_row)
        await db.flush()
        preview_id = mp_row.id
        ph = built.preview_hash
        await db.commit()

    async with AsyncSessionLocal() as db:
        out1 = await mex.execute_global_booking_broker_merge(
            db,
            preview_id=preview_id,
            preview_hash=ph,
            name_resolution=None,
            legal_name_resolution=None,
            display_name_resolution=None,
        )
        assert out1.status == "completed"

    async with AsyncSessionLocal() as db:
        out2 = await mex.execute_global_booking_broker_merge(
            db,
            preview_id=preview_id,
            preview_hash=ph,
            name_resolution=None,
            legal_name_resolution=None,
            display_name_resolution=None,
        )
        assert out2.status == "already_completed"

    async with AsyncSessionLocal() as db:
        out3 = await mex.execute_global_booking_broker_merge(
            db,
            preview_id=preview_id,
            preview_hash=ph,
            name_resolution=None,
            legal_name_resolution=None,
            display_name_resolution=None,
        )
        assert out3.status == "already_completed"



@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL not set")
async def test_rehome_deactivates_when_survivor_already_has_active_key(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _peer_has_active(_db, _sid: int, _key: str) -> bool:
        return True

    monkeypatch.setattr(mex, "_survivor_has_active_domain", _peer_has_active)
    monkeypatch.setattr(mex, "_survivor_has_active_sender", _peer_has_active)
    monkeypatch.setattr(mex, "_survivor_has_active_alias", _peer_has_active)

    suffix = uuid.uuid4().hex[:12]
    dom = f"{suffix}.gbb-dup-dem.invalid"

    async with AsyncSessionLocal() as db:
        source = GlobalBookingBroker(name=f"Sd {suffix}", canonical_status="approved")
        surv = GlobalBookingBroker(name=f"Zd {suffix}", canonical_status="approved")
        db.add(source)
        db.add(surv)
        await db.flush()
        db.add(GlobalBookingBrokerDomain(global_broker_id=source.id, domain=dom, is_active=True))
        db.add(
            GlobalBookingBrokerKnownSender(
                global_broker_id=source.id,
                email_normalized=f"d.{suffix}@d.invalid",
                is_active=True,
            )
        )
        db.add(GlobalBookingBrokerAlias(global_broker_id=source.id, alias=f"a{suffix}".casefold(), is_active=True))
        await db.flush()
        src_id, surv_id = source.id, surv.id
        await db.commit()

    async with AsyncSessionLocal() as db:
        stats = await mex._rehome_active_children(db, source_id=src_id, survivor_id=surv_id)
        assert stats["domains_deactivated"] == 1
        assert stats["domains_rehomed"] == 0
        assert stats["senders_deactivated"] == 1
        assert stats["aliases_deactivated"] == 1

        row = (
            await db.execute(select(GlobalBookingBrokerDomain).where(GlobalBookingBrokerDomain.domain == dom))
        ).scalar_one()


def test_fresh_preview_not_persist_eligible_when_source_already_loser() -> None:
    s = GlobalBookingBroker(name="L", canonical_status="approved", merged_into_global_broker_id=99)
    z = GlobalBookingBroker(name="N", canonical_status="approved")
    built = build_merge_preview(source=s, survivor=z, duplicate_candidate_id=None)
    assert built.persist_eligible is False


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL not set")
async def test_operator_resolution_required_for_name_conflict() -> None:
    from fastapi import HTTPException

    suffix = uuid.uuid4().hex[:12]
    async with AsyncSessionLocal() as db:
        source = GlobalBookingBroker(name=f"Name A {suffix}", canonical_status="approved", mc_number="300001")
        surv = GlobalBookingBroker(name=f"Name B {suffix}", canonical_status="approved", mc_number="300001")
        db.add(source)
        db.add(surv)
        await db.flush()
        built = build_merge_preview(source=source, survivor=surv, duplicate_candidate_id=None)
        assert "name" in built.preview_body["summary"]["operator_choice_required_fields"]
        mp_row = GlobalBookingBrokerMergePreview(
            source_global_broker_id=source.id,
            survivor_global_broker_id=surv.id,
            duplicate_candidate_id=None,
            preview_hash=built.preview_hash,
            preview_payload=json.dumps(built.preview_body, separators=(",", ":"), ensure_ascii=False),
        )
        db.add(mp_row)
        await db.flush()
        preview_id = mp_row.id
        ph = built.preview_hash
        await db.commit()

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as ei:
            await mex.execute_global_booking_broker_merge(
                db,
                preview_id=preview_id,
                preview_hash=ph,
                name_resolution=None,
                legal_name_resolution=None,
                display_name_resolution=None,
            )
        assert ei.value.status_code == 422
        assert ei.value.detail == "merge_resolution_required:name"

    async with AsyncSessionLocal() as db:
        out = await mex.execute_global_booking_broker_merge(
            db,
            preview_id=preview_id,
            preview_hash=ph,
            name_resolution="source",
            legal_name_resolution=None,
            display_name_resolution=None,
        )
        assert out.status == "completed"
        z = await db.get(GlobalBookingBroker, out.survivor_global_broker_id)
        assert z is not None
        assert suffix in z.name and "Name A" in z.name
