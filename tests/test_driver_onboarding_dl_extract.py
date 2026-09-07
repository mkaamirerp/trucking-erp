"""Regression: CDL back PDF417 reads the confirmed processed image only."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import app.core.storage as storage_mod
import pytest
from PIL import Image

from app.services.applicant_dl_pdf417 import (
    apply_stored_cdl_back_pdf417,
    clear_pdf417_extract_from_intake,
    pdf417_enabled_for_doc_type,
)
from app.services.dl_pdf417 import Pdf417DecodeMeta


SYNTHETIC_AAMVA = (
    "DLDAQH010062911981DCAF^DCSMOTORISTSAMPLE^DACJANEQA^DAD^"
    "DBD20160715^DBA20360115^DBB19850520^DAJON^DCGCAN^"
)


@pytest.mark.asyncio
async def test_apply_cdl_back_no_processed_image_is_failed() -> None:
    out = await apply_stored_cdl_back_pdf417({"step": "dl_upload"}, None, "demo")
    assert out["license_extract_status"] == "FAILED"
    assert out.get("license_extract_error") == "missing_processed_image"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "processed"
    assert dbg.get("processed_fallback_used") is False


@pytest.mark.asyncio
async def test_apply_cdl_back_success_when_decode_returns_aamva_text(tmp_path: Path) -> None:
    p = tmp_path / "processed.jpg"
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
        out = await apply_stored_cdl_back_pdf417({}, "processed-key", "demo")

    assert out["license_extract_status"] == "SUCCESS"
    assert out.get("driver_license_number") == "H010062911981"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("meaningful_field_count", 0) >= 1
    assert dbg.get("barcode_image_source") == "processed"
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
            "CDL_BACK": {"storage_key": "saved-key", "upload_status": "READY", "enh_file_id": "proc-key"},
        }
    }
    with patch.object(storage_mod, "readable_path", fake_readable_path):
        out = await apply_stored_cdl_back_pdf417(intake, "proc-key", "demo")

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
async def test_decode_opens_processed_key_never_original(tmp_path: Path) -> None:
    proc = tmp_path / "proc.jpg"
    proc.write_bytes(b"proc")
    opened: list[str] = []

    @contextmanager
    def fake_readable_path(storage_key: str, _kind: str, _slug: str):
        opened.append(storage_key)
        yield proc

    def fake_decode(path, mode="applicant_two_phase"):
        return SYNTHETIC_AAMVA, Pdf417DecodeMeta("fast_full_rgb", "zxing", [])

    with (
        patch.object(storage_mod, "readable_path", fake_readable_path),
        patch("app.services.applicant_dl_pdf417.decode_pdf417_barcode_with_trace", fake_decode),
    ):
        out = await apply_stored_cdl_back_pdf417({}, "processed-key", "demo")

    assert opened == ["processed-key"]
    assert out["license_extract_status"] == "SUCCESS"
    assert out.get("driver_license_number") == "H010062911981"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "processed"
    assert dbg.get("processed_fallback_used") is False


@pytest.mark.asyncio
async def test_timeout_on_processed_does_not_open_another_key(tmp_path: Path) -> None:
    proc = tmp_path / "proc.jpg"
    proc.write_bytes(b"proc")
    opened: list[str] = []

    @contextmanager
    def fake_readable_path(storage_key: str, _kind: str, _slug: str):
        opened.append(storage_key)
        yield proc

    import asyncio

    async def fake_wait_for(aw, timeout=None):
        if hasattr(aw, "close"):
            aw.close()
        raise asyncio.TimeoutError()

    with (
        patch.object(storage_mod, "readable_path", fake_readable_path),
        patch("app.services.applicant_dl_pdf417.asyncio.wait_for", fake_wait_for),
    ):
        out = await apply_stored_cdl_back_pdf417({}, "processed-key", "demo")

    assert opened == ["processed-key"]
    assert out["license_extract_status"] == "FAILED"
    assert out.get("license_extract_error") == "decode_timeout"
    assert out["license_extract_debug"].get("processed_fallback_used") is False
    assert out["license_extract_debug"].get("barcode_image_source") == "processed"


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


def test_clear_pdf417_extract_drops_stale_fields() -> None:
    intake = {
        "driver_license_number": "H010062911981",
        "first_name": "JANE",
        "phone": "555-0100",
        "license_extract_status": "SUCCESS",
        "license_extract_debug": {"attempted": True},
        "field_sources": {
            "license_number": {"source": "pdf417", "confidence": 0.93},
            "first_name": {"source": "pdf417", "confidence": 0.93},
        },
    }
    out = clear_pdf417_extract_from_intake(intake)
    assert "driver_license_number" not in out
    assert "first_name" not in out
    assert out.get("phone") == "555-0100"
    assert "license_extract_status" not in out
    assert "field_sources" not in out


def _img6446_processed_warp() -> Path | None:
    candidates = [
        Path("/tmp/dl_pdf417_forensic/60001d44d82e4e70a198c981ef3cb78a.jpg"),
        Path("/tmp/app157_processed.jpg"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


@pytest.mark.asyncio
async def test_img6446_processed_warp_pdf417_via_confirm_entry(tmp_path: Path) -> None:
    """Product path: PDF417 on the confirmed processed warp of IMG_6446, not the original."""
    src = _img6446_processed_warp()
    if src is None:
        pytest.skip("IMG_6446 processed warp not present on this host")

    dest = tmp_path / "processed.jpg"
    dest.write_bytes(src.read_bytes())

    @contextmanager
    def fake_readable_path(_storage_key: str, _kind: str, _slug: str):
        yield dest

    with patch.object(storage_mod, "readable_path", fake_readable_path):
        out = await apply_stored_cdl_back_pdf417({}, "processed-key", "demo")

    assert out["license_extract_status"] == "SUCCESS"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "processed"
    assert dbg.get("processed_fallback_used") is False
    assert int(dbg.get("meaningful_field_count") or 0) >= 15
    assert out.get("driver_license_number")
    assert out.get("first_name")
    assert out.get("last_name")
