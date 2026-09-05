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
)
from app.services.applicant_dl_preprocess import (
    WORKING_COPY_MAX_SIDE,
    _prepare_working_copy,
    run_applicant_dl_opencv,
)

_PRIVATE_SKIP = "private DL regression fixture not installed"
_PRIVATE_FILENAME = "IMG_6446_normalized.jpg"


def _private_img6446() -> Path | None:
    raw = (os.environ.get("DL_PRIVATE_FIXTURE_DIR") or "").strip()
    if not raw:
        return None
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
    assert outcome.jpeg_bytes
    arr = cv2.imdecode(np.frombuffer(outcome.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert arr is not None
    assert arr.shape[1] == TARGET_W
    assert arr.shape[0] == TARGET_H


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
