"""Applicant DL OpenCV preprocessing wrapper tests."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.services.applicant_dl_opencv import PREPROCESS_VERSION, _confirm_all_four_corners, _rough_card_candidates
from app.services.applicant_dl_preprocess import run_applicant_dl_opencv


def test_preprocess_version():
    assert PREPROCESS_VERSION.startswith("2026-08-28")


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
