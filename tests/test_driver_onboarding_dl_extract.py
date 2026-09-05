"""Regression: CDL back upload must not report SUCCESS when PDF417 yields no license fields."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import app.core.storage as storage_mod
import pytest
from PIL import Image

from app.services.applicant_dl_pdf417 import (
    apply_stored_cdl_back_pdf417,
    pdf417_enabled_for_doc_type,
)
from app.services.dl_pdf417 import Pdf417DecodeMeta


SYNTHETIC_AAMVA = (
    "DLDAQH010062911981DCAF^DCSMOTORISTSAMPLE^DACJANEQA^DAD^"
    "DBD20160715^DBA20360115^DBB19850520^DAJON^DCGCAN^"
)


@pytest.mark.asyncio
async def test_apply_cdl_back_no_barcode_image_is_no_fields_found(tmp_path: Path) -> None:
    p = tmp_path / "back.jpg"
    Image.new("RGB", (120, 120), color="white").save(p, "JPEG")

    @contextmanager
    def fake_readable_path(_storage_key: str, _kind: str, _slug: str):
        yield p

    with patch.object(storage_mod, "readable_path", fake_readable_path):
        out = await apply_stored_cdl_back_pdf417({"step": "dl_upload"}, "fake-key", "demo")

    assert out["license_extract_status"] == "NO_FIELDS_FOUND"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("attempted") is True
    assert dbg.get("decode_succeeded") is False
    assert dbg.get("meaningful_field_count") == 0
    assert dbg.get("decode_attempt_count", 0) >= 1
    assert dbg.get("decode_winning_candidate") is None
    assert dbg.get("barcode_image_source") == "original"
    assert dbg.get("processed_fallback_used") is False


@pytest.mark.asyncio
async def test_apply_cdl_back_success_when_decode_returns_aamva_text(tmp_path: Path) -> None:
    p = tmp_path / "back.jpg"
    p.write_bytes(b"x")

    @contextmanager
    def fake_readable_path(_storage_key: str, _kind: str, _slug: str):
        yield p

    with (
        patch.object(storage_mod, "readable_path", fake_readable_path),
        patch(
            "app.services.applicant_dl_pdf417.decode_pdf417_barcode_with_trace",
            return_value=(SYNTHETIC_AAMVA, Pdf417DecodeMeta("mock", "zxing", [])),
        ),
    ):
        out = await apply_stored_cdl_back_pdf417({}, "fake-key", "demo")

    assert out["license_extract_status"] == "SUCCESS"
    assert out.get("driver_license_number") == "H010062911981"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("meaningful_field_count", 0) >= 1
    assert dbg.get("barcode_image_source") == "original"
    assert "H010062911981" not in str(dbg)
    assert "pdf417_text" not in dbg


@pytest.mark.asyncio
async def test_apply_cdl_back_preserves_existing_intake_files(tmp_path: Path) -> None:
    p = tmp_path / "back.jpg"
    Image.new("RGB", (30, 30), color="white").save(p, "JPEG")

    @contextmanager
    def fake_readable_path(_storage_key: str, _kind: str, _slug: str):
        yield p

    intake = {
        "files": {
            "CDL_BACK": {"storage_key": "saved-key", "upload_status": "READY"},
        }
    }
    with patch.object(storage_mod, "readable_path", fake_readable_path):
        out = await apply_stored_cdl_back_pdf417(intake, "saved-key", "demo")

    assert out["files"]["CDL_BACK"]["storage_key"] == "saved-key"
    assert out["license_extract_status"] == "NO_FIELDS_FOUND"


@pytest.mark.asyncio
async def test_apply_cdl_back_failed_on_missing_file(tmp_path: Path) -> None:
    p = tmp_path / "nope.jpg"

    @contextmanager
    def fake_readable_path(_storage_key: str, _kind: str, _slug: str):
        yield p

    with patch.object(storage_mod, "readable_path", fake_readable_path):
        out = await apply_stored_cdl_back_pdf417({}, "fake-key", "demo")

    assert out["license_extract_status"] == "FAILED"
    assert out.get("license_extract_error") == "source_file_missing"


def test_front_does_not_invoke_pdf417() -> None:
    assert pdf417_enabled_for_doc_type("CDL_FRONT") is False
    assert pdf417_enabled_for_doc_type("CDL_BACK") is True
    assert pdf417_enabled_for_doc_type("OTHER") is False


@pytest.mark.asyncio
async def test_back_extraction_prefers_original_and_skips_processed(tmp_path: Path) -> None:
    orig = tmp_path / "orig.jpg"
    proc = tmp_path / "proc.jpg"
    orig.write_bytes(b"orig")
    proc.write_bytes(b"proc")
    opened: list[str] = []

    @contextmanager
    def fake_readable_path(storage_key: str, _kind: str, _slug: str):
        opened.append(storage_key)
        yield orig if storage_key == "original-key" else proc

    decode_paths: list[str] = []

    def fake_decode(path, mode="applicant_two_phase"):
        decode_paths.append(str(path))
        return SYNTHETIC_AAMVA, Pdf417DecodeMeta("fast_full_rgb", "zxing", [])

    with (
        patch.object(storage_mod, "readable_path", fake_readable_path),
        patch("app.services.applicant_dl_pdf417.decode_pdf417_barcode_with_trace", fake_decode),
    ):
        out = await apply_stored_cdl_back_pdf417(
            {},
            "original-key",
            "demo",
            processed_storage_key="processed-key",
        )

    assert opened == ["original-key"]
    assert decode_paths == [str(orig)]
    assert out["license_extract_status"] == "SUCCESS"
    assert out.get("driver_license_number") == "H010062911981"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "original"
    assert dbg.get("processed_fallback_used") is False


@pytest.mark.asyncio
async def test_processed_fallback_only_when_original_fails(tmp_path: Path) -> None:
    orig = tmp_path / "orig.jpg"
    proc = tmp_path / "proc.jpg"
    Image.new("RGB", (40, 40), "white").save(orig, "JPEG")
    proc.write_bytes(b"proc")
    opened: list[str] = []

    @contextmanager
    def fake_readable_path(storage_key: str, _kind: str, _slug: str):
        opened.append(storage_key)
        yield orig if storage_key == "original-key" else proc

    def fake_decode(path, mode="applicant_two_phase"):
        if str(path) == str(orig):
            return None, Pdf417DecodeMeta(None, None, [{"ok": False, "engine": "zxing"}])
        return SYNTHETIC_AAMVA, Pdf417DecodeMeta("fast_full_rgb", "zxing", [])

    with (
        patch.object(storage_mod, "readable_path", fake_readable_path),
        patch("app.services.applicant_dl_pdf417.decode_pdf417_barcode_with_trace", fake_decode),
    ):
        out = await apply_stored_cdl_back_pdf417(
            {},
            "original-key",
            "demo",
            processed_storage_key="processed-key",
        )

    assert opened == ["original-key", "processed-key"]
    assert out["license_extract_status"] == "SUCCESS"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "processed"
    assert dbg.get("processed_fallback_used") is True


@pytest.mark.asyncio
async def test_no_fields_preserves_existing_pdf417_intake_values(tmp_path: Path) -> None:
    p = tmp_path / "back.jpg"
    Image.new("RGB", (40, 40), "white").save(p, "JPEG")

    @contextmanager
    def fake_readable_path(_storage_key: str, _kind: str, _slug: str):
        yield p

    intake = {
        "driver_license_number": "KEEP-EXISTING",
        "license_expiry": "2030-01-01",
        "field_sources": {"license_number": {"source": "pdf417", "confidence": 0.93}},
    }
    with patch.object(storage_mod, "readable_path", fake_readable_path):
        out = await apply_stored_cdl_back_pdf417(intake, "saved-key", "demo")

    assert out["license_extract_status"] == "NO_FIELDS_FOUND"
    assert out["driver_license_number"] == "KEEP-EXISTING"
    assert out["license_expiry"] == "2030-01-01"
    assert out["field_sources"]["license_number"]["source"] == "pdf417"


@pytest.mark.asyncio
async def test_timeout_does_not_start_processed_fallback(tmp_path: Path) -> None:
    orig = tmp_path / "orig.jpg"
    orig.write_bytes(b"orig")
    opened: list[str] = []

    @contextmanager
    def fake_readable_path(storage_key: str, _kind: str, _slug: str):
        opened.append(storage_key)
        yield orig

    import asyncio

    async def fake_wait_for(aw, timeout=None):
        if hasattr(aw, "close"):
            aw.close()
        raise asyncio.TimeoutError()

    with (
        patch.object(storage_mod, "readable_path", fake_readable_path),
        patch("app.services.applicant_dl_pdf417.asyncio.wait_for", fake_wait_for),
    ):
        out = await apply_stored_cdl_back_pdf417(
            {},
            "original-key",
            "demo",
            processed_storage_key="processed-key",
        )

    assert opened == ["original-key"]
    assert out["license_extract_status"] == "FAILED"
    assert out.get("license_extract_error") == "decode_timeout"
    assert out["license_extract_debug"].get("processed_fallback_used") is False
