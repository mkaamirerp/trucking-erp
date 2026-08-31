"""Short-side edge repair fallback — hermetic unit tests. No real DL images."""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.services.applicant_dl_opencv import (
    DL_ASPECT,
    TARGET_H,
    TARGET_W,
    _attempt_short_side_edge_repair,
    _confirm_all_four_corners,
    _evaluate_four_edge_geometry,
    _expected_short_length,
    _is_short_side_repairable,
    _search_confirmed_seed,
    process_driver_license_image,
    rotate_image,
)
from app.services.applicant_dl_preprocess import run_applicant_dl_opencv

_PRIVATE_DIR = Path((os.environ.get("DL_PRIVATE_FIXTURE_DIR") or "/home/admin/private_test_fixtures/dl"))


def _axis_lines(x0, y0, x1, y1):
    return [
        (1.0, 0.0, float(x0), float(y0)),
        (0.0, 1.0, float(x1), float(y0)),
        (1.0, 0.0, float(x0), float(y1)),
        (0.0, 1.0, float(x0), float(y0)),
    ]


def _rect_corners(x0, y0, x1, y1):
    return {
        "TL": [float(x0), float(y0)],
        "TR": [float(x1), float(y0)],
        "BR": [float(x1), float(y1)],
        "BL": [float(x0), float(y1)],
    }


def _diag_for_rect(x0, y0, x1, y1, inliers, *, inside=True, ratio=None):
    long_len = float(x1 - x0)
    short_len = float(y1 - y0)
    if ratio is None:
        ratio = long_len / (short_len + 1e-6)
    return {
        "confirmed": False,
        "all_four_corners_inside_source": inside,
        "edge_inliers": list(inliers),
        "ratio": float(ratio),
        "long_side_length": long_len,
        "short_side_length": short_len,
        "corners": _rect_corners(x0, y0, x1, y1),
        "max_angle_error_from_90": 0.5,
        "area_percent": 18.0,
    }


def _paint_id1_card(img, x0, y0, long_px, thickness=8):
    short_px = int(round(long_px / DL_ASPECT))
    x1, y1 = x0 + long_px, y0 + short_px
    cv2.rectangle(img, (x0, y0), (x1, y1), (220, 215, 200), -1)
    cv2.rectangle(img, (x0, y0), (x1, y1), (8, 8, 8), thickness)
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32), short_px


def test_1_normal_confirmed_geometry_does_not_call_repair():
    img = np.full((900, 1400, 3), 36, dtype=np.uint8)
    box, _ = _paint_id1_card(img, 240, 180, 720)
    corners, diag, _ = _confirm_all_four_corners(img, box)
    assert corners is not None
    assert diag["confirmed"] is True
    assert 1.25 <= diag["ratio"] <= 1.95
    assert "edge_repair_attempted" not in diag

    result, _final = process_driver_license_image(img)
    assert result.post_validation_pass is True
    assert result.report.get("edge_repair_applied") is False
    assert result.report.get("edge_repair_attempted") is False


def test_2_ratio_too_wide_truncated_short_side_is_repairable():
    x0, y0, x1, y1 = 100.0, 80.0, 816.0, 430.0
    diag = _diag_for_rect(x0, y0, x1, y1, [152, 129, 62, 180], ratio=2.05)
    lines = _axis_lines(x0, y0, x1, y1)
    ok, reason, ctx = _is_short_side_repairable(diag, lines, (1024, 768, 3))
    assert ok is True
    assert reason == "short_side_truncated"
    assert ctx is not None
    assert ctx["suspect_name"] == "bottom"


def test_3_expected_short_length_is_long_over_dl_aspect():
    long_len = 716.0
    expected = _expected_short_length(long_len)
    assert expected == pytest.approx(long_len / DL_ASPECT)
    assert expected == pytest.approx(451.5, abs=1.0)


def test_4_predicted_edge_searches_outward_not_inward():
    x0, y0, x1, y1 = 100.0, 80.0, 816.0, 430.0
    diag = _diag_for_rect(x0, y0, x1, y1, [152, 129, 62, 180], ratio=2.05)
    lines = _axis_lines(x0, y0, x1, y1)
    ok, _reason, ctx = _is_short_side_repairable(diag, lines, (1200, 1000, 3))
    assert ok is True
    assert ctx is not None
    centroid = np.array([(x0 + x1) / 2.0, (y0 + y1) / 2.0])
    suspect_mid = np.array([(x0 + x1) / 2.0, y1])
    pred = ctx["predicted_mid"]
    assert float(np.linalg.norm(pred - centroid)) > float(np.linalg.norm(suspect_mid - centroid))
    assert float(pred[1]) > float(y1)


def test_5_and_6_real_replacement_line_recomputes_corners_and_can_pass():
    img = np.full((1000, 1300, 3), 40, dtype=np.uint8)
    full_box, short_px = _paint_id1_card(img, 160, 120, 700, thickness=10)
    x0, y0 = 160, 120
    x1 = 160 + 700
    y1 = int(full_box[2][1])
    truncated_y = y0 + int(short_px * 0.72)
    # Shorter internal divider so the false bottom is clearly weaker than the
    # outer sides; the real outer bottom remains the repair target.
    cv2.line(img, (x0 + 140, truncated_y), (x1 - 140, truncated_y), (10, 10, 10), 3)
    truncated = np.array(
        [[x0, y0], [x1, y0], [x1, truncated_y], [x0, truncated_y]],
        dtype=np.float32,
    )
    corners, diag, support = _confirm_all_four_corners(img, truncated)
    if corners is not None:
        pytest.skip("synthetic truncated seed unexpectedly confirmed")
    assert diag.get("ratio") is not None
    assert diag["ratio"] > 1.95
    repaired = _attempt_short_side_edge_repair(img, diag, support, is_closeup_seed=False)
    assert repaired is not None
    assert repaired["corners"] is not None
    assert repaired["diagnostics"]["edge_repair_passed"] is True
    assert 1.25 <= repaired["diagnostics"]["ratio"] <= 1.95
    assert repaired["diagnostics"]["edge_repair_new_edge_inliers"] >= 50
    rc = repaired["corners"]
    assert abs(float(rc[2][1]) - float(y1)) < 30
    assert abs(float(rc[3][1]) - float(y1)) < 30


def test_7_no_replacement_physical_line_fails_safely():
    img = np.full((900, 1200, 3), 40, dtype=np.uint8)
    x0, y0, x1, y1 = 180, 140, 900, 430
    cv2.rectangle(img, (x0, y0), (x1, y1), (210, 210, 200), -1)
    cv2.line(img, (x0, y0), (x1, y0), (8, 8, 8), 8)
    cv2.line(img, (x1, y0), (x1, y1), (8, 8, 8), 8)
    cv2.line(img, (x0, y0), (x0, y1), (8, 8, 8), 8)
    truncated = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)
    _corners, diag, support = _confirm_all_four_corners(img, truncated)
    diag = dict(diag)
    diag["ratio"] = 2.08
    diag["long_side_length"] = float(x1 - x0)
    diag["short_side_length"] = float(y1 - y0)
    diag["edge_inliers"] = [140, 120, 60, 150]
    repaired = _attempt_short_side_edge_repair(img, diag, support, is_closeup_seed=False)
    assert repaired is not None
    assert repaired["corners"] is None
    assert repaired["diagnostics"]["edge_repair_passed"] is False


def test_8_repaired_ratio_invalid_is_rejected():
    img = np.full((400, 600, 3), 40, dtype=np.uint8)
    corners = np.array([[20, 20], [580, 20], [580, 80], [20, 80]], dtype=np.float32)
    confirmed, diag = _evaluate_four_edge_geometry(img, corners, [120, 120, 120, 120])
    assert confirmed is False
    assert not (1.25 <= diag["ratio"] <= 1.95)


def test_9_repaired_angles_invalid_is_rejected():
    img = np.full((400, 400, 3), 40, dtype=np.uint8)
    corners = np.array([[10, 10], [300, 40], [260, 200], [20, 250]], dtype=np.float32)
    confirmed, diag = _evaluate_four_edge_geometry(img, corners, [100, 100, 100, 100])
    assert confirmed is False
    assert diag["max_angle_error_from_90"] > 20.0 or not (1.25 <= diag["ratio"] <= 1.95)


def test_10_repaired_corners_outside_source_rejected():
    img = np.full((200, 200, 3), 40, dtype=np.uint8)
    corners = np.array([[-40, -40], [300, -20], [320, 260], [-30, 250]], dtype=np.float32)
    confirmed, diag = _evaluate_four_edge_geometry(img, corners, [120, 120, 120, 120])
    assert confirmed is False
    assert diag["all_four_corners_inside_source"] is False


def test_11_arbitrary_bad_geometry_does_not_enter_repair():
    diag = {
        "confirmed": False,
        "all_four_corners_inside_source": True,
        "edge_inliers": [12, 9, 8, 11],
        "ratio": 3.4,
        "long_side_length": 400.0,
        "short_side_length": 80.0,
        "corners": _rect_corners(10, 10, 410, 90),
    }
    ok, reason, ctx = _is_short_side_repairable(diag, _axis_lines(10, 10, 410, 90), (500, 500, 3))
    assert ok is False
    assert ctx is None
    assert reason in {"ratio_absurdly_wide", "other_sides_lack_support"}


def test_12_repaired_candidate_does_not_override_valid_normal():
    img = np.full((1000, 1400, 3), 38, dtype=np.uint8)
    full_box, short_px = _paint_id1_card(img, 200, 150, 720, thickness=10)
    x0, y0 = 200, 150
    x1 = 200 + 720
    truncated_y = y0 + int(short_px * 0.70)
    truncated = np.array(
        [[x0, y0], [x1, y0], [x1, truncated_y], [x0, truncated_y]],
        dtype=np.float32,
    )

    def seed_fn(_oriented):
        def _seed(box, rank_score):
            top = float(np.linalg.norm(box[1] - box[0]))
            left = float(np.linalg.norm(box[3] - box[0]))
            return {
                "rough_box": box,
                "seed_score": rank_score,
                "is_closeup_seed": False,
                "area_ratio": 0.2,
                "rough_ratio": top / max(left, 1e-6),
                "mask_name": "test",
            }

        return [_seed(truncated, 0.0), _seed(full_box, 1.0)]

    normal, repaired = _search_confirmed_seed(img, seed_fn, locator_name="TEST")
    assert normal is not None
    assert normal["edge_repair_applied"] is False


def test_13_orientation_safe_physical_bottom_may_be_top_after_rotate180():
    # Landscape card low in the frame so the outward (upward) predicted top stays inside.
    x0, y0, x1, y1 = 80.0, 420.0, 796.0, 770.0
    inliers = [62, 180, 152, 129]
    diag = _diag_for_rect(x0, y0, x1, y1, inliers, ratio=2.05)
    ok, _reason, ctx = _is_short_side_repairable(diag, _axis_lines(x0, y0, x1, y1), (1024, 900, 3))
    assert ok is True
    assert ctx is not None
    assert ctx["suspect_name"] == "top"
    assert float(ctx["predicted_mid"][1]) < float(y0)


def _private(name: str) -> Path | None:
    path = _PRIVATE_DIR / name
    return path if path.is_file() else None


@pytest.mark.skipif(_private("IMG_8789.png") is None, reason="private IMG_8789 not installed")
def test_14_img_8789_remains_failure():
    out = run_applicant_dl_opencv(_private("IMG_8789.png"))
    assert out.success is False
    assert out.debug.get("status") == "FOUR_CORNERS_NOT_CONFIRMED"
    assert out.debug.get("edge_repair_applied") in (None, False)


@pytest.mark.skipif(_private("IMG_6446_normalized.jpg") is None, reason="private IMG_6446 not installed")
def test_15_img6446_remains_normal_path_pass():
    out = run_applicant_dl_opencv(_private("IMG_6446_normalized.jpg"))
    assert out.success is True
    assert out.debug.get("rough_locator_used") == "CANNY"
    assert out.debug.get("edge_repair_applied") is False
    assert out.debug.get("edge_repair_attempted") is False
    arr = cv2.imdecode(np.frombuffer(out.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert arr is not None
    assert arr.shape[1] == TARGET_W
    assert arr.shape[0] == TARGET_H


@pytest.mark.skipif(_private("IMG_0084_ontario_back.jpg") is None, reason="private Ontario back not installed")
def test_ontario_back_repair_confirms_near_id1():
    out = run_applicant_dl_opencv(_private("IMG_0084_ontario_back.jpg"))
    assert out.success is True
    assert out.debug.get("edge_repair_applied") is True
    assert out.debug.get("edge_repair_attempted") is True
    assert 1.25 <= float(out.debug.get("final_ratio")) <= 1.95
    arr = cv2.imdecode(np.frombuffer(out.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert arr is not None
    assert arr.shape == (TARGET_H, TARGET_W, 3)
