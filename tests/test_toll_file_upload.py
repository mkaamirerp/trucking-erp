"""Unified Toll file upload: kind detection, provider gate, evidence gate."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.toll_file_upload import (
    KIND_CSV,
    KIND_IMAGE,
    KIND_OTHER,
    KIND_PDF,
    NOT_A_TOLL_FILE,
    TollFileUploadError,
    classify_toll_upload_kind,
    ingest_toll_upload,
)
from app.services.toll_wvpa_pdf import TollPdfIntakeError
from tests.support.toll_wvpa_fixture import build_non_wvpa_pdf, build_wvpa_monthly_statement_pdf
from tests.test_toll_wvpa_pdf import FakePdfSession, _store


def test_classifies_pdf_csv_and_image() -> None:
    assert classify_toll_upload_kind(filename="a.pdf", body=b"%PDF-1.4", content_type="application/pdf") == KIND_PDF
    assert classify_toll_upload_kind(filename="a.csv", body=b"Date,Amount\n1,2\n", content_type="text/csv") == KIND_CSV
    assert classify_toll_upload_kind(filename="a.jpg", body=b"\xff\xd8\xff\xe0rest", content_type="image/jpeg") == KIND_IMAGE
    assert classify_toll_upload_kind(filename="a.png", body=b"\x89PNG\r\n\x1a\nrest", content_type="image/png") == KIND_IMAGE
    assert classify_toll_upload_kind(filename="notes.txt", body=b"hello", content_type="text/plain") == KIND_OTHER


@pytest.mark.asyncio
async def test_provider_required() -> None:
    db = FakePdfSession()
    with pytest.raises(TollFileUploadError) as err:
        await ingest_toll_upload(
            db,
            tenant_id=7,
            tenant_slug="demo",
            filename="a.pdf",
            body=b"%PDF-1.4",
            content_type="application/pdf",
            provider_code=None,
            created_by="u1",
        )
    assert err.value.code == "TOLL_PROVIDER_REQUIRED"


@pytest.mark.asyncio
async def test_prepass_not_wired() -> None:
    db = FakePdfSession()
    with pytest.raises(TollFileUploadError) as err:
        await ingest_toll_upload(
            db,
            tenant_id=7,
            tenant_slug="demo",
            filename="a.pdf",
            body=build_wvpa_monthly_statement_pdf(),
            content_type="application/pdf",
            provider_code="PREPASS",
            created_by="u1",
        )
    assert err.value.code == "TOLL_PROVIDER_NOT_IMPLEMENTED"
    assert db.reviews == []


@pytest.mark.asyncio
async def test_csv_not_wired() -> None:
    db = FakePdfSession()
    with pytest.raises(TollFileUploadError) as err:
        await ingest_toll_upload(
            db,
            tenant_id=7,
            tenant_slug="demo",
            filename="tolls.csv",
            body=b"Date,Amount\n2026-01-01,5.00\n",
            content_type="text/csv",
            provider_code="EZPASS",
            created_by="u1",
        )
    assert err.value.code == "TOLL_CSV_NOT_WIRED"
    assert db.reviews == []


@pytest.mark.asyncio
async def test_image_is_not_a_toll_file_without_readable_evidence() -> None:
    db = FakePdfSession()
    with pytest.raises(TollFileUploadError) as err:
        await ingest_toll_upload(
            db,
            tenant_id=7,
            tenant_slug="demo",
            filename="receipt.jpg",
            body=b"\xff\xd8\xff\xe0not-a-statement",
            content_type="image/jpeg",
            provider_code="EZPASS",
            created_by="u1",
        )
    assert err.value.code == "TOLL_NOT_A_TOLL_FILE"
    assert err.value.message == NOT_A_TOLL_FILE


@pytest.mark.asyncio
async def test_non_toll_pdf_is_not_a_toll_file() -> None:
    db = FakePdfSession()
    with pytest.raises(TollFileUploadError) as err:
        await ingest_toll_upload(
            db,
            tenant_id=7,
            tenant_slug="demo",
            filename="other.pdf",
            body=build_non_wvpa_pdf(),
            content_type="application/pdf",
            provider_code="EZPASS",
            created_by="u1",
        )
    assert err.value.code == "TOLL_NOT_A_TOLL_FILE"
    assert err.value.message == NOT_A_TOLL_FILE
    assert db.reviews == []


@pytest.mark.asyncio
async def test_ezpass_pdf_with_evidence_persists_review() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        result = await ingest_toll_upload(
            db,
            tenant_id=7,
            tenant_slug="demo",
            filename="wvpa.pdf",
            body=build_wvpa_monthly_statement_pdf(),
            content_type="application/pdf",
            provider_code="EZPASS",
            created_by="u1",
        )
    assert result["detected_kind"] == KIND_PDF
    assert result["provider_code"] == "EZPASS"
    assert result["parsed_trip_count"] == 74
    assert result["profile_code"] == "EZPASS_WVPA_MONTHLY_STATEMENT_PDF"
    assert len(db.review_rows) == 74


@pytest.mark.asyncio
async def test_unreadable_pdf_maps_to_not_a_toll_file() -> None:
    db = FakePdfSession()
    with patch(
        "app.services.toll_file_upload.persist_toll_pdf_file",
        side_effect=TollPdfIntakeError("TOLL_PDF_UNREADABLE", "no text"),
    ):
        with pytest.raises(TollFileUploadError) as err:
            await ingest_toll_upload(
                db,
                tenant_id=7,
                tenant_slug="demo",
                filename="scan.pdf",
                body=b"%PDF-1.4 empty",
                content_type="application/pdf",
                provider_code="EZPASS",
                created_by="u1",
            )
    assert err.value.code == "TOLL_NOT_A_TOLL_FILE"
