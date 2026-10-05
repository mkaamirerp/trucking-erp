"""Toll Segment 2: FILE/CSV intake persistence (no TollFileIntake)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.core.storage import StoredFile
from app.deps.auth import get_current_user
from app.deps.entitlements import require_admin_sensitive_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.models.base import Base
from app.models.toll import (
    BATCH_STATUS_PARSED,
    FILE_FORMAT_CSV,
    SOURCE_TYPE_FILE,
    TollFileSourceRow,
    TollSourceBatch,
    TollTransaction,
)
from app.routers import tolls as tolls_router
from app.services.toll_csv_intake import (
    MAX_TOLL_CSV_ROWS,
    TollCsvIntakeError,
    list_duplicate_batch_ids,
    mapped_canonical_fields,
    parse_toll_csv_bytes,
    persist_toll_csv_file,
    read_toll_csv_upload_bounded,
    sha256_hex,
)
from tests.test_toll_segment_1 import FORBIDDEN_TOLL_COLUMNS

GENERIC_CSV = (
    b"Posted Date,Agency,Amount,Plate\n"
    b"2026-03-01 10:05,Niagara,$5.25,ABC123\n"
    b"2026-03-01 10:42,I-90,\"12.00\",ABC123\n"
)

LOCKED_GENERIC_CSV = b"Date,Unit,Amount,Unknown\n10/01/2026,1104,5.25,ABC\n"


class FakeScalars:
    def __init__(self, ids: list[int]) -> None:
        self._ids = ids

    def all(self) -> list[int]:
        return list(self._ids)


class FakeResult:
    def __init__(self, ids: list[int]) -> None:
        self._ids = ids

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._ids)


def _like_needles(stmt: Any) -> list[str]:
    try:
        compiled = stmt.compile()
    except Exception:
        return []
    needles: list[str] = []
    for value in compiled.params.values():
        if isinstance(value, str) and "%" in value:
            needle = value.replace("\\%", "\x00").replace("%", "").replace("\x00", "%")
            needle = needle.replace("\\_", "_").replace("\\\\", "\\").strip().lower()
            if needle:
                needles.append(needle)
    return needles


def _stmt_limit_offset(stmt: Any) -> tuple[int | None, int | None]:
    def _as_int(raw: Any) -> int | None:
        if raw is None:
            return None
        if hasattr(raw, "value"):
            raw = raw.value
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    limit = _as_int(getattr(stmt, "_limit", None))
    if limit is None:
        limit = _as_int(getattr(stmt, "_limit_clause", None))
    offset = _as_int(getattr(stmt, "_offset", None))
    if offset is None:
        offset = _as_int(getattr(stmt, "_offset_clause", None))
    return limit, offset


def _eq_filters(stmt: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    where = getattr(stmt, "whereclause", None)
    if where is None:
        return out
    clauses = list(getattr(where, "clauses", [where]))
    for clause in clauses:
        left = getattr(clause, "left", None)
        right = getattr(clause, "right", None)
        if left is None:
            continue
        name = getattr(left, "key", None)
        value = getattr(right, "value", right)
        if hasattr(value, "value"):
            value = value.value
        out[name] = value
    return out


class FakeTollSession:
    """Tenant-scoped stand-in for AsyncSession used by Segment 2 persist tests."""

    def __init__(self) -> None:
        self.batches: list[TollSourceBatch] = []
        self.rows: list[TollFileSourceRow] = []
        self.transactions: list[TollTransaction] = []
        self._pending: list[Any] = []
        self._next_id = 1
        self.committed = False
        self.rolled_back = False
        self.raise_on_flush = False
        self.expire_ids_on_commit = False
        self.execute_calls = 0

    def add(self, obj: Any) -> None:
        self._pending.append(obj)

    async def flush(self) -> None:
        if self.raise_on_flush:
            raise RuntimeError("flush failed")
        for obj in self._pending:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1
            if isinstance(obj, TollSourceBatch):
                self.batches.append(obj)
            elif isinstance(obj, TollFileSourceRow):
                self.rows.append(obj)
            elif isinstance(obj, TollTransaction):
                self.transactions.append(obj)
        self._pending.clear()

    async def commit(self) -> None:
        self.committed = True
        if self.expire_ids_on_commit:
            for batch in self.batches:
                batch.id = None
            for row in self.rows:
                row.id = None

    async def rollback(self) -> None:
        self.rolled_back = True
        self._pending.clear()
        if not self.committed:
            self.batches.clear()
            self.rows.clear()
            self.transactions.clear()

    async def execute(self, stmt: Any) -> FakeResult:
        self.execute_calls += 1
        filters = _eq_filters(stmt)
        tenant_id = filters.get("tenant_id")
        source_hash = filters.get("source_hash")
        batch_id = filters.get("batch_id")
        object_id = filters.get("id")
        source_type = filters.get("source_type")
        needles = _like_needles(stmt)
        limit, offset = _stmt_limit_offset(stmt)
        descs = list(getattr(stmt, "column_descriptions", []) or [])
        names = [d.get("name") for d in descs]
        entity = descs[0].get("entity") if descs else None
        froms = list(stmt.get_final_froms()) if hasattr(stmt, "get_final_froms") else []
        from_names = {getattr(item, "name", None) for item in froms}
        batches = [
            batch
            for batch in self.batches
            if batch.id is not None
            and (tenant_id is None or batch.tenant_id == tenant_id)
            and (source_hash is None or batch.source_hash == source_hash)
            and (source_type is None or batch.source_type == source_type)
            and (object_id is None or entity is TollFileSourceRow or batch.id == object_id)
        ]
        if needles:
            batches = [
                batch
                for batch in batches
                if any(
                    needle in (batch.source_filename or "").lower()
                    or needle in (batch.source_hash or "").lower()
                    for needle in needles
                )
            ]
        batches.sort(key=lambda batch: int(batch.id or 0), reverse=names != ["id"])
        if names == ["id"] and entity is not TollFileSourceRow:
            batches.sort(key=lambda batch: int(batch.id or 0))
            return FakeResult([int(batch.id) for batch in batches])
        if entity is TollFileSourceRow or TollFileSourceRow.__tablename__ in from_names:
            rows = [
                row
                for row in self.rows
                if (tenant_id is None or row.tenant_id == tenant_id)
                and (batch_id is None or row.batch_id == batch_id)
            ]
            rows.sort(key=lambda row: row.source_row_order)
            start = offset or 0
            end = start + limit if limit is not None else None
            rows = rows[start:end]
            return FakeResult(rows)
        if limit is not None:
            batches = batches[:limit]
        return FakeResult(batches)

    async def scalar(self, stmt: Any) -> Any:
        items = (await self.execute(stmt)).scalars().all()
        return items[0] if items else None


async def _fake_store(
    tenant_slug: str,
    intake_token: str,
    body: bytes,
    *,
    filename_hint: str,
) -> StoredFile:
    key = f"{tenant_slug}/toll/csv/{intake_token}/{filename_hint}"
    return StoredFile(
        storage_key=key,
        original_filename=filename_hint,
        content_type="text/csv",
        file_size_bytes=len(body),
        sha256=sha256_hex(body),
    )


class RecordingStore:
    def __init__(self) -> None:
        self.saved: list[str] = []
        self.deleted: list[str] = []
        self.fail_save = False
        self.fail_delete = False

    async def store(
        self,
        tenant_slug: str,
        intake_token: str,
        body: bytes,
        *,
        filename_hint: str,
    ) -> StoredFile:
        if self.fail_save:
            raise RuntimeError("storage save failed")
        stored = await _fake_store(
            tenant_slug, intake_token, body, filename_hint=filename_hint
        )
        self.saved.append(stored.storage_key)
        return stored

    def delete(self, storage_key: str, *, tenant_slug: str | None = None) -> None:
        _ = tenant_slug
        if self.fail_delete:
            raise RuntimeError("storage delete failed")
        self.deleted.append(storage_key)


def _unique_names(table) -> set[str]:
    return {uq.name for uq in table.constraints if isinstance(uq, UniqueConstraint) and uq.name}


def _fk_names(table) -> set[str]:
    return {
        fk.name
        for fk in table.constraints
        if isinstance(fk, ForeignKeyConstraint) and fk.name
    }


def test_toll_file_intakes_does_not_exist() -> None:
    import app.models.toll as toll_models

    assert "toll_file_intakes" not in Base.metadata.tables
    assert not hasattr(toll_models, "TollFileIntake")


def test_toll_file_source_rows_exists() -> None:
    assert "toll_file_source_rows" in Base.metadata.tables
    assert TollFileSourceRow.__tablename__ == "toll_file_source_rows"
    assert "uq_toll_file_source_rows_tenant_batch_source_row_order" in _unique_names(
        TollFileSourceRow.__table__
    )
    assert "fk_toll_file_source_rows_batch_tenant" in _fk_names(TollFileSourceRow.__table__)


@pytest.mark.asyncio
async def test_valid_csv_persists_one_file_batch_and_source_rows() -> None:
    db = FakeTollSession()
    result = await persist_toll_csv_file(
        db,
        tenant_id=7,
        tenant_slug="demo",
        filename="tolls.csv",
        body=GENERIC_CSV,
        store_bytes=_fake_store,
    )
    assert db.committed is True
    assert len(db.batches) == 1
    batch = db.batches[0]
    assert batch.source_type == SOURCE_TYPE_FILE
    assert batch.file_format == FILE_FORMAT_CSV
    assert batch.source_filename == "tolls.csv"
    assert batch.source_hash == sha256_hex(GENERIC_CSV)
    assert batch.source_storage_ref.startswith("demo/toll/csv/")
    assert batch.status == BATCH_STATUS_PARSED
    assert result.batch_id == batch.id
    assert [row.source_row_order for row in db.rows] == [1, 2]
    assert db.rows[0].cells["Amount"] == "$5.25"
    assert db.rows[1].values == ["2026-03-01 10:42", "I-90", "12.00", "ABC123"]
    assert db.rows[0].source_line_number == 2
    assert db.rows[1].source_line_number == 3
    assert batch.csv_column_keys == ["Posted Date", "Agency", "Amount", "Plate"]
    assert batch.csv_raw_header_names == ["Posted Date", "Agency", "Amount", "Plate"]
    assert batch.csv_parsed_row_count == 2
    assert batch.csv_parser_name == "generic_csv"
    assert db.transactions == []


@pytest.mark.asyncio
async def test_original_file_is_stored_through_existing_storage_abstraction() -> None:
    stored: dict[str, Any] = {}

    async def capture_store(tenant_slug: str, intake_token: str, body: bytes, *, filename_hint: str) -> StoredFile:
        stored["tenant_slug"] = tenant_slug
        stored["intake_token"] = intake_token
        stored["body"] = body
        stored["filename_hint"] = filename_hint
        return await _fake_store(tenant_slug, intake_token, body, filename_hint=filename_hint)

    db = FakeTollSession()
    result = await persist_toll_csv_file(
        db,
        tenant_id=1,
        tenant_slug="acme",
        filename="portal.csv",
        body=GENERIC_CSV,
        store_bytes=capture_store,
    )
    assert stored["tenant_slug"] == "acme"
    assert stored["body"] == GENERIC_CSV
    assert stored["filename_hint"] == "portal.csv"
    assert result.source_storage_ref == db.batches[0].source_storage_ref
    assert "/toll/csv/" in result.source_storage_ref


@pytest.mark.asyncio
async def test_save_toll_csv_file_bytes_writes_original_bytes(tmp_path: Path) -> None:
    from app.core.storage import LocalStorageBackend, save_toll_csv_file_bytes

    backend = LocalStorageBackend()
    with patch("app.core.storage.settings") as mock_settings:
        mock_settings.local_storage_dir = str(tmp_path)
        mock_settings.company_docs_dir = None
        with patch("app.core.storage.get_storage", return_value=backend):
            db = FakeTollSession()
            result = await persist_toll_csv_file(
                db,
                tenant_id=1,
                tenant_slug="demo",
                filename="tolls.csv",
                body=GENERIC_CSV,
            )
    stored_path = tmp_path / result.source_storage_ref
    assert stored_path.is_file()
    assert stored_path.read_bytes() == GENERIC_CSV
    assert result.source_hash == sha256_hex(GENERIC_CSV)
    assert db.batches[0].source_storage_ref == result.source_storage_ref


@pytest.mark.asyncio
async def test_db_failure_removes_local_storage_object(tmp_path: Path) -> None:
    from app.core.storage import LocalStorageBackend

    backend = LocalStorageBackend()
    with patch("app.core.storage.settings") as mock_settings:
        mock_settings.local_storage_dir = str(tmp_path)
        mock_settings.company_docs_dir = None
        with patch("app.core.storage.get_storage", return_value=backend):
            db = FakeTollSession()
            db.raise_on_flush = True
            with pytest.raises(RuntimeError, match="flush failed"):
                await persist_toll_csv_file(
                    db,
                    tenant_id=1,
                    tenant_slug="demo",
                    filename="tolls.csv",
                    body=GENERIC_CSV,
                )
    leftover_files = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert leftover_files == []
    assert db.batches == []
    assert db.rows == []


def test_utf8_bom_quoted_commas_duplicate_headers_and_strings() -> None:
    bom = b"\xef\xbb\xbfAmount,Amount\n\"1,00\",2\n"
    parsed = parse_toll_csv_bytes(bom)
    assert parsed.encoding == "utf-8-sig"
    assert parsed.header_names == ("Amount", "Amount")
    assert parsed.cell_keys == ("Amount", "Amount__2")
    assert parsed.rows[0].cells["Amount"] == "1,00"
    assert parsed.rows[0].cells["Amount__2"] == "2"
    assert parsed.rows[0].values == ("1,00", "2")
    assert isinstance(parsed.rows[0].cells["Amount"], str)


def test_generic_parse_boundary_locked_example() -> None:
    parsed = parse_toll_csv_bytes(LOCKED_GENERIC_CSV)
    assert parsed.rows[0].cells == {
        "Date": "10/01/2026",
        "Unit": "1104",
        "Amount": "5.25",
        "Unknown": "ABC",
    }
    assert parsed.rows[0].cells["Date"] == "10/01/2026"
    assert parsed.rows[0].cells["Amount"] == "5.25"
    assert mapped_canonical_fields(parsed.rows[0].cells) == {}
    staging_cols = set(TollFileSourceRow.__table__.c.keys())
    assert "truck_id" not in staging_cols
    assert "amount" not in staging_cols
    assert "transaction_datetime" not in staging_cols
    assert "transaction_type" not in staging_cols


@pytest.mark.asyncio
async def test_same_hash_creates_multiple_batches_and_reports_duplicate() -> None:
    db = FakeTollSession()
    first = await persist_toll_csv_file(
        db,
        tenant_id=9,
        tenant_slug="demo",
        filename="a.csv",
        body=GENERIC_CSV,
        store_bytes=_fake_store,
    )
    second = await persist_toll_csv_file(
        db,
        tenant_id=9,
        tenant_slug="demo",
        filename="b.csv",
        body=GENERIC_CSV,
        store_bytes=_fake_store,
    )
    assert first.source_hash == second.source_hash
    assert first.batch_id != second.batch_id
    assert first.source_storage_ref != second.source_storage_ref
    assert first.source_storage_ref.startswith("demo/toll/csv/")
    assert second.source_storage_ref.startswith("demo/toll/csv/")
    assert len(db.batches) == 2
    assert first.duplicate_match_count == 0
    assert first.duplicate_batch_ids == ()
    assert second.duplicate_match_count == 1
    assert second.duplicate_batch_ids == (first.batch_id,)
    hash_indexes = [
        ix
        for ix in TollSourceBatch.__table__.indexes
        if ix.name == "ix_toll_source_batches_tenant_source_hash"
    ]
    assert hash_indexes[0].unique is False


@pytest.mark.asyncio
async def test_duplicate_lookup_is_tenant_isolated() -> None:
    db = FakeTollSession()
    tenant_a = await persist_toll_csv_file(
        db,
        tenant_id=53,
        tenant_slug="alpha",
        filename="tolls.csv",
        body=GENERIC_CSV,
        store_bytes=_fake_store,
    )
    tenant_b = await persist_toll_csv_file(
        db,
        tenant_id=54,
        tenant_slug="beta",
        filename="tolls.csv",
        body=GENERIC_CSV,
        store_bytes=_fake_store,
    )
    assert tenant_a.source_hash == tenant_b.source_hash
    assert tenant_a.source_storage_ref.startswith("alpha/toll/csv/")
    assert tenant_b.source_storage_ref.startswith("beta/toll/csv/")
    assert tenant_a.source_storage_ref != tenant_b.source_storage_ref
    a_ids = await list_duplicate_batch_ids(
        db, tenant_id=53, source_hash=tenant_a.source_hash
    )
    b_ids = await list_duplicate_batch_ids(
        db, tenant_id=54, source_hash=tenant_b.source_hash
    )
    assert a_ids == [tenant_a.batch_id]
    assert b_ids == [tenant_b.batch_id]
    assert tenant_a.batch_id not in b_ids
    assert tenant_b.batch_id not in a_ids
    assert tenant_b.duplicate_match_count == 0


@pytest.mark.asyncio
async def test_provider_account_connection_may_be_null() -> None:
    db = FakeTollSession()
    await persist_toll_csv_file(
        db,
        tenant_id=1,
        tenant_slug="demo",
        filename="tolls.csv",
        body=GENERIC_CSV,
        store_bytes=_fake_store,
    )
    batch = db.batches[0]
    assert batch.provider_code is None
    assert batch.provider_connection_id is None
    assert batch.account_reference is None


@pytest.mark.asyncio
async def test_flush_failure_rolls_back_partial_batch() -> None:
    db = FakeTollSession()
    db.raise_on_flush = True
    store = RecordingStore()
    with pytest.raises(RuntimeError, match="flush failed"):
        await persist_toll_csv_file(
            db,
            tenant_id=1,
            tenant_slug="demo",
            filename="tolls.csv",
            body=GENERIC_CSV,
            store_bytes=store.store,
            delete_stored=store.delete,
        )
    assert db.rolled_back is True
    assert db.committed is False
    assert db.batches == []
    assert db.rows == []
    assert len(store.saved) == 1
    assert store.deleted == store.saved


@pytest.mark.asyncio
async def test_db_failure_deletes_only_this_intake_object() -> None:
    db = FakeTollSession()
    store = RecordingStore()
    first = await persist_toll_csv_file(
        db,
        tenant_id=1,
        tenant_slug="demo",
        filename="keep.csv",
        body=GENERIC_CSV,
        store_bytes=store.store,
        delete_stored=store.delete,
    )
    db.raise_on_flush = True
    with pytest.raises(RuntimeError, match="flush failed"):
        await persist_toll_csv_file(
            db,
            tenant_id=1,
            tenant_slug="demo",
            filename="orphan.csv",
            body=GENERIC_CSV,
            store_bytes=store.store,
            delete_stored=store.delete,
        )
    assert first.source_storage_ref not in store.deleted
    assert store.deleted == [store.saved[-1]]
    assert store.saved[-1] != first.source_storage_ref
    assert any(batch.source_storage_ref == first.source_storage_ref for batch in db.batches)


@pytest.mark.asyncio
async def test_cleanup_failure_preserves_original_db_error(caplog: pytest.LogCaptureFixture) -> None:
    db = FakeTollSession()
    db.raise_on_flush = True
    store = RecordingStore()
    store.fail_delete = True
    with caplog.at_level("ERROR", logger="app.services.toll_csv_intake"):
        with pytest.raises(RuntimeError, match="flush failed"):
            await persist_toll_csv_file(
                db,
                tenant_id=1,
                tenant_slug="demo",
                filename="tolls.csv",
                body=GENERIC_CSV,
                store_bytes=store.store,
                delete_stored=store.delete,
            )
    assert "storage cleanup failed after DB rollback" in caplog.text
    assert "AWS" not in caplog.text
    assert "secret" not in caplog.text.lower()
    assert db.committed is False
    assert db.batches == []


@pytest.mark.asyncio
async def test_storage_failure_commits_no_batch_or_rows() -> None:
    db = FakeTollSession()
    store = RecordingStore()
    store.fail_save = True
    with pytest.raises(RuntimeError, match="storage save failed"):
        await persist_toll_csv_file(
            db,
            tenant_id=1,
            tenant_slug="demo",
            filename="tolls.csv",
            body=GENERIC_CSV,
            store_bytes=store.store,
            delete_stored=store.delete,
        )
    assert store.saved == []
    assert store.deleted == []
    assert db.committed is False
    assert db.batches == []
    assert db.rows == []


@pytest.mark.asyncio
async def test_validation_failure_does_not_store_file() -> None:
    db = FakeTollSession()
    store = RecordingStore()
    with pytest.raises(TollCsvIntakeError) as err:
        await persist_toll_csv_file(
            db,
            tenant_id=1,
            tenant_slug="demo",
            filename="bill.pdf",
            body=b"%PDF-1.7\n1 0 obj",
            store_bytes=store.store,
            delete_stored=store.delete,
        )
    assert err.value.code == "TOLL_CSV_NOT_CSV"
    assert store.saved == []
    assert store.deleted == []
    assert db.batches == []
    assert db.rows == []


def test_reject_empty_binary_pdf_xlsx() -> None:
    from app.services.toll_csv_intake import validate_toll_csv_file

    with pytest.raises(TollCsvIntakeError) as named_pdf:
        validate_toll_csv_file(filename="bill.pdf", body=b"%PDF-1.7\n1 0 obj")
    assert named_pdf.value.code == "TOLL_CSV_NOT_CSV"
    with pytest.raises(TollCsvIntakeError) as empty_err:
        validate_toll_csv_file(filename="empty.csv", body=b"")
    assert empty_err.value.code == "TOLL_CSV_EMPTY"
    with pytest.raises(TollCsvIntakeError) as nul_err:
        validate_toll_csv_file(filename="bin.csv", body=b"Date,Amount\n\x00\x01")
    assert nul_err.value.code == "TOLL_CSV_BINARY"
    with pytest.raises(TollCsvIntakeError) as xlsx_err:
        validate_toll_csv_file(filename="tolls.xlsx", body=b"PK\x03\x04not-csv")
    assert xlsx_err.value.code == "TOLL_CSV_NOT_CSV"


def test_staging_has_no_payroll_canonical_or_intake_table() -> None:
    from app.services import toll_csv_intake as intake

    cols = set(TollFileSourceRow.__table__.c.keys())
    assert FORBIDDEN_TOLL_COLUMNS & cols == set()
    assert "amount" not in cols
    assert "truck_id" not in cols
    assert "ezpass_profile" not in cols
    assert "parser_name" not in cols
    assert not hasattr(intake, "persist_created_canonical_transactions")


def test_csv_api_route_is_registered() -> None:
    paths = {getattr(route, "path", None) for route in tolls_router.router.routes}
    assert "/tolls/files/csv" in paths


@pytest.mark.asyncio
async def test_csv_api_intake_and_tenant_isolation() -> None:
    shared_db = FakeTollSession()

    async def _db_a():
        yield shared_db

    app_a = FastAPI()
    app_a.include_router(tolls_router.router, prefix="/api/v1")
    app_a.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id="u1")
    app_a.dependency_overrides[require_admin_sensitive_entitlement] = lambda: None
    app_a.dependency_overrides[require_tenant] = lambda: 53
    app_a.dependency_overrides[require_tenant_slug] = lambda: "alpha"
    app_a.dependency_overrides[get_tenant_db] = _db_a

    # persist_toll_csv_file uses real store_bytes default; override by patching
    from unittest.mock import patch

    with patch(
        "app.services.toll_csv_intake.save_toll_csv_file_bytes",
        new=_fake_store,
    ):
        client = TestClient(app_a)
        first = client.post(
            "/api/v1/tolls/files/csv",
            files={"file": ("tolls.csv", GENERIC_CSV, "text/csv")},
        )
        assert first.status_code == 201, first.text
        body = first.json()
        assert body["source_type"] == "FILE"
        assert body["file_format"] == "CSV"
        assert body["filename"] == "tolls.csv"
        assert body["row_count"] == 2
        assert body["duplicate_match_count"] == 0
        assert "file" not in body
        assert "source_storage_ref" not in body
        assert body["headers"] == ["Posted Date", "Agency", "Amount", "Plate"]
        assert body["csv_column_keys"] == body["headers"]
        assert body["csv_raw_header_names"] == ["Posted Date", "Agency", "Amount", "Plate"]
        assert body["preview_rows"][0]["Amount"] == "$5.25"

        second = client.post(
            "/api/v1/tolls/files/csv",
            files={"file": ("tolls.csv", GENERIC_CSV, "text/csv")},
        )
        assert second.status_code == 201
        assert second.json()["duplicate_match_count"] == 1
        assert second.json()["duplicate_batch_ids"] == [body["batch_id"]]
        assert second.json()["batch_id"] != body["batch_id"]

        app_b = FastAPI()
        app_b.include_router(tolls_router.router, prefix="/api/v1")
        app_b.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id="u2")
        app_b.dependency_overrides[require_admin_sensitive_entitlement] = lambda: None
        app_b.dependency_overrides[require_tenant] = lambda: 54
        app_b.dependency_overrides[require_tenant_slug] = lambda: "beta"
        app_b.dependency_overrides[get_tenant_db] = _db_a
        client_b = TestClient(app_b)
        other = client_b.post(
            "/api/v1/tolls/files/csv",
            files={"file": ("tolls.csv", GENERIC_CSV, "text/csv")},
        )
        assert other.status_code == 201
        assert other.json()["duplicate_match_count"] == 0
        assert body["batch_id"] not in other.json()["duplicate_batch_ids"]
        assert "source_storage_ref" not in other.json()


def test_duplicate_and_blank_headers_normalize_in_source_order() -> None:
    parsed = parse_toll_csv_bytes(b" Amount ,Amount,\n1,2,3\n")
    assert parsed.header_names == (" Amount ", "Amount", "")
    assert parsed.cell_keys == ("Amount", "Amount__2", "column_3")
    assert parsed.rows[0].cells["Amount"] == "1"
    assert parsed.rows[0].cells["Amount__2"] == "2"
    assert parsed.rows[0].cells["column_3"] == "3"


def test_extra_column_synthetic_keys_do_not_overwrite_column_5_header() -> None:
    parsed = parse_toll_csv_bytes(b"column_5,b,c,d\nKEEP_ME,2,3,4,EXTRA\n")
    assert parsed.cell_keys == ("column_5", "b", "c", "d", "extra_column_5")
    assert parsed.rows[0].cells["column_5"] == "KEEP_ME"
    assert parsed.rows[0].cells["extra_column_5"] == "EXTRA"
    assert parsed.rows[0].values == ("KEEP_ME", "2", "3", "4", "EXTRA")


def test_extra_column_key_is_unique_against_existing_extra_column_header() -> None:
    parsed = parse_toll_csv_bytes(b"extra_column_5,b,c,d\nKEEP,2,3,4,EXTRA\n")
    assert parsed.cell_keys == ("extra_column_5", "b", "c", "d", "extra_column_5__2")
    assert parsed.rows[0].cells["extra_column_5"] == "KEEP"
    assert parsed.rows[0].cells["extra_column_5__2"] == "EXTRA"


def test_source_line_number_survives_skipped_blank_rows() -> None:
    body = b"Date,Amount\nrowA,1\n\nrowB,2\n"
    parsed = parse_toll_csv_bytes(body)
    assert parsed.skipped_blank_row_count == 1
    assert [row.source_row_order for row in parsed.rows] == [1, 2]
    assert [row.source_line_number for row in parsed.rows] == [2, 4]


def test_header_only_csv_is_rejected() -> None:
    with pytest.raises(TollCsvIntakeError) as err:
        parse_toll_csv_bytes(b"Date,Amount\n")
    assert err.value.code == "TOLL_CSV_NO_DATA_ROWS"


@pytest.mark.asyncio
async def test_header_only_csv_does_not_store_or_persist() -> None:
    db = FakeTollSession()
    store = RecordingStore()
    with pytest.raises(TollCsvIntakeError) as err:
        await persist_toll_csv_file(
            db,
            tenant_id=1,
            tenant_slug="demo",
            filename="headers.csv",
            body=b"Date,Amount\n",
            store_bytes=store.store,
            delete_stored=store.delete,
        )
    assert err.value.code == "TOLL_CSV_NO_DATA_ROWS"
    assert store.saved == []
    assert db.batches == []
    assert db.rows == []
    assert db.committed is False


def test_row_cap_is_enforced_before_returning_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.toll_csv_intake.MAX_TOLL_CSV_ROWS", 2)
    with pytest.raises(TollCsvIntakeError) as err:
        parse_toll_csv_bytes(b"a\n1\n2\n3\n")
    assert err.value.code == "TOLL_CSV_TOO_MANY_ROWS"
    assert MAX_TOLL_CSV_ROWS == 50_000


@pytest.mark.asyncio
async def test_row_cap_rejects_before_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.toll_csv_intake.MAX_TOLL_CSV_ROWS", 1)
    db = FakeTollSession()
    store = RecordingStore()
    with pytest.raises(TollCsvIntakeError) as err:
        await persist_toll_csv_file(
            db,
            tenant_id=1,
            tenant_slug="demo",
            filename="dense.csv",
            body=b"a\n1\n2\n",
            store_bytes=store.store,
            delete_stored=store.delete,
        )
    assert err.value.code == "TOLL_CSV_TOO_MANY_ROWS"
    assert store.saved == []
    assert db.batches == []


@pytest.mark.asyncio
async def test_bounded_upload_read_rejects_without_retaining_full_body() -> None:
    class _ChunkedUpload:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload
            self.requested: list[int] = []

        async def read(self, size: int = -1) -> bytes:
            self.requested.append(size)
            if size < 0:
                chunk = self._payload
                self._payload = b""
                return chunk
            chunk = self._payload[:size]
            self._payload = self._payload[size:]
            return chunk

    upload = _ChunkedUpload(b"x" * 40)
    with pytest.raises(TollCsvIntakeError) as err:
        await read_toll_csv_upload_bounded(upload, max_bytes=10)
    assert err.value.code == "TOLL_CSV_TOO_LARGE"
    assert sum(upload.requested) <= 11
    assert all(n <= 11 for n in upload.requested)


@pytest.mark.asyncio
async def test_persist_captures_primitives_before_commit_expire() -> None:
    db = FakeTollSession()
    db.expire_ids_on_commit = True
    result = await persist_toll_csv_file(
        db,
        tenant_id=3,
        tenant_slug="demo",
        filename="tolls.csv",
        body=GENERIC_CSV,
        store_bytes=_fake_store,
    )
    assert db.committed is True
    assert db.batches[0].id is None
    assert isinstance(result.batch_id, int)
    assert result.batch_id > 0
    payload = result.as_api_dict()
    assert payload["batch_id"] == result.batch_id
    assert "source_storage_ref" not in payload
    assert payload["csv_column_keys"] == ["Posted Date", "Agency", "Amount", "Plate"]


@pytest.mark.asyncio
async def test_upload_and_detail_share_normalized_ordered_keys() -> None:
    db = FakeTollSession()
    result = await persist_toll_csv_file(
        db,
        tenant_id=5,
        tenant_slug="demo",
        filename="dup.csv",
        body=b" Amount ,Amount,\n1,2,3\n",
        store_bytes=_fake_store,
    )
    from app.services.toll_file_history import get_toll_file_batch

    detail = await get_toll_file_batch(db, tenant_id=5, batch_id=result.batch_id)
    keys = ["Amount", "Amount__2", "column_3"]
    assert list(result.csv_column_keys) == keys
    assert result.as_api_dict()["headers"] == keys
    assert result.as_api_dict()["csv_column_keys"] == keys
    assert result.as_api_dict()["csv_raw_header_names"] == [" Amount ", "Amount", ""]
    assert detail["headers"] == keys
    assert detail["csv_column_keys"] == keys
    assert detail["csv_raw_header_names"] == [" Amount ", "Amount", ""]
    assert "source_storage_ref" not in detail


@pytest.mark.asyncio
async def test_header_order_does_not_follow_jsonb_object_key_order() -> None:
    import json

    from app.services.toll_file_history import get_toll_file_batch

    db = FakeTollSession()
    result = await persist_toll_csv_file(
        db,
        tenant_id=6,
        tenant_slug="demo",
        filename="order.csv",
        body=b"Zed,Amount,Unit\nz,1,u\n",
        store_bytes=_fake_store,
    )
    row = db.rows[0]
    row.cells = json.loads(json.dumps(row.cells, sort_keys=True))
    assert list(row.cells.keys()) != ["Zed", "Amount", "Unit"]
    detail = await get_toll_file_batch(db, tenant_id=6, batch_id=result.batch_id)
    assert detail["headers"] == ["Zed", "Amount", "Unit"]
    assert detail["csv_column_keys"] == ["Zed", "Amount", "Unit"]
    assert detail["headers"] != list(row.cells.keys())
