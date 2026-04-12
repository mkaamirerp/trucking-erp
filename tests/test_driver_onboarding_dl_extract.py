"""Regression: CDL back upload must not report SUCCESS when PDF417 yields no license fields."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import app.core.storage as storage_mod
import pytest
from PIL import Image

from app.services.applicant_dl_pdf417 import apply_stored_cdl_back_pdf417
from app.services.dl_pdf417 import Pdf417DecodeMeta


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


@pytest.mark.asyncio
async def test_apply_cdl_back_success_when_decode_returns_aamva_text(tmp_path: Path) -> None:
    p = tmp_path / "back.jpg"
    p.write_bytes(b"x")

    synthetic = (
        "DLDAQH010062911981DCAF^DCSMOTORISTSAMPLE^DACJANEQA^DAD^"
        "DBD20160715^DBA20360115^DBB19850520^DAJON^DCGCAN^"
    )

    @contextmanager
    def fake_readable_path(_storage_key: str, _kind: str, _slug: str):
        yield p

    with (
        patch.object(storage_mod, "readable_path", fake_readable_path),
        patch(
            "app.services.applicant_dl_pdf417.decode_pdf417_barcode_with_trace",
            return_value=(synthetic, Pdf417DecodeMeta("mock", "zxing", [])),
        ),
    ):
        out = await apply_stored_cdl_back_pdf417({}, "fake-key", "demo")

    assert out["license_extract_status"] == "SUCCESS"
    assert out.get("driver_license_number") == "H010062911981"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("meaningful_field_count", 0) >= 1


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
