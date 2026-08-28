"""
TruckERP Driver ID Preprocessor
Geometry-first, rounded-corner-safe line-intersection pipeline.

Purpose:
- Existing OCR is assumed to work.
- This module prepares driver-license / ID-card photos by finding the card,
  validating geometry against an ID-1 reference card, applying perspective
  correction only when safe, and falling back to safe crop/orientation when not.

Core rule:
    candidate corners -> measure -> refine loop -> perspective warp if valid
    fallback safely if geometry is unsafe

Why line intersections:
- DL/ID cards have rounded physical corners.
- The visible rounded arc is NOT the true geometric rectangle corner.
- True perspective corners are estimated by fitting four straight edge lines
  while ignoring rounded corner zones, then intersecting those lines.

Target reference:
- ID-1 card ratio = 85.60 / 53.98 ~= 1.586
- Default normalized output = 1000 x 630

Run:
    python preprocess_driver_id_line_intersection.py input.jpg output.jpg --debug-dir debug_out
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

DL_ASPECT = 85.60 / 53.98
TARGET_W = 1000
TARGET_H = int(round(TARGET_W / DL_ASPECT))


@dataclass
class GeometryMeasurement:
    top_width: float
    bottom_width: float
    left_height: float
    right_height: float
    diagonal_1: float
    diagonal_2: float
    average_width: float
    average_height: float
    detected_ratio: float
    expected_ratio: float
    ratio_error_percent: float
    top_bottom_delta_percent: float
    left_right_delta_percent: float
    diagonal_delta_percent: float
    corner_angles: List[float]
    max_angle_error_from_90: float
    area_percent: float
    touches_border: bool
    border_touch_count: int
    valid_for_perspective: bool
    reject_reasons: List[str]


@dataclass
class CandidateResult:
    orientation_name: str
    mask_name: str
    component_index: int
    score: float
    decision: str
    measurement: Optional[GeometryMeasurement]
    corners: Optional[List[List[float]]]
    fallback_rect: Optional[List[int]]
    refinement_attempts: List[Dict]


def rotate_image(image: np.ndarray, orientation: str) -> np.ndarray:
    if orientation == "original":
        return image.copy()
    if orientation == "cw90":
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if orientation == "ccw90":
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if orientation == "rotate180":
        return cv2.rotate(image, cv2.ROTATE_180)
    raise ValueError(f"Unknown orientation: {orientation}")


def orientation_candidates(image: np.ndarray) -> Dict[str, np.ndarray]:
    return {
        "original": rotate_image(image, "original"),
        "cw90": rotate_image(image, "cw90"),
        "ccw90": rotate_image(image, "ccw90"),
        "rotate180": rotate_image(image, "rotate180"),
    }


def clean_mask(mask: np.ndarray, kernel_size: int = 5, close_iter: int = 1, open_iter: int = 1) -> np.ndarray:
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    out = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=close_iter)
    out = cv2.morphologyEx(out, cv2.MORPH_OPEN, kernel, iterations=open_iter)
    return out


def build_candidate_masks(image_bgr: np.ndarray) -> Dict[str, np.ndarray]:
    """
    Multiple masks are intentional. Different backgrounds fail different signals.
    Preferred mask for Ontario-style DLs is blue/green security printing.
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    # Ontario DL blue/green security pattern. Avoids red/black background better than brightness.
    blue_green = cv2.inRange(hsv, np.array([35, 22, 35]), np.array([125, 255, 255]))
    blue_green = clean_mask(blue_green, 5, 1, 1)

    # Saturation Otsu fallback. Good when DL is colorful and background is neutral.
    _, sat_otsu = cv2.threshold(s, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    sat_otsu = clean_mask(sat_otsu, 5, 1, 1)

    # Bright fallback catches pale cards but can include glare; lower priority.
    bright = cv2.inRange(v, 95, 255)
    bright = clean_mask(bright, 7, 1, 1)

    # Edge fallback for low-saturation scans.
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray_blur, 50, 150)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)
    edges = clean_mask(edges, 7, 1, 1)

    return {
        "blue_green_component": blue_green,
        "saturation_otsu": sat_otsu,
        "bright_fallback": bright,
        "edge_fallback": edges,
    }


def connected_components_by_area(mask: np.ndarray, min_area_ratio: float = 0.006) -> List[np.ndarray]:
    h, w = mask.shape[:2]
    image_area = h * w
    num, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    comps: List[np.ndarray] = []
    for label in range(1, num):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < image_area * min_area_ratio:
            continue
        comp = np.zeros_like(mask)
        comp[labels == label] = 255
        comps.append(comp)
    comps.sort(key=lambda c: int(cv2.countNonZero(c)), reverse=True)
    return comps


def largest_contour(component_mask: np.ndarray) -> Optional[np.ndarray]:
    contours, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def order_corners(pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1).reshape(-1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def fit_line(points: np.ndarray) -> Tuple[float, float, float, float]:
    line = cv2.fitLine(points.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01)
    return tuple(float(v) for v in line.reshape(-1))  # vx, vy, x0, y0


def intersect_lines(line1: Tuple[float, float, float, float], line2: Tuple[float, float, float, float]) -> Optional[np.ndarray]:
    vx1, vy1, x1, y1 = line1
    vx2, vy2, x2, y2 = line2
    a = np.array([[vx1, -vx2], [vy1, -vy2]], dtype=np.float32)
    b = np.array([x2 - x1, y2 - y1], dtype=np.float32)
    det = float(np.linalg.det(a))
    if abs(det) < 1e-6:
        return None
    t, _u = np.linalg.solve(a, b)
    return np.array([x1 + t * vx1, y1 + t * vy1], dtype=np.float32)


def line_intersection_corners_for_rounded_card(
    component_mask: np.ndarray,
    low_pct: float = 3.0,
    high_pct: float = 97.0,
    band_ratio: float = 0.055,
    corner_ignore_ratio: float = 0.16,
) -> Optional[np.ndarray]:
    """
    Rounded-corner-safe corner logic.

    minAreaRect is only used as a rough coordinate frame. It is NOT the final truth.
    Final corners are created by:
      1. project contour points into rough card coordinates
      2. fit top/bottom/left/right lines from straight edge zones
      3. ignore rounded corner zones while fitting each line
      4. intersect the four lines to synthesize true rectangle corners
    """
    contour = largest_contour(component_mask)
    if contour is None or len(contour) < 50:
        return None

    pts = contour.reshape(-1, 2).astype(np.float32)
    rough_rect = cv2.minAreaRect(pts)
    rough_box = order_corners(cv2.boxPoints(rough_rect).astype(np.float32))

    x_axis = rough_box[1] - rough_box[0]
    y_axis = rough_box[3] - rough_box[0]
    x_axis = x_axis / (np.linalg.norm(x_axis) + 1e-6)
    y_axis = y_axis / (np.linalg.norm(y_axis) + 1e-6)
    origin = rough_box[0]

    rel = pts - origin
    x_proj = rel @ x_axis
    y_proj = rel @ y_axis

    x_min, x_max = np.percentile(x_proj, [low_pct, high_pct])
    y_min, y_max = np.percentile(y_proj, [low_pct, high_pct])
    x_span = max(1.0, x_max - x_min)
    y_span = max(1.0, y_max - y_min)
    x_band = max(6.0, x_span * band_ratio)
    y_band = max(6.0, y_span * band_ratio)
    x_mid_lo = x_min + x_span * corner_ignore_ratio
    x_mid_hi = x_max - x_span * corner_ignore_ratio
    y_mid_lo = y_min + y_span * corner_ignore_ratio
    y_mid_hi = y_max - y_span * corner_ignore_ratio

    # Edge points: use only the straight middle portions of each edge.
    # This avoids treating rounded arc endpoints as real corners.
    top_pts = pts[(y_proj <= y_min + y_band) & (x_proj >= x_mid_lo) & (x_proj <= x_mid_hi)]
    bottom_pts = pts[(y_proj >= y_max - y_band) & (x_proj >= x_mid_lo) & (x_proj <= x_mid_hi)]
    left_pts = pts[(x_proj <= x_min + x_band) & (y_proj >= y_mid_lo) & (y_proj <= y_mid_hi)]
    right_pts = pts[(x_proj >= x_max - x_band) & (y_proj >= y_mid_lo) & (y_proj <= y_mid_hi)]

    if min(len(top_pts), len(bottom_pts), len(left_pts), len(right_pts)) < 8:
        return None

    top = fit_line(top_pts)
    bottom = fit_line(bottom_pts)
    left = fit_line(left_pts)
    right = fit_line(right_pts)

    tl = intersect_lines(top, left)
    tr = intersect_lines(top, right)
    br = intersect_lines(bottom, right)
    bl = intersect_lines(bottom, left)
    if any(p is None for p in [tl, tr, br, bl]):
        return None
    return order_corners(np.vstack([tl, tr, br, bl]).astype(np.float32))


def angle_at(p_prev: np.ndarray, p: np.ndarray, p_next: np.ndarray) -> float:
    v1 = p_prev - p
    v2 = p_next - p
    cos_ang = float(np.dot(v1, v2) / ((np.linalg.norm(v1) * np.linalg.norm(v2)) + 1e-6))
    return float(np.degrees(np.arccos(np.clip(cos_ang, -1.0, 1.0))))


def measure_geometry(corners: np.ndarray, image_shape: Tuple[int, int, int], expected_ratio: float = DL_ASPECT) -> GeometryMeasurement:
    corners = order_corners(corners).astype(np.float32)
    h, w = image_shape[:2]
    tl, tr, br, bl = corners

    top = float(np.linalg.norm(tr - tl))
    bottom = float(np.linalg.norm(br - bl))
    left = float(np.linalg.norm(bl - tl))
    right = float(np.linalg.norm(br - tr))
    d1 = float(np.linalg.norm(br - tl))
    d2 = float(np.linalg.norm(bl - tr))
    avg_w = (top + bottom) / 2.0
    avg_h = (left + right) / 2.0
    ratio = avg_w / (avg_h + 1e-6)

    def pct_delta(a: float, b: float) -> float:
        return abs(a - b) / max(a, b, 1e-6) * 100.0

    angles = [
        angle_at(bl, tl, tr),
        angle_at(tl, tr, br),
        angle_at(tr, br, bl),
        angle_at(br, bl, tl),
    ]

    border_margin = max(6, int(min(h, w) * 0.008))
    touch_count = 0
    for x, y in corners:
        if x <= border_margin or x >= w - border_margin or y <= border_margin or y >= h - border_margin:
            touch_count += 1

    area = abs(cv2.contourArea(corners.astype(np.float32)))
    area_percent = area / float(h * w) * 100.0

    ratio_error = abs(ratio - expected_ratio) / expected_ratio * 100.0
    tb_delta = pct_delta(top, bottom)
    lr_delta = pct_delta(left, right)
    diag_delta = pct_delta(d1, d2)
    max_angle_error = max(abs(a - 90.0) for a in angles)

    # Two-stage geometry gate.
    #
    # A strict gate is best for normal photos, but angled-but-good DL photos can have
    # one side-height delta around 10-15% while the other metrics are strong. Do not
    # reject those just because of one mild perspective signal. Use hard rejects for
    # truly unsafe geometry and allow a controlled permissive pass when the rest of
    # the reference-card measurements are strong.
    hard_reject: List[str] = []
    if ratio_error > 6.0:
        hard_reject.append("ratio_error_gt_6_percent")
    if max_angle_error > 12.0:
        hard_reject.append("corner_angle_error_gt_12_degrees")
    if tb_delta > 12.0:
        hard_reject.append("top_bottom_delta_gt_12_percent")
    if lr_delta > 18.0:
        hard_reject.append("left_right_delta_gt_18_percent")
    if diag_delta > 14.0:
        hard_reject.append("diagonal_delta_gt_14_percent")
    if area_percent < 8.0:
        hard_reject.append("card_area_too_small")
    if area_percent > 95.0:
        hard_reject.append("card_area_too_large")
    if touch_count > 0:
        hard_reject.append("border_touch_risk")

    strict_ok = (
        ratio_error <= 5.0
        and max_angle_error <= 10.0
        and tb_delta <= 8.0
        and lr_delta <= 10.0
        and diag_delta <= 10.0
        and area_percent >= 8.0
        and area_percent <= 95.0
        and touch_count == 0
    )
    permissive_ok = (
        not hard_reject
        and ratio_error <= 4.0
        and max_angle_error <= 6.0
        and tb_delta <= 4.0
        and lr_delta <= 15.0
        and diag_delta <= 10.0
    )

    reject: List[str] = []
    if not (strict_ok or permissive_ok):
        reject.extend(hard_reject)
        if ratio_error > 5.0:
            reject.append("ratio_error_gt_5_percent")
        if max_angle_error > 10.0:
            reject.append("corner_angle_error_gt_10_degrees")
        if tb_delta > 8.0:
            reject.append("top_bottom_delta_gt_8_percent")
        if lr_delta > 10.0:
            reject.append("left_right_delta_gt_10_percent")
        if diag_delta > 10.0:
            reject.append("diagonal_delta_gt_10_percent")
        # De-duplicate while preserving order.
        reject = list(dict.fromkeys(reject))

    return GeometryMeasurement(
        top_width=top,
        bottom_width=bottom,
        left_height=left,
        right_height=right,
        diagonal_1=d1,
        diagonal_2=d2,
        average_width=avg_w,
        average_height=avg_h,
        detected_ratio=ratio,
        expected_ratio=expected_ratio,
        ratio_error_percent=ratio_error,
        top_bottom_delta_percent=tb_delta,
        left_right_delta_percent=lr_delta,
        diagonal_delta_percent=diag_delta,
        corner_angles=[float(a) for a in angles],
        max_angle_error_from_90=float(max_angle_error),
        area_percent=float(area_percent),
        touches_border=touch_count > 0,
        border_touch_count=touch_count,
        valid_for_perspective=len(reject) == 0,
        reject_reasons=reject,
    )


def geometry_error_score(m: GeometryMeasurement) -> float:
    score = 0.0
    score += m.ratio_error_percent * 3.0
    score += m.max_angle_error_from_90 * 1.5
    score += m.top_bottom_delta_percent * 1.0
    score += m.left_right_delta_percent * 1.0
    score += m.diagonal_delta_percent * 0.4
    if m.touches_border:
        score += 35.0
    if m.area_percent < 8.0 or m.area_percent > 95.0:
        score += 40.0
    return float(score)


def refine_corners_iterative(component_mask: np.ndarray, image_shape: Tuple[int, int, int], max_iterations: int = 12) -> Tuple[Optional[np.ndarray], Optional[GeometryMeasurement], List[Dict]]:
    """
    Loop over edge-line sampling parameters. This is the reference validation loop.
    We keep the rounded-corner line-intersection method, then adjust how edge points
    are selected until the measured corners match the DL reference or we choose the
    least-bad safe candidate.
    """
    attempts: List[Dict] = []
    best_corners: Optional[np.ndarray] = None
    best_measurement: Optional[GeometryMeasurement] = None
    best_error = float("inf")

    param_grid: List[Tuple[float, float, float, float]] = []
    for low, high in [(2, 98), (3, 97), (4, 96), (5, 95), (6, 94), (8, 92)]:
        for band in [0.04, 0.05, 0.06, 0.075, 0.09, 0.11, 0.13]:
            for ignore in [0.10, 0.13, 0.16, 0.20, 0.24]:
                param_grid.append((float(low), float(high), float(band), float(ignore)))

    for iteration, (low, high, band, ignore) in enumerate(param_grid[:max_iterations]):
        corners = line_intersection_corners_for_rounded_card(component_mask, low, high, band, ignore)
        if corners is None:
            attempts.append({
                "iteration": iteration,
                "low_pct": low,
                "high_pct": high,
                "band_ratio": band,
                "corner_ignore_ratio": ignore,
                "status": "no_corners",
            })
            continue

        measurement = measure_geometry(corners, image_shape)
        err = geometry_error_score(measurement)
        attempts.append({
            "iteration": iteration,
            "low_pct": low,
            "high_pct": high,
            "band_ratio": band,
            "corner_ignore_ratio": ignore,
            "status": "measured",
            "error_score": err,
            "valid_for_perspective": measurement.valid_for_perspective,
            "measurement": asdict(measurement),
        })

        if err < best_error:
            best_error = err
            best_corners = corners
            best_measurement = measurement

        if measurement.valid_for_perspective:
            break

    return best_corners, best_measurement, attempts


def perspective_warp_to_reference(image_bgr: np.ndarray, corners: np.ndarray, target_w: int = TARGET_W, target_h: int = TARGET_H) -> np.ndarray:
    src = order_corners(corners).astype(np.float32)
    dst = np.array([[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image_bgr, matrix, (target_w, target_h))


def ensure_landscape_upright_for_dl(image_bgr: np.ndarray) -> np.ndarray:
    out = image_bgr.copy()
    if out.shape[0] > out.shape[1]:
        out = cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE)

    # Ontario DL has the portrait/photo block on the left. Use a conservative dark-mass check.
    gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    y0, y1 = int(h * 0.18), int(h * 0.82)
    left_roi = gray[y0:y1, int(w * 0.05):int(w * 0.45)]
    right_roi = gray[y0:y1, int(w * 0.55):int(w * 0.95)]
    left_dark = float(np.mean(left_roi < 115)) if left_roi.size else 0.0
    right_dark = float(np.mean(right_roi < 115)) if right_roi.size else 0.0
    if right_dark > left_dark * 1.15 and right_dark > 0.03:
        out = cv2.rotate(out, cv2.ROTATE_180)
    return out


def safe_crop_from_component(image_bgr: np.ndarray, component_mask: np.ndarray, pad_ratio: float = 0.025) -> Tuple[np.ndarray, List[int]]:
    contour = largest_contour(component_mask)
    if contour is None:
        return image_bgr.copy(), [0, 0, image_bgr.shape[1], image_bgr.shape[0]]
    x, y, w, h = cv2.boundingRect(contour)
    ih, iw = image_bgr.shape[:2]
    pad = int(max(iw, ih) * pad_ratio)
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(iw, x + w + pad)
    y1 = min(ih, y + h + pad)
    return image_bgr[y0:y1, x0:x1].copy(), [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]


def score_candidate(measurement: Optional[GeometryMeasurement], component_mask: np.ndarray, mask_priority: float, component_index: int) -> float:
    area_percent = cv2.countNonZero(component_mask) / float(component_mask.shape[0] * component_mask.shape[1]) * 100.0
    if measurement is None:
        return -500.0 + area_percent + mask_priority - component_index * 4.0
    score = 100.0
    score -= measurement.ratio_error_percent * 4.0
    score -= measurement.max_angle_error_from_90 * 2.0
    score -= measurement.top_bottom_delta_percent * 1.0
    score -= measurement.left_right_delta_percent * 1.0
    score -= measurement.diagonal_delta_percent * 0.4
    score += min(25.0, measurement.area_percent * 0.45)
    score += mask_priority
    if measurement.valid_for_perspective:
        score += 75.0
    if measurement.touches_border:
        score -= 35.0
    score -= component_index * 4.0
    return float(score)


def choose_best_candidate(image_bgr: np.ndarray, debug_dir: Optional[Path] = None) -> Tuple[CandidateResult, np.ndarray]:
    all_results: List[Tuple[CandidateResult, np.ndarray, Optional[np.ndarray], np.ndarray]] = []
    mask_priorities = {
        "blue_green_component": 14.0,
        "saturation_otsu": 7.0,
        "bright_fallback": 0.0,
        "edge_fallback": -7.0,
    }

    for orientation_name, oriented in orientation_candidates(image_bgr).items():
        masks = build_candidate_masks(oriented)
        for mask_name, mask in masks.items():
            comps = connected_components_by_area(mask, min_area_ratio=0.006)[:1]
            for idx, comp in enumerate(comps):
                corners, measurement, attempts = refine_corners_iterative(comp, oriented.shape)
                crop, rect = safe_crop_from_component(oriented, comp)
                score = score_candidate(measurement, comp, mask_priorities.get(mask_name, 0.0), idx)

                if measurement and measurement.valid_for_perspective:
                    decision = "accepted_perspective_first_warp_line_intersection"
                elif measurement:
                    decision = "rejected_perspective_safe_crop_orientation_only"
                else:
                    decision = "no_geometry_safe_crop_orientation_only"

                result = CandidateResult(
                    orientation_name=orientation_name,
                    mask_name=mask_name,
                    component_index=idx,
                    score=score,
                    decision=decision,
                    measurement=measurement,
                    corners=corners.tolist() if corners is not None else None,
                    fallback_rect=rect,
                    refinement_attempts=attempts,
                )
                all_results.append((result, oriented, corners, comp))

    if not all_results:
        fallback = CandidateResult(
            orientation_name="original",
            mask_name="none",
            component_index=0,
            score=-999.0,
            decision="original_fallback_no_candidate",
            measurement=None,
            corners=None,
            fallback_rect=[0, 0, image_bgr.shape[1], image_bgr.shape[0]],
            refinement_attempts=[],
        )
        return fallback, ensure_landscape_upright_for_dl(image_bgr)

    all_results.sort(key=lambda item: item[0].score, reverse=True)
    best, oriented, corners, comp = all_results[0]

    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        with open(debug_dir / "candidate_scores.json", "w", encoding="utf-8") as f:
            json.dump([asdict(item[0]) for item in all_results[:20]], f, indent=2)
        cv2.imwrite(str(debug_dir / "01_best_component_mask.jpg"), comp)
        debug = oriented.copy()
        if corners is not None:
            c = order_corners(corners).astype(int)
            labels = ["TL", "TR", "BR", "BL"]
            for i in range(4):
                p1 = tuple(c[i])
                p2 = tuple(c[(i + 1) % 4])
                cv2.line(debug, p1, p2, (0, 0, 255), 3)
                cv2.circle(debug, p1, 8, (0, 255, 0), -1)
                cv2.putText(debug, labels[i], (p1[0] + 8, p1[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
        cv2.imwrite(str(debug_dir / "02_best_corners_debug.jpg"), debug)

    if best.measurement and best.measurement.valid_for_perspective and corners is not None:
        final = perspective_warp_to_reference(oriented, corners)
        final = ensure_landscape_upright_for_dl(final)
        return best, final

    safe, _rect = safe_crop_from_component(oriented, comp)
    safe = ensure_landscape_upright_for_dl(safe)
    return best, safe


def preprocess_driver_id_image(input_path: str, output_path: str, debug_dir: Optional[str] = None) -> Dict:
    image = cv2.imread(input_path)
    if image is None:
        raise FileNotFoundError(f"Cannot load image: {input_path}")
    debug_path = Path(debug_dir) if debug_dir else None
    result, final = choose_best_candidate(image, debug_path)
    cv2.imwrite(output_path, final)

    payload = {
        "input_path": input_path,
        "output_path": output_path,
        "target_width": TARGET_W,
        "target_height": TARGET_H,
        "target_aspect": DL_ASPECT,
        "result": asdict(result),
        "final_shape": {"height": int(final.shape[0]), "width": int(final.shape[1])},
    }
    if debug_path:
        cv2.imwrite(str(debug_path / "03_final_selected.jpg"), final)
        with open(debug_path / "result.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess driver ID image using rounded-corner line-intersection geometry.")
    parser.add_argument("input", help="Input image path")
    parser.add_argument("output", help="Output image path")
    parser.add_argument("--debug-dir", default=None, help="Optional debug output folder")
    args = parser.parse_args()
    result = preprocess_driver_id_image(args.input, args.output, args.debug_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
