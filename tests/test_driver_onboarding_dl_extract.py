"""Regression: CDL back PDF417 reads processed first, original upload as fallback."""

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
    assert dbg.get("original_fallback_used") is False


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
    assert dbg.get("original_fallback_used") is False
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
    intake = {"files": {"CDL_BACK": {"storage_key": "original-key", "enh_file_id": "processed-key"}}}

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
        out = await apply_stored_cdl_back_pdf417(
            intake, "processed-key", "demo", original_storage_key="original-key"
        )

    assert opened == ["processed-key"]
    assert out["license_extract_status"] == "SUCCESS"
    assert out.get("driver_license_number") == "H010062911981"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "processed"
    assert dbg.get("processed_fallback_used") is False
    assert dbg.get("original_fallback_used") is False


@pytest.mark.asyncio
async def test_processed_no_fields_falls_back_to_original(tmp_path: Path) -> None:
    proc = tmp_path / "proc.jpg"
    orig = tmp_path / "orig.jpg"
    proc.write_bytes(b"proc")
    orig.write_bytes(b"orig")
    opened: list[str] = []

    @contextmanager
    def fake_readable_path(storage_key: str, _kind: str, _slug: str):
        opened.append(storage_key)
        yield orig if storage_key == "original-key" else proc

    def fake_decode(path, mode="applicant_two_phase"):
        if Path(path).name == "orig.jpg":
            return SYNTHETIC_AAMVA, Pdf417DecodeMeta("fast_full_rgb", "zxing", [])
        return None, Pdf417DecodeMeta(None, None, [])

    with (
        patch.object(storage_mod, "readable_path", fake_readable_path),
        patch("app.services.applicant_dl_pdf417.decode_pdf417_barcode_with_trace", fake_decode),
    ):
        out = await apply_stored_cdl_back_pdf417(
            {"files": {"CDL_BACK": {"storage_key": "original-key"}}},
            "processed-key",
            "demo",
            original_storage_key="original-key",
        )

    assert opened == ["processed-key", "original-key"]
    assert out["license_extract_status"] == "SUCCESS"
    assert out.get("driver_license_number") == "H010062911981"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "original"
    assert dbg.get("original_fallback_used") is True
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
    assert out["license_extract_debug"].get("original_fallback_used") is False
    assert out["license_extract_debug"].get("barcode_image_source") == "processed"


@pytest.mark.asyncio
async def test_timeout_on_processed_falls_back_to_original(tmp_path: Path) -> None:
    proc = tmp_path / "proc.jpg"
    orig = tmp_path / "orig.jpg"
    proc.write_bytes(b"proc")
    orig.write_bytes(b"orig")
    opened: list[str] = []

    @contextmanager
    def fake_readable_path(storage_key: str, _kind: str, _slug: str):
        opened.append(storage_key)
        yield orig if storage_key == "original-key" else proc

    import asyncio

    real_wait_for = asyncio.wait_for

    async def fake_wait_for(aw, timeout=None):
        if opened[-1] == "processed-key":
            if hasattr(aw, "close"):
                aw.close()
            raise asyncio.TimeoutError()
        return await real_wait_for(aw, timeout=timeout)

    def fake_decode(path, mode="applicant_two_phase"):
        return SYNTHETIC_AAMVA, Pdf417DecodeMeta("fast_full_rgb", "zxing", [])

    with (
        patch.object(storage_mod, "readable_path", fake_readable_path),
        patch("app.services.applicant_dl_pdf417.asyncio.wait_for", fake_wait_for),
        patch("app.services.applicant_dl_pdf417.decode_pdf417_barcode_with_trace", fake_decode),
    ):
        out = await apply_stored_cdl_back_pdf417(
            {}, "processed-key", "demo", original_storage_key="original-key"
        )

    assert opened == ["processed-key", "original-key"]
    assert out["license_extract_status"] == "SUCCESS"
    assert out.get("driver_license_number") == "H010062911981"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "original"
    assert dbg.get("original_fallback_used") is True


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


_REGRESS_DIR = Path("/tmp/dl_pdf417_regress")
_IMG6446_PROCESSED = _REGRESS_DIR / "img6446_processed.jpg"
_IMG6446_ORIGINAL = _REGRESS_DIR / "img6446_original.jpg"
_IMG0084_PROCESSED = _REGRESS_DIR / "img0084_processed.jpg"
_IMG0084_ORIGINAL = _REGRESS_DIR / "img0084_original.jpg"


def _img6446_processed_warp() -> Path | None:
    candidates = [
        _IMG6446_PROCESSED,
        Path("/tmp/dl_pdf417_forensic/60001d44d82e4e70a198c981ef3cb78a.jpg"),
        Path("/tmp/app157_processed.jpg"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


@pytest.mark.asyncio
async def test_img6446_processed_succeeds_skips_original_fallback(tmp_path: Path) -> None:
    """Known-good IMG_6446 warp: processed SUCCESS, original file is never opened."""
    processed = _img6446_processed_warp()
    original = _IMG6446_ORIGINAL if _IMG6446_ORIGINAL.is_file() else None
    if processed is None or original is None:
        pytest.skip("IMG_6446 processed/original pair not present on this host")

    opened: list[str] = []
    dest_p = tmp_path / "processed.jpg"
    dest_o = tmp_path / "original.jpg"
    dest_p.write_bytes(processed.read_bytes())
    dest_o.write_bytes(original.read_bytes())

    @contextmanager
    def fake_readable_path(storage_key: str, _kind: str, _slug: str):
        opened.append(storage_key)
        yield dest_p if storage_key == "processed-key" else dest_o

    with patch.object(storage_mod, "readable_path", fake_readable_path):
        out = await apply_stored_cdl_back_pdf417(
            {}, "processed-key", "demo", original_storage_key="original-key"
        )

    assert opened == ["processed-key"]
    assert out["license_extract_status"] == "SUCCESS"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "processed"
    assert dbg.get("original_fallback_used") is False
    assert dbg.get("processed_fallback_used") is False
    assert int(dbg.get("meaningful_field_count") or 0) >= 15
    assert out.get("driver_license_number")
    assert out.get("first_name")
    assert out.get("last_name")


@pytest.mark.asyncio
async def test_img0084_processed_fails_original_fallback_succeeds(tmp_path: Path) -> None:
    """Safety net: the old 1544-pixel 1000×631 warp still falls back to original."""
    if not _IMG0084_PROCESSED.is_file() or not _IMG0084_ORIGINAL.is_file():
        pytest.skip("IMG_0084 processed/original pair not present on this host")

    opened: list[str] = []
    dest_p = tmp_path / "processed.jpg"
    dest_o = tmp_path / "original.jpg"
    dest_p.write_bytes(_IMG0084_PROCESSED.read_bytes())
    dest_o.write_bytes(_IMG0084_ORIGINAL.read_bytes())

    @contextmanager
    def fake_readable_path(storage_key: str, _kind: str, _slug: str):
        opened.append(storage_key)
        yield dest_p if storage_key == "processed-key" else dest_o

    with patch.object(storage_mod, "readable_path", fake_readable_path):
        out = await apply_stored_cdl_back_pdf417(
            {}, "processed-key", "demo", original_storage_key="original-key"
        )

    assert opened == ["processed-key", "original-key"]
    assert out["license_extract_status"] == "SUCCESS"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "original"
    assert dbg.get("original_fallback_used") is True
    assert dbg.get("processed_fallback_used") is False
    assert int(dbg.get("meaningful_field_count") or 0) >= 15
    assert out.get("driver_license_number")
    assert out.get("first_name")
    assert out.get("last_name")


@pytest.mark.asyncio
async def test_img0084_original_pixel_processed_succeeds_without_fallback(tmp_path: Path) -> None:
    """New OpenCV path: 1544 detection + original-pixel 1000×631 should hydrate without fallback."""
    if not _IMG0084_ORIGINAL.is_file():
        pytest.skip("IMG_0084 original not present on this host")

    from app.services.applicant_dl_preprocess import run_applicant_dl_opencv

    outcome = run_applicant_dl_opencv(_IMG0084_ORIGINAL)
    assert outcome.success is True
    assert outcome.jpeg_bytes
    assert outcome.debug.get("final_warp_source") == "original_pixels"

    opened: list[str] = []
    dest_p = tmp_path / "processed.jpg"
    dest_o = tmp_path / "original.jpg"
    dest_p.write_bytes(outcome.jpeg_bytes)
    dest_o.write_bytes(_IMG0084_ORIGINAL.read_bytes())

    @contextmanager
    def fake_readable_path(storage_key: str, _kind: str, _slug: str):
        opened.append(storage_key)
        yield dest_p if storage_key == "processed-key" else dest_o

    with patch.object(storage_mod, "readable_path", fake_readable_path):
        out = await apply_stored_cdl_back_pdf417(
            {}, "processed-key", "demo", original_storage_key="original-key"
        )

    assert opened == ["processed-key"]
    assert out["license_extract_status"] == "SUCCESS"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "processed"
    assert dbg.get("original_fallback_used") is False
    assert dbg.get("processed_fallback_used") is False
    assert int(dbg.get("meaningful_field_count") or 0) >= 15
    assert out.get("driver_license_number")
    assert out.get("first_name")
    assert out.get("last_name")


@pytest.mark.asyncio
async def test_both_images_fail_keeps_current_failure_status(tmp_path: Path) -> None:
    proc = tmp_path / "proc.jpg"
    orig = tmp_path / "orig.jpg"
    Image.new("RGB", (80, 50), "white").save(proc, "JPEG")
    Image.new("RGB", (80, 50), "white").save(orig, "JPEG")
    opened: list[str] = []

    @contextmanager
    def fake_readable_path(storage_key: str, _kind: str, _slug: str):
        opened.append(storage_key)
        yield orig if storage_key == "original-key" else proc

    with patch.object(storage_mod, "readable_path", fake_readable_path):
        out = await apply_stored_cdl_back_pdf417(
            {}, "processed-key", "demo", original_storage_key="original-key"
        )

    assert opened == ["processed-key", "original-key"]
    assert out["license_extract_status"] == "NO_FIELDS_FOUND"
    assert "license_extract_error" not in out
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("barcode_image_source") == "original"
    assert dbg.get("original_fallback_used") is True
    from app.routers.driver_onboarding import _pdf417_confirm_message

    assert _pdf417_confirm_message(out) == (
        "We could not read licence details from this photo. "
        "The photo is saved — you can upload a clearer back photo or enter details manually."
    )
