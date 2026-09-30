"""BVD import staging — upload/review/discard/process (locked staging decisions)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.models.fuel import (
    FuelBvd,
    FuelBvdFieldCorrection,
    FuelBvdImportStage,
    FuelBvdStageFieldCorrection,
    FuelBvdStageRow,
)
from app.services.fuel_bvd_import import import_bvd_digital_pdf
from app.services.fuel_bvd_review import (
    BVD_REVIEW_SOURCE_COMPLETE,
    list_bvd_import_rows_for_review,
    process_bvd_import_review,
    save_bvd_import_review,
)
from app.services.fuel_bvd_stage import (
    STAGE_STATUS_ACTIVE,
    create_bvd_import_stage_from_pdf,
    discard_bvd_import_stage,
    get_active_stage,
    process_stage_to_permanent,
)
from app.services.fuel_source_duplicate_gate import FUEL_DUPLICATE_EXACT, sha256_hex
from tests.support.integration_isolation import require_integration_tenant_database_url

REPO = Path(__file__).resolve().parents[1]
BVD_PDF = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_972201.pdf"
INTEGRATION_TENANT_ID = 53


def _tenant_url() -> str | None:
    try:
        return to_async_pg_url(require_integration_tenant_database_url(context="fuel_bvd_staging"))
    except Exception:
        return None


REQUIRES_TENANT_DB = _tenant_url() is None


class _FakeScalars:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


async def _ensure_staging_tables(engine) -> None:
    tables = [
        FuelBvd.__table__,
        FuelBvdFieldCorrection.__table__,
        FuelBvdImportStage.__table__,
        FuelBvdStageRow.__table__,
        FuelBvdStageFieldCorrection.__table__,
    ]
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(lambda sync, t=table: t.create(sync, checkfirst=True))


async def _count_fuel_bvd(session: AsyncSession, tenant_id: int) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(FuelBvd).where(FuelBvd.tenant_id == tenant_id))
        or 0
    )


async def _purge_bvd_pdf_artifacts(session: AsyncSession, *, tenant_id: int, pdf_bytes: bytes) -> None:
    file_sha = sha256_hex(pdf_bytes)
    await session.execute(
        delete(FuelBvdImportStage).where(
            FuelBvdImportStage.tenant_id == tenant_id,
            FuelBvdImportStage.source_file_sha256 == file_sha,
        )
    )
    await session.execute(
        delete(FuelBvd).where(
            FuelBvd.tenant_id == tenant_id,
            FuelBvd.source_file_sha256 == file_sha,
        )
    )
    await session.commit()


async def _count_stage_rows(session: AsyncSession, tenant_id: int) -> int:
    reg = await session.scalar(text("SELECT to_regclass('fuel_bvd_import_stage')"))
    if reg is None:
        return 0
    return int(
        await session.scalar(
            select(func.count()).select_from(FuelBvdImportStage).where(FuelBvdImportStage.tenant_id == tenant_id)
        )
        or 0
    )


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="integration tenant DB required")
async def test_upload_creates_stage_zero_fuel_bvd(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _tenant_url()
    assert url is not None
    engine = create_async_engine(url, pool_pre_ping=True)
    await _ensure_staging_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stored_keys: list[str] = []

    async def _fake_stage_save(tenant_slug: str, stage_id: str, body: bytes, **kwargs):
        key = f"{tenant_slug}/fuel_bvd_stage/stage/{stage_id}/file.pdf"
        stored_keys.append(key)
        from app.core.storage import StoredFile

        return StoredFile(key, kwargs.get("filename_hint"), "application/pdf", len(body), sha256_hex(body))

    monkeypatch.setattr("app.services.fuel_bvd_stage.save_fuel_bvd_stage_bytes", _fake_stage_save)
    monkeypatch.setattr("app.services.fuel_bvd_stage.purge_expired_stages", AsyncMock(return_value=0))

    pdf_bytes = BVD_PDF.read_bytes()
    async with session_factory() as session:
        await _purge_bvd_pdf_artifacts(session, tenant_id=INTEGRATION_TENANT_ID, pdf_bytes=pdf_bytes)
        before = await _count_fuel_bvd(session, INTEGRATION_TENANT_ID)
        corr_before = await session.scalar(select(func.count()).select_from(FuelBvdFieldCorrection)) or 0
        stage_id, count, status, reused = await create_bvd_import_stage_from_pdf(
            session,
            tenant_id=INTEGRATION_TENANT_ID,
            tenant_slug="pytest",
            pdf_bytes=pdf_bytes,
            filename="BVD_invoice_972201.pdf",
            uploaded_by="staging_test",
        )
        assert status == "SUCCESS"
        assert count == 24
        assert reused is False
        after = await _count_fuel_bvd(session, INTEGRATION_TENANT_ID)
        corr_after = await session.scalar(select(func.count()).select_from(FuelBvdFieldCorrection)) or 0
        assert after == before
        assert corr_after == corr_before
        assert stored_keys and "fuel_bvd_stage/stage/" in stored_keys[0]
        stage = await get_active_stage(session, tenant_id=INTEGRATION_TENANT_ID, stage_id=stage_id)
        assert stage is not None
        assert stage.source_storage_ref == stored_keys[0]

        await discard_bvd_import_stage(
            session, tenant_id=INTEGRATION_TENANT_ID, tenant_slug="pytest", stage_id=stage_id
        )

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="integration tenant DB required")
async def test_discard_then_reupload_same_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _tenant_url()
    assert url is not None
    engine = create_async_engine(url, pool_pre_ping=True)
    await _ensure_staging_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _fake_stage_save(tenant_slug: str, stage_id: str, body: bytes, **kwargs):
        from app.core.storage import StoredFile

        key = f"{tenant_slug}/fuel_bvd_stage/stage/{stage_id}/file.pdf"
        return StoredFile(key, kwargs.get("filename_hint"), "application/pdf", len(body), sha256_hex(body))

    monkeypatch.setattr("app.services.fuel_bvd_stage.save_fuel_bvd_stage_bytes", _fake_stage_save)
    monkeypatch.setattr("app.services.fuel_bvd_stage.purge_expired_stages", AsyncMock(return_value=0))

    pdf = BVD_PDF.read_bytes()
    async with session_factory() as session:
        await _purge_bvd_pdf_artifacts(session, tenant_id=INTEGRATION_TENANT_ID, pdf_bytes=pdf)
        s1, *_ = await create_bvd_import_stage_from_pdf(
            session,
            tenant_id=INTEGRATION_TENANT_ID,
            tenant_slug="pytest",
            pdf_bytes=pdf,
            filename="BVD_invoice_972201.pdf",
            uploaded_by="staging_test",
        )
        await discard_bvd_import_stage(
            session, tenant_id=INTEGRATION_TENANT_ID, tenant_slug="pytest", stage_id=s1
        )
        s2, count, status, reused = await create_bvd_import_stage_from_pdf(
            session,
            tenant_id=INTEGRATION_TENANT_ID,
            tenant_slug="pytest",
            pdf_bytes=pdf,
            filename="BVD_invoice_972201.pdf",
            uploaded_by="staging_test",
        )
        assert status == "SUCCESS"
        assert count == 24
        assert reused is False
        assert s2 != s1
        await discard_bvd_import_stage(
            session, tenant_id=INTEGRATION_TENANT_ID, tenant_slug="pytest", stage_id=s2
        )

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="integration tenant DB required")
async def test_active_stage_duplicate_reuses_stage_id(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _tenant_url()
    assert url is not None
    engine = create_async_engine(url, pool_pre_ping=True)
    await _ensure_staging_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _fake_stage_save(tenant_slug: str, stage_id: str, body: bytes, **kwargs):
        from app.core.storage import StoredFile

        key = f"{tenant_slug}/fuel_bvd_stage/stage/{stage_id}/file.pdf"
        return StoredFile(key, kwargs.get("filename_hint"), "application/pdf", len(body), sha256_hex(body))

    monkeypatch.setattr("app.services.fuel_bvd_stage.save_fuel_bvd_stage_bytes", _fake_stage_save)
    monkeypatch.setattr("app.services.fuel_bvd_stage.purge_expired_stages", AsyncMock(return_value=0))

    pdf = BVD_PDF.read_bytes()
    async with session_factory() as session:
        await _purge_bvd_pdf_artifacts(session, tenant_id=INTEGRATION_TENANT_ID, pdf_bytes=pdf)
        s1, c1, st1, _ = await create_bvd_import_stage_from_pdf(
            session,
            tenant_id=INTEGRATION_TENANT_ID,
            tenant_slug="pytest",
            pdf_bytes=pdf,
            filename="BVD_invoice_972201.pdf",
            uploaded_by="staging_test",
        )
        s2, c2, st2, reused = await create_bvd_import_stage_from_pdf(
            session,
            tenant_id=INTEGRATION_TENANT_ID,
            tenant_slug="pytest",
            pdf_bytes=pdf,
            filename="BVD_invoice_972201.pdf",
            uploaded_by="staging_test",
        )
        assert s1 == s2
        assert reused is True
        assert c1 == c2 == 24
        assert st1 == st2
        await discard_bvd_import_stage(
            session, tenant_id=INTEGRATION_TENANT_ID, tenant_slug="pytest", stage_id=s1
        )

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="integration tenant DB required")
async def test_save_review_writes_stage_corrections_only(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _tenant_url()
    assert url is not None
    engine = create_async_engine(url, pool_pre_ping=True)
    await _ensure_staging_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _fake_stage_save(tenant_slug: str, stage_id: str, body: bytes, **kwargs):
        from app.core.storage import StoredFile

        key = f"{tenant_slug}/fuel_bvd_stage/stage/{stage_id}/file.pdf"
        return StoredFile(key, kwargs.get("filename_hint"), "application/pdf", len(body), sha256_hex(body))

    monkeypatch.setattr("app.services.fuel_bvd_stage.save_fuel_bvd_stage_bytes", _fake_stage_save)
    monkeypatch.setattr("app.services.fuel_bvd_stage.purge_expired_stages", AsyncMock(return_value=0))

    pdf_bytes = BVD_PDF.read_bytes()
    async with session_factory() as session:
        await _purge_bvd_pdf_artifacts(session, tenant_id=INTEGRATION_TENANT_ID, pdf_bytes=pdf_bytes)
        stage_id, *_ = await create_bvd_import_stage_from_pdf(
            session,
            tenant_id=INTEGRATION_TENANT_ID,
            tenant_slug="pytest",
            pdf_bytes=pdf_bytes,
            filename="BVD_invoice_972201.pdf",
            uploaded_by="staging_test",
        )
        rows = await list_bvd_import_rows_for_review(
            session, tenant_id=INTEGRATION_TENANT_ID, import_id=stage_id
        )
        txn = next(r for r in rows if r["row_type"] == "TRANSACTION")
        perm_before = await session.scalar(select(func.count()).select_from(FuelBvdFieldCorrection)) or 0
        written = await save_bvd_import_review(
            session,
            tenant_id=INTEGRATION_TENANT_ID,
            import_id=stage_id,
            reviewed_by="reviewer",
            corrections=[
                {
                    "fuel_bvd_id": txn["id"],
                    "field_name": "driver_name",
                    "reviewed_value": "Stage Driver",
                }
            ],
        )
        assert written == 1
        perm_after = await session.scalar(select(func.count()).select_from(FuelBvdFieldCorrection)) or 0
        assert perm_after == perm_before
        stage_corr = await session.scalar(
            select(func.count())
            .select_from(FuelBvdStageFieldCorrection)
            .where(FuelBvdStageFieldCorrection.stage_id == stage_id)
        )
        assert stage_corr == 1
        await discard_bvd_import_stage(
            session, tenant_id=INTEGRATION_TENANT_ID, tenant_slug="pytest", stage_id=stage_id
        )

    await engine.dispose()


@pytest.mark.asyncio
async def test_process_idempotent_when_permanent_already_committed() -> None:
    stage_id = uuid.uuid4()
    db = AsyncMock()
    summary = {
        "import_id": str(stage_id),
        "invoice_number": "972201",
        "row_count": 24,
        "transaction_count": 2,
        "correction_count": 0,
        "review_status": BVD_REVIEW_SOURCE_COMPLETE,
    }
    with patch(
        "app.services.fuel_bvd_stage._import_already_source_reviewed",
        AsyncMock(return_value=True),
    ):
        with patch(
            "app.services.fuel_bvd_stage._finish_idempotent_process_cleanup",
            AsyncMock(return_value=summary),
        ) as finish:
            out = await process_stage_to_permanent(
                db,
                tenant_id=53,
                tenant_slug="demo",
                stage_id=stage_id,
                reviewed_by="u",
            )
    assert out["review_status"] == BVD_REVIEW_SOURCE_COMPLETE
    finish.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_promotion_failure_keeps_stage() -> None:
    db = MagicMock()
    stage = FuelBvdImportStage(
        stage_id=uuid.uuid4(),
        tenant_id=53,
        provider_code="BVD",
        status=STAGE_STATUS_ACTIVE,
        source_file_name="x.pdf",
        source_file_sha256="abc",
        source_storage_ref="k",
        parse_status="SUCCESS",
    )
    rows = [{"row_type": "HEADER", "id": 1, "invoice_number": "1"}]

    with patch(
        "app.services.fuel_bvd_stage._import_already_source_reviewed",
        AsyncMock(return_value=False),
    ):
        with patch("app.services.fuel_bvd_stage.get_active_stage", AsyncMock(return_value=stage)):
            with patch("app.services.fuel_bvd_stage.list_stage_rows_for_review", AsyncMock(return_value=rows)):
                with patch(
                    "app.services.fuel_bvd_stage.reconcile_bvd_source_rows",
                    return_value=MagicMock(passed=True),
                ):
                    with patch(
                        "app.services.fuel_bvd_stage.acquire_bvd_import_advisory_lock",
                        AsyncMock(),
                    ):
                        with patch(
                            "app.services.fuel_bvd_stage.check_bvd_pdf_duplicate_before_import",
                            AsyncMock(return_value=None),
                        ):
                            with patch("app.services.fuel_bvd_stage.get_storage") as gs:
                                gs.return_value.read_bytes.return_value = b"%PDF-1.4"
                                with patch(
                                    "app.services.fuel_bvd_stage.save_fuel_bvd_import_bytes",
                                    AsyncMock(side_effect=RuntimeError("disk full")),
                                ):
                                    with pytest.raises(HTTPException) as exc:
                                        await process_stage_to_permanent(
                                            db,
                                            tenant_id=53,
                                            tenant_slug="demo",
                                            stage_id=stage.stage_id,
                                            reviewed_by="u",
                                        )
                                    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_cleanup_after_commit_failure_best_effort_orphan_purge() -> None:
    stage_id = uuid.uuid4()
    stage = FuelBvdImportStage(
        stage_id=stage_id,
        tenant_id=53,
        provider_code="BVD",
        status=STAGE_STATUS_ACTIVE,
        source_file_name="x.pdf",
        source_file_sha256="abc",
        source_storage_ref="k",
        parse_status="SUCCESS",
        uploaded_at=None,
    )
    header = {
        "row_type": "HEADER",
        "id": 10,
        "source_page": 1,
        "source_row_number": 1,
        "invoice_number": "972201",
        "invoice_date": "2026-07-01 00:00:00",
        "start_date": "2026-07-01 00:00:00",
        "end_date": "2026-07-31 23:59:59",
    }
    grand = {
        "row_type": "GRAND_TOTAL",
        "id": 11,
        "source_page": 1,
        "source_row_number": 2,
        "row_label": "Grand Total",
        "final_amt": "100.00",
        "cur": "CAD",
    }
    txn = {
        "row_type": "TRANSACTION",
        "id": 12,
        "source_page": 1,
        "source_row_number": 3,
        "auth_code": "A",
        "pre_tax_amt": "100.00",
        "final_amt": "100.00",
        "cur": "CAD",
    }
    rows = [header, grand, txn]

    async def _exec(*_a, **_k):
        class _Scalars:
            def all(self):
                return []

        class _Result:
            def scalars(self):
                return _Scalars()

        return _Result()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_exec)
    db.flush = AsyncMock()
    db.commit = AsyncMock(side_effect=RuntimeError("db down"))
    db.rollback = AsyncMock()
    db.add = MagicMock()

    stored = MagicMock(storage_key="perm/key.pdf")

    with patch(
        "app.services.fuel_bvd_stage._import_already_source_reviewed",
        AsyncMock(return_value=False),
    ):
        with patch("app.services.fuel_bvd_stage.get_active_stage", AsyncMock(return_value=stage)):
            with patch("app.services.fuel_bvd_stage.list_stage_rows_for_review", AsyncMock(return_value=rows)):
                with patch(
                    "app.services.fuel_bvd_stage.reconcile_bvd_source_rows",
                    return_value=MagicMock(passed=True, provider_grand_total="100.00"),
                ):
                    with patch(
                        "app.services.fuel_bvd_stage.project_bvd_rows_to_canonical",
                        return_value=([], []),
                    ):
                        with patch("app.services.fuel_bvd_stage.assert_canonical_money_gate"):
                            with patch(
                                "app.services.fuel_bvd_stage.build_fuel_source_batch",
                                return_value=MagicMock(id=1),
                            ):
                                with patch("app.services.fuel_bvd_stage.finalize_batch"):
                                    with patch("app.services.fuel_bvd_stage.get_storage") as gs:
                                        gs.return_value.read_bytes.return_value = b"%PDF-1.4"
                                        with patch(
                                            "app.services.fuel_bvd_stage.save_fuel_bvd_import_bytes",
                                            AsyncMock(return_value=stored),
                                        ):
                                            with patch(
                                                "app.services.fuel_bvd_stage.check_bvd_pdf_duplicate_before_import",
                                                AsyncMock(return_value=None),
                                            ):
                                                with patch(
                                                    "app.services.fuel_bvd_stage.acquire_bvd_import_advisory_lock",
                                                    AsyncMock(),
                                                ):
                                                    with patch(
                                                        "app.services.fuel_bvd_stage.purge_fuel_bvd_import_files"
                                                    ) as purge:
                                                        with pytest.raises(RuntimeError):
                                                            await process_stage_to_permanent(
                                                                db,
                                                                tenant_id=53,
                                                                tenant_slug="demo",
                                                                stage_id=stage_id,
                                                                reviewed_by="u",
                                                            )
                                                        db.rollback.assert_awaited()
                                                        purge.assert_called_once()
