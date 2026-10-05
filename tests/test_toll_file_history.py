"""Toll FILE history/search: list + expand raw CSV rows (no canonical mapping)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps.auth import get_current_user
from app.deps.entitlements import require_admin_sensitive_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.models.toll import (
    BATCH_STATUS_PARSED,
    FILE_FORMAT_CSV,
    SOURCE_TYPE_API,
    SOURCE_TYPE_FILE,
    TollFileSourceRow,
    TollSourceBatch,
)
from app.routers import tolls as tolls_router
from app.services.toll_csv_intake import TollCsvIntakeError
from app.services.toll_file_history import (
    batch_matches_search,
    get_toll_file_batch,
    headers_from_source_rows,
    list_toll_file_batches,
)
from tests.test_toll_segment_2 import GENERIC_CSV, FakeTollSession, _fake_store

CANONICAL_TOP_LEVEL_KEYS = {
    "transaction_date",
    "transaction_datetime",
    "unit_number",
    "unit_number_snapshot",
    "truck_id",
    "agency",
    "toll_agency",
    "amount",
    "transaction_type",
    "read_type",
    "read_by",
    "identifier",
    "device_number",
    "plate_number",
}


def _file_batch(
    *,
    tenant_id: int,
    batch_id: int,
    filename: str,
    source_hash: str = "abc123",
    source_type: str = SOURCE_TYPE_FILE,
) -> TollSourceBatch:
    batch = TollSourceBatch(
        tenant_id=tenant_id,
        source_type=source_type,
        file_format=FILE_FORMAT_CSV if source_type == SOURCE_TYPE_FILE else None,
        source_filename=filename,
        source_hash=source_hash,
        source_storage_ref=f"{tenant_id}/toll/csv/{filename}",
        status=BATCH_STATUS_PARSED,
    )
    batch.id = batch_id
    batch.imported_at = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    return batch


def _source_row(*, tenant_id: int, batch_id: int, order: int, cells: dict[str, str]) -> TollFileSourceRow:
    row = TollFileSourceRow(
        tenant_id=tenant_id,
        batch_id=batch_id,
        source_row_order=order,
        cells=cells,
        values=list(cells.values()),
    )
    row.id = order
    return row


def test_history_routes_are_registered() -> None:
    paths = {getattr(route, "path", None) for route in tolls_router.router.routes}
    assert "/tolls/files" in paths
    assert "/tolls/files/{batch_id}" in paths
    assert "/tolls/files/csv" in paths


def test_search_matches_filename_and_hash_only() -> None:
    batch = _file_batch(tenant_id=1, batch_id=1, filename="portal.csv", source_hash="deadbeef")
    assert batch_matches_search(batch, "PORTAL")
    assert batch_matches_search(batch, "dead")
    assert not batch_matches_search(batch, "Niagara")
    assert batch_matches_search(batch, "  ")


def test_headers_follow_source_cell_keys() -> None:
    rows = [
        _source_row(
            tenant_id=1,
            batch_id=1,
            order=1,
            cells={"Posted Date": "2026-03-01", "Agency": "Niagara", "Amount": "$5.25"},
        )
    ]
    assert headers_from_source_rows(rows) == ["Posted Date", "Agency", "Amount"]
    assert "Unit" not in headers_from_source_rows(rows)
    assert "Date/Time" not in headers_from_source_rows(rows)


@pytest.mark.asyncio
async def test_list_file_batches_filters_search_and_source_type() -> None:
    db = FakeTollSession()
    db.batches.extend(
        [
            _file_batch(tenant_id=53, batch_id=2, filename="keep.csv", source_hash="aaa111"),
            _file_batch(tenant_id=53, batch_id=1, filename="other.csv", source_hash="bbb222"),
            _file_batch(tenant_id=54, batch_id=9, filename="keep.csv", source_hash="ccc333"),
            _file_batch(
                tenant_id=53,
                batch_id=8,
                filename="api.csv",
                source_hash="ddd444",
                source_type=SOURCE_TYPE_API,
            ),
        ]
    )
    db.rows.append(
        _source_row(
            tenant_id=53,
            batch_id=2,
            order=1,
            cells={"Posted Date": "2026-03-01", "Agency": "Niagara"},
        )
    )
    items = await list_toll_file_batches(db, tenant_id=53, q="keep")
    assert [item["batch_id"] for item in items] == [2]
    assert items[0]["row_count"] == 1
    assert items[0]["filename"] == "keep.csv"
    assert items[0]["source_type"] == "FILE"
    all_items = await list_toll_file_batches(db, tenant_id=53)
    assert [item["batch_id"] for item in all_items] == [2, 1]
    assert 8 not in [item["batch_id"] for item in all_items]
    assert 9 not in [item["batch_id"] for item in all_items]
    hash_other = await list_toll_file_batches(db, tenant_id=53, q="ccc333")
    assert hash_other == []
    filename_other = await list_toll_file_batches(db, tenant_id=53, q="api.csv")
    assert filename_other == []
    assert db.transactions == []


@pytest.mark.asyncio
async def test_get_file_batch_returns_raw_cells_and_404s_cross_tenant() -> None:
    db = FakeTollSession()
    db.batches.append(_file_batch(tenant_id=53, batch_id=2, filename="keep.csv"))
    db.rows.append(
        _source_row(
            tenant_id=53,
            batch_id=2,
            order=1,
            cells={"Posted Date": "2026-03-01 10:05", "Agency": "Niagara", "Amount": "$5.25", "Plate": "ABC123"},
        )
    )
    detail = await get_toll_file_batch(db, tenant_id=53, batch_id=2)
    assert detail["headers"] == ["Posted Date", "Agency", "Amount", "Plate"]
    assert detail["rows"][0]["cells"]["Agency"] == "Niagara"
    assert "unit_number" not in detail
    assert "truck_id" not in detail
    with pytest.raises(TollCsvIntakeError) as err:
        await get_toll_file_batch(db, tenant_id=54, batch_id=2)
    assert err.value.code == "TOLL_FILE_NOT_FOUND"
    assert err.value.http_status == 404
    assert db.transactions == []


def _app(db: FakeTollSession, tenant_id: int) -> FastAPI:
    async def _yield_db():
        yield db

    app = FastAPI()
    app.include_router(tolls_router.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id="u1")
    app.dependency_overrides[require_admin_sensitive_entitlement] = lambda: None
    app.dependency_overrides[require_tenant] = lambda: tenant_id
    app.dependency_overrides[require_tenant_slug] = lambda: "demo"
    app.dependency_overrides[get_tenant_db] = _yield_db
    return app


@pytest.mark.asyncio
async def test_history_http_list_detail_and_tenant_404() -> None:
    db = FakeTollSession()
    with patch("app.services.toll_csv_intake.save_toll_csv_file_bytes", new=_fake_store):
        client = TestClient(_app(db, 53))
        created = client.post(
            "/api/v1/tolls/files/csv",
            files={"file": ("portal.csv", GENERIC_CSV, "text/csv")},
        )
        assert created.status_code == 201, created.text
        batch_id = created.json()["batch_id"]
        source_hash = created.json()["source_hash"]
        assert db.transactions == []

        listed = client.get("/api/v1/tolls/files", params={"q": "portal"})
        assert listed.status_code == 200, listed.text
        assert listed.json()[0]["batch_id"] == batch_id
        assert listed.json()[0]["row_count"] == 2
        assert listed.json()[0]["status"] == "PARSED"
        assert "preview_rows" not in listed.json()[0]
        assert CANONICAL_TOP_LEVEL_KEYS.isdisjoint(listed.json()[0].keys())

        by_hash = client.get("/api/v1/tolls/files", params={"q": source_hash})
        assert [item["batch_id"] for item in by_hash.json()] == [batch_id]

        detail = client.get(f"/api/v1/tolls/files/{batch_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["headers"] == ["Posted Date", "Agency", "Amount", "Plate"]
        assert body["rows"][0]["cells"]["Amount"] == "$5.25"
        assert "Date/Time" not in body["headers"]
        assert "Unit" not in body["headers"]
        assert "Read By" not in body["headers"]
        assert "Identifier" not in body["headers"]
        assert CANONICAL_TOP_LEVEL_KEYS.isdisjoint(body.keys())
        assert db.transactions == []

        duplicate = client.post(
            "/api/v1/tolls/files/csv",
            files={"file": ("portal.csv", GENERIC_CSV, "text/csv")},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["duplicate_match_count"] == 1
        assert duplicate.json()["duplicate_batch_ids"] == [batch_id]
        assert duplicate.json()["batch_id"] != batch_id
        assert db.transactions == []

        other = TestClient(_app(db, 54))
        missing = other.get(f"/api/v1/tolls/files/{batch_id}")
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "TOLL_FILE_NOT_FOUND"
        empty = other.get("/api/v1/tolls/files")
        assert empty.status_code == 200
        assert empty.json() == []
        filename_leak = other.get("/api/v1/tolls/files", params={"q": "portal"})
        assert filename_leak.json() == []
        hash_leak = other.get("/api/v1/tolls/files", params={"q": source_hash})
        assert hash_leak.json() == []
        other_dup_id = other.get(f"/api/v1/tolls/files/{duplicate.json()['batch_id']}")
        assert other_dup_id.status_code == 404
