"""
TruckERP driver ID preprocessing prototype.

Save-only prototype. It is not wired into onboarding yet.

Purpose:
- Existing OCR is assumed to work.
- This module prepares driver-license / ID-card photos before OCR.
- It uses rounded-corner-safe edge-line intersections, geometry validation,
  real perspective warp when safe, and safe crop/orientation fallback when not.
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
    ratio_error_percent: float
    top_bottom_delta_percent: float
    left_right_delta_percent: float
    diagonal_delta_percent: float
    max_angle_error_from_90: float
    area_percent: float
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


def clean_mask(mask: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    out = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return cv2.morphologyEx(out, cv2.MORPH_OPEN, kernel, iterations=1)


def build_candidate_masks(image_bgr: np.ndarray) -> Dict[str, np.ndarray]:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    _h, s, v = cv2.split(hsv)

    blue_green = cv2.inRange(hsv, np.array([35, 22, 35]), np.array([125, 255, 255]))
    blue_green = clean_mask(blue_green, 5)

    _, sat_otsu = cv2.threshold(s, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    sat_otsu = clean_mask(sat_otsu, 5)

    bright = cv2.inRange(v, 95, 255)
    bright = clean_mask(bright, 7)

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)
    edges = clean_mask(edges, 7)

    return {
        "blue_green_component": blue_green,
        "saturation_otsu": sat_otsu,
        "bright_fallback": bright,
        "edge_fallback": edges,
    }


def connected_components_by_area(mask: np.ndarray, min_area_ratio: float = 0.006) -> List[np.ndarray]:
    h, w = mask.shape[:2]
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    comps: List[np.ndarray] = []
    for label in range(1, num):
        if stats[label, cv2.CC_STAT_AREA] < h * w * min_area_ratio:
            continue
        comp = np.zeros_like(mask)
        comp[labels == label] = 255
        comps.append(comp)
    comps.sort(key=lambda c: int(cv2.countNonZero(c)), reverse=True)
    return comps


def largest_contour(mask: np.ndarray) -> Optional[np.ndarray]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(contours, key=cv2.contourArea) if contours else None


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
    return tuple(float(v) for v in line.reshape(-1))


def intersect_lines(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> Optional[np.ndarray]:
    vx1, vy1, x1, y1 = a
    vx2, vy2, x2, y2 = b
    matrix = np.array([[vx1, -vx2], [vy1, -vy2]], dtype=np.float32)
    vector = np.array([x2 - x1, y2 - y1], dtype=np.float32)
    if abs(float(np.linalg.det(matrix))) < 1e-6:
        return None
    t, _ = np.linalg.solve(matrix, vector)
    return np.array([x1 + t * vx1, y1 + t * vy1], dtype=np.float32)


def line_intersection_corners_for_rounded_card(
    component_mask: np.ndarray,
    low_pct: float = 3.0,
    high_pct: float = 97.0,
    band_ratio: float = 0.055,
    corner_ignore_ratio: float = 0.16,
) -> Optional[np.ndarray]:
    """Use straight edge-line intersections, not rounded arc pixels, as DL corners."""
    contour = largest_contour(component_mask)
    if contour is None or len(contour) < 50:
        return None

    pts = contour.reshape(-1, 2).astype(np.float32)
    # Rough frame only. Do not use minAreaRect as final perspective truth.
    rough_box = order_corners(cv2.boxPoints(cv2.minAreaRect(pts)).astype(np.float32))
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
    corners = [intersect_lines(top, left), intersect_lines(top, right), intersect_lines(bottom, right), intersect_lines(bottom, left)]
    if any(c is None for c in corners):
        return None
    return order_corners(np.vstack(corners).astype(np.float32))


def angle_at(p_prev: np.ndarray, p: np.ndarray, p_next: np.ndarray) -> float:
    v1 = p_prev - p
    v2 = p_next - p
    cos_ang = float(np.dot(v1, v2) / ((np.linalg.norm(v1) * np.linalg.norm(v2)) + 1e-6))
    return float(np.degrees(np.arccos(np.clip(cos_ang, -1.0, 1.0))))


def measure_geometry(corners: np.ndarray, image_shape: Tuple[int, int, int]) -> GeometryMeasurement:
    corners = order_corners(corners).astype(np.float32)
    h, w = image_shape[:2]
    tl, tr, br, bl = corners

    top = float(np.linalg.norm(tr - tl))
    bottom = float(np.linalg.norm(br - bl))
    left = float(np.linalg.norm(bl - tl))
    right = float(np.linalg.norm(br - tr))
    d1 = float(np.linalg.norm(br - tl))
    d2 = float(np.linalg.norm(bl - tr))
    ratio = ((top + bottom) / 2.0) / (((left + right) / 2.0) + 1e-6)
    angles = [angle_at(bl, tl, tr), angle_at(tl, tr, br), angle_at(tr, br, bl), angle_at(br, bl, tl)]
    max_angle_err = max(abs(a - 90.0) for a in angles)

    x_min, y_min = np.min(corners, axis=0)
    x_max, y_max = np.max(corners, axis=0)
    margin = max(4, int(max(w, h) * 0.006))
    border_touch_count = int(sum([x_min <= margin, y_min <= margin, x_max >= w - 1 - margin, y_max >= h - 1 - margin]))

    ratio_error = abs(ratio - DL_ASPECT) / DL_ASPECT * 100.0
    tb_delta = abs(top - bottom) / (max(top, bottom) + 1e-6) * 100.0
    lr_delta = abs(left - right) / (max(left, right) + 1e-6) * 100.0
    diag_delta = abs(d1 - d2) / (max(d1, d2) + 1e-6) * 100.0
    area_percent = abs(float(cv2.contourArea(corners))) / float(w * h) * 100.0

    strict = ratio_error <= 5.0 and max_angle_err <= 10.0 and tb_delta <= 8.0 and lr_delta <= 10.0 and diag_delta <= 10.0
    permissive = ratio_error <= 4.0 and max_angle_err <= 6.0 and tb_delta <= 4.0 and lr_delta <= 15.0 and diag_delta <= 10.0

    reasons: List[str] = []
    if border_touch_count:
        reasons.append("border_touch_risk")
    if ratio_error > 5.0:
        reasons.append("ratio_error_gt_5_percent")
    if max_angle_err > 10.0:
        reasons.append("angle_error_gt_10_degrees")
    if tb_delta > 8.0:
        reasons.append("top_bottom_delta_gt_8_percent")
    if lr_delta > 10.0 and not permissive:
        reasons.append("left_right_delta_gt_10_percent")
    if diag_delta > 10.0:
        reasons.append("diagonal_delta_gt_10_percent")

    return GeometryMeasurement(
        ratio_error,
        tb_delta,
        lr_delta,
        diag_delta,
        max_angle_err,
        area_percent,
        border_touch_count,
        (strict or permissive) and border_touch_count == 0,
        reasons,
    )


def geometry_error_score(m: GeometryMeasurement) -> float:
    return (
        m.ratio_error_percent * 4.0
        + m.max_angle_error_from_90 * 2.0
        + m.top_bottom_delta_percent
        + m.left_right_delta_percent
        + m.diagonal_delta_percent * 0.5
        + (60.0 if m.border_touch_count else 0.0)
    )


def refine_corners_iterative(component_mask: np.ndarray, image_shape: Tuple[int, int, int]) -> Tuple[Optional[np.ndarray], Optional[GeometryMeasurement], List[Dict]]:
    attempts: List[Dict] = []
    best_corners: Optional[np.ndarray] = None
    best_measurement: Optional[GeometryMeasurement] = None
    best_error = float("inf")

    for low, high in [(2, 98), (3, 97), (4, 96), (5, 95), (6, 94), (8, 92)]:
        for band in [0.04, 0.05, 0.06, 0.075, 0.09, 0.11, 0.13]:
            for ignore in [0.10, 0.13, 0.16, 0.20, 0.24]:
                corners = line_intersection_corners_for_rounded_card(component_mask, float(low), float(high), float(band), float(ignore))
                if corners is None:
                    continue
                measurement = measure_geometry(corners, image_shape)
                err = geometry_error_score(measurement)
                attempts.append({
                    "low_pct": low,
                    "high_pct": high,
                    "band_ratio": band,
                    "corner_ignore_ratio": ignore,
                    "error_score": err,
                    "valid_for_perspective": measurement.valid_for_perspective,
                    "measurement": asdict(measurement),
                })
                if err < best_error:
                    best_error = err
                    best_corners = corners
                    best_measurement = measurement
                if measurement.valid_for_perspective:
                    return best_corners, best_measurement, attempts
    return best_corners, best_measurement, attempts


def perspective_warp_to_reference(image_bgr: np.ndarray, corners: np.ndarray) -> np.ndarray:
    src = order_corners(corners).astype(np.float32)
    dst = np.array([[0, 0], [TARGET_W - 1, 0], [TARGET_W - 1, TARGET_H - 1], [0, TARGET_H - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image_bgr, matrix, (TARGET_W, TARGET_H))


def ensure_landscape_upright_for_dl(image_bgr: np.ndarray) -> np.ndarray:
    out = image_bgr.copy()
    if out.shape[0] > out.shape[1]:
        out = cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE)
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
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(iw, x + w + pad), min(ih, y + h + pad)
    return image_bgr[y0:y1, x0:x1].copy(), [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]


def score_candidate(m: Optional[GeometryMeasurement], component_mask: np.ndarray, mask_priority: float, component_index: int) -> float:
    area_percent = cv2.countNonZero(component_mask) / float(component_mask.shape[0] * component_mask.shape[1]) * 100.0
    if m is None:
        return -500.0 + area_percent + mask_priority - component_index * 4.0
    score = 100.0 - m.ratio_error_percent * 4.0 - m.max_angle_error_from_90 * 2.0 - m.top_bottom_delta_percent - m.left_right_delta_percent - m.diagonal_delta_percent * 0.4
    score += min(25.0, m.area_percent * 0.45) + mask_priority
    if m.valid_for_perspective:
        score += 75.0
    if m.border_touch_count:
        score -= 35.0
    return float(score - component_index * 4.0)


def choose_best_candidate(image_bgr: np.ndarray, debug_dir: Optional[Path] = None) -> Tuple[CandidateResult, np.ndarray]:
    results: List[Tuple[CandidateResult, np.ndarray, Optional[np.ndarray], np.ndarray]] = []
    priorities = {"blue_green_component": 14.0, "saturation_otsu": 7.0, "bright_fallback": 0.0, "edge_fallback": -7.0}

    for orientation_name, oriented in orientation_candidates(image_bgr).items():
        for mask_name, mask in build_candidate_masks(oriented).items():
            for idx, comp in enumerate(connected_components_by_area(mask)[:1]):
                corners, measurement, attempts = refine_corners_iterative(comp, oriented.shape)
                _crop, rect = safe_crop_from_component(oriented, comp)
                score = score_candidate(measurement, comp, priorities.get(mask_name, 0.0), idx)
                decision = "accepted_perspective_first_warp_line_intersection" if measurement and measurement.valid_for_perspective else ("rejected_perspective_safe_crop_orientation_only" if measurement else "no_geometry_safe_crop_orientation_only")
                results.append((CandidateResult(orientation_name, mask_name, idx, score, decision, measurement, corners.tolist() if corners is not None else None, rect, attempts), oriented, corners, comp))

    if not results:
        fallback = CandidateResult("original", "none", 0, -999.0, "original_fallback_no_candidate", None, None, [0, 0, image_bgr.shape[1], image_bgr.shape[0]], [])
        return fallback, ensure_landscape_upright_for_dl(image_bgr)

    results.sort(key=lambda item: item[0].score, reverse=True)
    best, oriented, corners, comp = results[0]

    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "candidate_scores.json").write_text(json.dumps([asdict(item[0]) for item in results[:20]], indent=2), encoding="utf-8")
        cv2.imwrite(str(debug_dir / "01_best_component_mask.jpg"), comp)
        debug = oriented.copy()
        if corners is not None:
            c = order_corners(corners).astype(int)
            for i, label in enumerate(["TL", "TR", "BR", "BL"]):
                p1 = tuple(c[i])
                p2 = tuple(c[(i + 1) % 4])
                cv2.line(debug, p1, p2, (0, 0, 255), 3)
                cv2.circle(debug, p1, 8, (0, 255, 0), -1)
                cv2.putText(debug, label, (p1[0] + 8, p1[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
        cv2.imwrite(str(debug_dir / "02_best_corners_debug.jpg"), debug)

    if best.measurement and best.measurement.valid_for_perspective and corners is not None:
        return best, ensure_landscape_upright_for_dl(perspective_warp_to_reference(oriented, corners))

    safe, _ = safe_crop_from_component(oriented, comp)
    return best, ensure_landscape_upright_for_dl(safe)


def preprocess_driver_id_image(input_path: str, output_path: str, debug_dir: Optional[str] = None) -> Dict:
    image = cv2.imread(input_path)
    if image is None:
        raise FileNotFoundError(f"Cannot load image: {input_path}")
    debug_path = Path(debug_dir) if debug_dir else None
    result, final = choose_best_candidate(image, debug_path)
    cv2.imwrite(output_path, final)
    payload = {"input_path": input_path, "output_path": output_path, "target_width": TARGET_W, "target_height": TARGET_H, "target_aspect": DL_ASPECT, "result": asdict(result), "final_shape": {"height": int(final.shape[0]), "width": int(final.shape[1])}}
    if debug_path:
        cv2.imwrite(str(debug_path / "03_final_selected.jpg"), final)
        (debug_path / "result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess driver ID image using rounded-corner line-intersection geometry.")
    parser.add_argument("input", help="Input image path")
    parser.add_argument("output", help="Output image path")
    parser.add_argument("--debug-dir", default=None, help="Optional debug output folder")
    args = parser.parse_args()
    print(json.dumps(preprocess_driver_id_image(args.input, args.output, args.debug_dir), indent=2))


if __name__ == "__main__":
    main()
