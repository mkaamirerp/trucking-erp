"""Applicant DL OpenCV preprocessing wrapper tests.

Hermetic tests (always run): working-scale contract on generated images.
Private battery tests: IMG6446 operator fixture only; skip when not installed.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.services.applicant_dl_opencv import (
    PREPROCESS_VERSION,
    TARGET_H,
    TARGET_W,
    _confirm_all_four_corners,
    map_working_corners_to_original,
    rotate_image,
)
from app.services.applicant_dl_preprocess import (
    WORKING_COPY_MAX_SIDE,
    _prepare_working_copy,
    run_applicant_dl_opencv,
)

_PRIVATE_SKIP = "private DL regression fixture not installed"
_PRIVATE_FILENAME = "IMG_6446_normalized.jpg"
_LIVE_0084 = Path("/tmp/dl_pdf417_regress/img0084_original.jpg")
_LIVE_6446 = Path("/tmp/dl_pdf417_regress/img6446_original.jpg")
_OLD_0084_WORKING_COPY_WARP_SHA = (
    "0b3e22b23c942b9298561f6e63aabfe1ddeb28e4483fe0086eb1c5f0f8b3f290"
)


def _private_img6446() -> Path | None:
    raw = (os.environ.get("DL_PRIVATE_FIXTURE_DIR") or "/home/admin/private_test_fixtures/dl").strip()
    path = Path(raw) / _PRIVATE_FILENAME
    return path if path.is_file() else None


def _cleanup_working_copy(temp_path: Path | None) -> None:
    if temp_path is not None:
        temp_path.unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _synthetic_cool_card(height: int = 900, width: int = 1400) -> np.ndarray:
    """Generated non-sensitive card: cool HSV fill + dark border (ID-1-ish ratio)."""
    hsv = np.zeros((height, width, 3), dtype=np.uint8)
    hsv[:] = (0, 0, 30)
    x0, y0, x1, y1 = 280, 190, 1120, 710
    hsv[y0:y1, x0:x1] = (90, 180, 200)
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    cv2.rectangle(bgr, (x0, y0), (x1, y1), (15, 15, 15), 10)
    return bgr


def test_preprocess_version():
    assert PREPROCESS_VERSION.startswith("2026-08-29")


def test_canny_second_locator_exists() -> None:
    from app.services.applicant_dl_opencv import _canny_rough_card_candidates

    img = np.full((900, 1400, 3), 40, dtype=np.uint8)
    cv2.rectangle(img, (350, 200), (1050, 650), (230, 230, 230), -1)
    cv2.rectangle(img, (350, 200), (1050, 650), (20, 20, 20), 6)
    seeds = _canny_rough_card_candidates(img)
    assert isinstance(seeds, list)
    for seed in seeds:
        assert seed.get("rough_locator") == "CANNY"
        assert "is_closeup_seed" in seed


def test_run_opencv_missing_file_returns_failed(tmp_path: Path) -> None:
    outcome = run_applicant_dl_opencv(tmp_path / "nope.jpg")
    assert outcome.success is False
    assert outcome.jpeg_bytes is None


def test_random_noise_image_fails_without_fallback(tmp_path: Path) -> None:
    img = np.random.randint(0, 255, (4032, 3024, 3), dtype=np.uint8)
    path = tmp_path / "big.jpg"
    cv2.imwrite(str(path), img)
    outcome = run_applicant_dl_opencv(path)
    assert outcome.success is False
    assert outcome.jpeg_bytes is None
    assert outcome.debug.get("status") == "FOUR_CORNERS_NOT_CONFIRMED"
    assert outcome.debug.get("method") is None


def test_confirmation_gate_requires_ratio_band() -> None:
    """Sandbox ratio gate 1.25-1.95 must reject extreme quads."""
    img = np.full((800, 1200, 3), 40, dtype=np.uint8)
    box = np.array([[100, 100], [1100, 120], [1080, 700], [80, 680]], dtype=np.float32)
    corners, diag, _ = _confirm_all_four_corners(img, box)
    assert corners is None or diag.get("confirmed") is False


def test_run_opencv_card_like_rectangle_may_process(tmp_path: Path) -> None:
    img = np.full((900, 1400, 3), 40, dtype=np.uint8)
    x0, y0, x1, y1 = 350, 200, 1050, 650
    cv2.rectangle(img, (x0, y0), (x1, y1), (230, 230, 230), -1)
    cv2.rectangle(img, (x0, y0), (x1, y1), (20, 20, 20), 6)
    path = tmp_path / "card.jpg"
    cv2.imwrite(str(path), img)
    outcome = run_applicant_dl_opencv(path)
    assert outcome.debug.get("preprocess_version")


def test_working_copy_max_side_is_frozen_1544() -> None:
    assert WORKING_COPY_MAX_SIDE == 1544


def test_working_copy_downscales_source_above_1544(tmp_path: Path) -> None:
    img = np.full((2400, 1350, 3), 40, dtype=np.uint8)
    path = tmp_path / "above.jpg"
    cv2.imwrite(str(path), img)
    before = _file_sha256(path)
    work_path, temp_path, meta = _prepare_working_copy(path)
    try:
        shape = meta["opencv_input_shape"]
        assert max(shape["width"], shape["height"]) == 1544
        assert meta["working_copy_downscaled"] is True
        assert meta["original_input_shape"] == {"width": 1350, "height": 2400}
        assert work_path != path
        assert _file_sha256(path) == before
    finally:
        _cleanup_working_copy(temp_path)


def test_working_copy_does_not_downscale_source_at_or_below_1544(tmp_path: Path) -> None:
    img = np.full((1024, 768, 3), 40, dtype=np.uint8)
    path = tmp_path / "below.jpg"
    cv2.imwrite(str(path), img)
    before = _file_sha256(path)
    _work_path, temp_path, meta = _prepare_working_copy(path)
    try:
        assert meta["working_copy_downscaled"] is False
        assert meta["opencv_input_shape"] == {"width": 768, "height": 1024}
        assert meta["original_input_shape"] == {"width": 768, "height": 1024}
        assert _file_sha256(path) == before
    finally:
        _cleanup_working_copy(temp_path)


def test_working_copy_does_not_overwrite_stored_source(tmp_path: Path) -> None:
    img = np.full((2400, 1350, 3), 80, dtype=np.uint8)
    path = tmp_path / "stored_source.jpg"
    cv2.imwrite(str(path), img)
    before = path.read_bytes()
    work_path, temp_path, meta = _prepare_working_copy(path)
    try:
        assert meta["working_copy_downscaled"] is True
        assert work_path.resolve() != path.resolve()
        assert path.read_bytes() == before
        work = cv2.imread(str(work_path))
        assert work is not None
        assert max(work.shape[0], work.shape[1]) == 1544
        stored = cv2.imread(str(path))
        assert stored is not None
        assert (stored.shape[0], stored.shape[1]) == (2400, 1350)
    finally:
        _cleanup_working_copy(temp_path)


def test_map_working_corners_to_original_scales_axis_aligned() -> None:
    working = np.zeros((772, 579, 3), dtype=np.uint8)
    original = np.zeros((1544, 1158, 3), dtype=np.uint8)
    corners = np.array([[10.0, 20.0], [200.0, 20.0], [200.0, 120.0], [10.0, 120.0]], dtype=np.float32)
    orig_oriented, mapped, meta = map_working_corners_to_original(
        corners,
        orientation="original",
        original_bgr=original,
        working_bgr=working,
    )
    assert orig_oriented.shape[:2] == (1544, 1158)
    assert mapped[0, 0] == pytest.approx(10.0 * (1158 / 579))
    assert mapped[0, 1] == pytest.approx(20.0 * (1544 / 772))
    assert mapped[2, 0] == pytest.approx(200.0 * (1158 / 579))
    assert meta["detection_source_dimensions"] == {"width": 579, "height": 772}
    assert meta["original_source_dimensions"] == {"width": 1158, "height": 1544}
    assert meta["coordinate_scale_factor"]["x"] == pytest.approx(1158 / 579)
    assert meta["coordinate_scale_factor"]["y"] == pytest.approx(1544 / 772)


def test_map_working_corners_to_original_respects_cw90() -> None:
    working = np.zeros((200, 100, 3), dtype=np.uint8)
    original = np.zeros((400, 200, 3), dtype=np.uint8)
    work_oriented_corners = np.array(
        [[10.0, 15.0], [80.0, 15.0], [80.0, 90.0], [10.0, 90.0]],
        dtype=np.float32,
    )
    orig_oriented, mapped, meta = map_working_corners_to_original(
        work_oriented_corners,
        orientation="cw90",
        original_bgr=original,
        working_bgr=working,
    )
    assert orig_oriented.shape[:2] == rotate_image(original, "cw90").shape[:2]
    assert mapped[0, 0] == pytest.approx(20.0)
    assert mapped[0, 1] == pytest.approx(30.0)
    assert meta["coordinate_scale_factor"]["x"] == pytest.approx(2.0)
    assert meta["coordinate_scale_factor"]["y"] == pytest.approx(2.0)


def test_confirmed_synthetic_card_output_is_1000x631(tmp_path: Path) -> None:
    path = tmp_path / "synthetic_card.jpg"
    cv2.imwrite(str(path), _synthetic_cool_card())
    outcome = run_applicant_dl_opencv(path)
    assert outcome.success is True
    assert outcome.jpeg_bytes
    arr = cv2.imdecode(np.frombuffer(outcome.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert arr is not None
    assert arr.shape[1] == TARGET_W == 1000
    assert arr.shape[0] == TARGET_H == 631
    assert outcome.debug.get("final_warp_source") == "original_pixels"
    assert outcome.debug.get("final_processed_dimensions") == {"width": 1000, "height": 631}
    assert outcome.debug.get("detection_source_dimensions") == {"width": 1400, "height": 900}
    assert outcome.debug.get("original_source_dimensions") == {"width": 1400, "height": 900}
    scale = outcome.debug.get("coordinate_scale_factor") or {}
    assert scale.get("x") == pytest.approx(1.0)
    assert scale.get("y") == pytest.approx(1.0)


@pytest.mark.skipif(_private_img6446() is None, reason=_PRIVATE_SKIP)
def test_private_img6446_canny_working_scale_1544() -> None:
    """Operator battery — not a hermetic CI gate. Requires private fixture."""
    src = _private_img6446()
    assert src is not None
    _work, temp_path, meta = _prepare_working_copy(src)
    try:
        shape = meta["opencv_input_shape"]
        orig = meta["original_input_shape"]
        assert orig["height"] == 2400
        assert orig["width"] == 1350
        assert shape["height"] == 1544
        assert 860 <= shape["width"] <= 880
        assert meta["working_copy_downscaled"] is True
    finally:
        _cleanup_working_copy(temp_path)

    outcome = run_applicant_dl_opencv(src)
    assert outcome.success is True
    assert outcome.debug.get("rough_locator_used") == "CANNY"
    assert outcome.debug.get("opencv_input_shape", {}).get("height") == 1544
    assert outcome.debug.get("final_warp_source") == "original_pixels"
    assert outcome.debug.get("detection_source_dimensions", {}).get("height") == 1544
    assert outcome.debug.get("original_source_dimensions") == {"width": 1350, "height": 2400}
    assert outcome.jpeg_bytes
    arr = cv2.imdecode(np.frombuffer(outcome.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert arr is not None
    assert arr.shape[1] == TARGET_W
    assert arr.shape[0] == TARGET_H
    assert outcome.debug.get("final_processed_dimensions") == {"width": TARGET_W, "height": TARGET_H}


@pytest.mark.skipif(_private_img6446() is None, reason=_PRIVATE_SKIP)
def test_private_img6446_processed_back_pdf417_fields(tmp_path: Path) -> None:
    """Operator battery — not a hermetic CI gate. Requires private fixture."""
    src = _private_img6446()
    assert src is not None
    outcome = run_applicant_dl_opencv(src)
    assert outcome.success is True
    assert outcome.jpeg_bytes
    out = tmp_path / "processed.jpg"
    out.write_bytes(outcome.jpeg_bytes)
    from app.services.dl_pdf417 import (
        aamva_intake_from_pdf417_text,
        decode_pdf417_barcode_with_trace,
        meaningful_license_field_count,
    )

    text, _meta = decode_pdf417_barcode_with_trace(out, mode="applicant_two_phase")
    assert text
    fields = meaningful_license_field_count(aamva_intake_from_pdf417_text(text))
    assert fields >= 15
    assert outcome.debug.get("final_warp_source") == "original_pixels"


def _decode_processed_fields(jpeg_bytes: bytes, tmp_path: Path) -> tuple[int, str | None]:
    from app.services.dl_pdf417 import (
        aamva_intake_from_pdf417_text,
        decode_pdf417_barcode_with_trace,
        meaningful_license_field_count,
    )

    out = tmp_path / "processed.jpg"
    out.write_bytes(jpeg_bytes)
    text, _meta = decode_pdf417_barcode_with_trace(out, mode="applicant_two_phase")
    if not text:
        return 0, None
    return meaningful_license_field_count(aamva_intake_from_pdf417_text(text)), text


@pytest.mark.skipif(not _LIVE_0084.is_file(), reason="live 1800x2400 IMG_0084 original not on host")
def test_live_img0084_original_pixel_warp_pdf417_succeeds(tmp_path: Path) -> None:
    outcome = run_applicant_dl_opencv(_LIVE_0084)
    assert outcome.success is True
    assert outcome.jpeg_bytes
    assert outcome.debug.get("final_warp_source") == "original_pixels"
    assert outcome.debug.get("original_source_dimensions") == {"width": 1800, "height": 2400}
    assert outcome.debug.get("detection_source_dimensions", {}).get("height") == 1544
    scale = outcome.debug.get("coordinate_scale_factor") or {}
    assert scale.get("x") == pytest.approx(1800 / 1158, rel=1e-4)
    assert scale.get("y") == pytest.approx(2400 / 1544, rel=1e-4)
    assert outcome.debug.get("final_processed_dimensions") == {"width": 1000, "height": 631}
    assert hashlib.sha256(outcome.jpeg_bytes).hexdigest() != _OLD_0084_WORKING_COPY_WARP_SHA
    arr = cv2.imdecode(np.frombuffer(outcome.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert arr is not None
    assert arr.shape[:2] == (TARGET_H, TARGET_W)
    fields, text = _decode_processed_fields(outcome.jpeg_bytes, tmp_path)
    assert text
    assert fields >= 15
    from app.services.dl_pdf417 import aamva_intake_from_pdf417_text

    payload = aamva_intake_from_pdf417_text(text)
    assert payload.get("sex") == "M"


@pytest.mark.skipif(not _LIVE_6446.is_file(), reason="live IMG_6446 original not on host")
def test_live_img6446_original_pixel_warp_pdf417_succeeds(tmp_path: Path) -> None:
    outcome = run_applicant_dl_opencv(_LIVE_6446)
    assert outcome.success is True
    assert outcome.jpeg_bytes
    assert outcome.debug.get("final_warp_source") == "original_pixels"
    assert outcome.debug.get("rough_locator_used") == "CANNY"
    assert outcome.debug.get("final_processed_dimensions") == {"width": 1000, "height": 631}
    fields, text = _decode_processed_fields(outcome.jpeg_bytes, tmp_path)
    assert text
    assert fields >= 15
    from app.services.dl_pdf417 import aamva_intake_from_pdf417_text

    payload = aamva_intake_from_pdf417_text(text)
    assert payload.get("sex") == "F"
