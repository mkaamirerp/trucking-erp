"""
Server-side driver licence OpenCV preprocessing (production).

Sandbox File-2 foundation: HSV seed → Sobel/RANSAC four edges → line intersections.
After confirm: classify FLAT_LEVEL / FLAT_ROTATED / PERSPECTIVE → correct → ensure upright.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import cv2
import numpy as np

PREPROCESS_VERSION = "2026-08-28-sandbox-v3"

MAX_OPENCV_INPUT_SIDE = 2400

RECTANGLE_CORNER_TOLERANCE_DEG = 4.0
PARALLEL_TOLERANCE_DEG = 3.0
LEVEL_TOLERANCE_DEG = 2.0
POST_ASPECT_TOLERANCE_PERCENT = 6.0

DL_ASPECT = 85.60 / 53.98
TARGET_W = 1000
TARGET_H = int(round(TARGET_W / DL_ASPECT))

ORIENTATION_ORDER = ["original", "cw90", "ccw90", "rotate180"]

GeometryClass = Literal["UNCONFIRMED", "FLAT_LEVEL", "FLAT_ROTATED", "PERSPECTIVE"]
LineParam = Tuple[float, float, float, float]


@dataclass
class EdgeLines:
    top: Optional[LineParam] = None
    right: Optional[LineParam] = None
    bottom: Optional[LineParam] = None
    left: Optional[LineParam] = None
    all_four_confirmed: bool = False


@dataclass
class GeometryMetrics:
    top_angle_deg: float = 0.0
    bottom_angle_deg: float = 0.0
    left_angle_deg: float = 0.0
    right_angle_deg: float = 0.0
    corner_angles_deg: List[float] = field(default_factory=list)
    parallel_error_top_bottom_deg: float = 0.0
    parallel_error_left_right_deg: float = 0.0
    avg_long_edge_rotation_deg: float = 0.0
    rotation_action_deg: float = 0.0
    top_bottom_length_delta_percent: float = 0.0
    left_right_length_delta_percent: float = 0.0
    diagonal_delta_percent: float = 0.0
    quadrilateral_area_percent: float = 0.0
    border_touch_count: int = 0
    edge_inliers: List[int] = field(default_factory=list)


@dataclass
class CandidateResult:
    orientation_name: str
    seed_rank: int
    score: float
    geometry_class: GeometryClass
    measurement: Optional[GeometryMetrics]
    corners: Optional[List[List[float]]]
    edge_lines: Optional[EdgeLines]
    post_validation: Optional[Dict[str, Any]]
    confirm_diagnostics: Optional[Dict[str, Any]]


@dataclass
class ProcessResult:
    geometry_class: GeometryClass
    correction_applied: str
    post_validation_pass: bool
    post_validation: Dict[str, Any]
    candidate: CandidateResult
    final_shape: Dict[str, int]
    report: Dict[str, Any]


def load_bgr_image_for_processing(image_path: str | Path, max_side: int = MAX_OPENCV_INPUT_SIDE) -> np.ndarray | None:
    """Load upload for OpenCV. Downscale phone photos so edge/RANSAC matches sandbox scale."""
    path = Path(image_path)
    image = cv2.imread(str(path))
    if image is None:
        try:
            from PIL import Image

            pil = Image.open(path).convert("RGB")
            image = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        except Exception:
            return None

    height, width = image.shape[:2]
    long_side = max(height, width)
    if long_side > max_side:
        scale = max_side / long_side
        image = cv2.resize(
            image,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return image


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


def angle_at(p_prev: np.ndarray, p: np.ndarray, p_next: np.ndarray) -> float:
    v1 = p_prev - p
    v2 = p_next - p
    cos_ang = float(np.dot(v1, v2) / ((np.linalg.norm(v1) * np.linalg.norm(v2)) + 1e-6))
    return float(np.degrees(np.arccos(np.clip(cos_ang, -1.0, 1.0))))


def ensure_landscape_upright_for_dl(image_bgr: np.ndarray) -> np.ndarray:
    """Sandbox May-12: landscape + photo-left upright (180° flip when portrait is on the right)."""
    out = image_bgr.copy()
    if out.shape[0] > out.shape[1]:
        out = cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE)
    gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    y0, y1 = int(h * 0.18), int(h * 0.82)
    left_roi = gray[y0:y1, int(w * 0.05) : int(w * 0.45)]
    right_roi = gray[y0:y1, int(w * 0.55) : int(w * 0.95)]
    left_dark = float(np.mean(left_roi < 115)) if left_roi.size else 0.0
    right_dark = float(np.mean(right_roi < 115)) if right_roi.size else 0.0
    if right_dark > left_dark * 1.15 and right_dark > 0.03:
        out = cv2.rotate(out, cv2.ROTATE_180)
    return out


def line_angle_deg(line: LineParam) -> float:
    vx, vy, _, _ = line
    return float(math.degrees(math.atan2(vy, vx)))


def angular_diff_deg(a: float, b: float) -> float:
    diff = abs(a - b) % 180.0
    return min(diff, 180.0 - diff)


def axial_circular_mean_deg(angles: List[float]) -> float:
    if not angles:
        return 0.0
    sin_sum = sum(math.sin(math.radians(a)) for a in angles)
    cos_sum = sum(math.cos(math.radians(a)) for a in angles)
    return float(math.degrees(math.atan2(sin_sum, cos_sum)))


def deviation_from_horizontal_deg(angle: float) -> float:
    a = ((angle % 180.0) + 180.0) % 180.0
    return min(a, abs(180.0 - a))


def deviation_from_vertical_deg(angle: float) -> float:
    return abs(deviation_from_horizontal_deg(angle) - 90.0)


def _rough_card_candidates(image_bgr: np.ndarray) -> List[Dict[str, Any]]:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    cool = cv2.inRange(hsv, np.array([35, 18, 60]), np.array([135, 255, 255]))
    cool = cv2.morphologyEx(cool, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cool = cv2.morphologyEx(cool, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19)))

    h, w = cool.shape
    n, labels, stats, _ = cv2.connectedComponentsWithStats(cool, 8)

    components: List[Tuple[int, np.ndarray]] = []
    for label in range(1, n):
        _x, _y, _cw, _ch, area = stats[label]
        if area < 0.004 * h * w:
            continue
        mask = (labels == label).astype(np.uint8) * 255
        contour = largest_contour(mask)
        if contour is not None:
            components.append((int(area), contour))

    components.sort(key=lambda item: item[0], reverse=True)
    components = components[:6]

    candidates: List[Dict[str, Any]] = []
    for count in range(1, min(4, len(components) + 1)):
        for indices in itertools.combinations(range(len(components)), count):
            pts = np.vstack([components[i][1].reshape(-1, 2) for i in indices]).astype(np.float32)
            hull = cv2.convexHull(pts)
            rect = cv2.minAreaRect(hull)
            (_, _), (rw, rh), _ = rect
            if min(rw, rh) < 20:
                continue

            ratio = max(rw, rh) / min(rw, rh)
            area_ratio = (rw * rh) / float(h * w)
            if not (0.06 <= area_ratio <= 0.65):
                continue

            box = order_corners(cv2.boxPoints(rect).astype(np.float32))
            top_len = float(np.linalg.norm(box[1] - box[0]))
            left_len = float(np.linalg.norm(box[3] - box[0]))
            if top_len < left_len:
                continue

            polygon_mask = np.zeros_like(cool)
            cv2.fillConvexPoly(polygon_mask, np.round(box).astype(np.int32), 255)
            inside = polygon_mask > 0
            density = float(np.mean(cool[inside] > 0)) if inside.any() else 0.0
            ratio_error = abs(ratio - DL_ASPECT) / DL_ASPECT
            seed_score = ratio_error * 4.0 - density * 0.6

            candidates.append(
                {
                    "seed_score": float(seed_score),
                    "rough_box": box,
                    "component_indices": indices,
                    "area_ratio": float(area_ratio),
                    "rough_ratio": float(ratio),
                    "cool_density": density,
                }
            )

    candidates.sort(key=lambda item: item["seed_score"])
    return candidates[:6]


def _gradient_magnitude(image_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gx, gy)


def _sample_boundary_points(
    image_bgr: np.ndarray,
    p0: np.ndarray,
    p1: np.ndarray,
    search_px: int,
    sample_count: int = 180,
) -> np.ndarray:
    mag = _gradient_magnitude(image_bgr)
    h, w = mag.shape

    p0 = np.asarray(p0, dtype=np.float32)
    p1 = np.asarray(p1, dtype=np.float32)
    edge = p1 - p0
    edge_len = float(np.linalg.norm(edge))
    tangent = edge / (edge_len + 1e-6)
    normal = np.array([-tangent[1], tangent[0]], dtype=np.float32)

    offsets = np.arange(-search_px, search_px + 1, dtype=np.float32)
    found: List[np.ndarray] = []

    for position in np.linspace(0.08, 0.92, sample_count):
        base = p0 + position * edge
        points = base[None, :] + offsets[:, None] * normal[None, :]
        xs = np.round(points[:, 0]).astype(int)
        ys = np.round(points[:, 1]).astype(int)

        valid = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        if valid.sum() < 3:
            continue

        vals = mag[ys[valid], xs[valid]]
        valid_offsets = offsets[valid]
        scores = vals - 0.6 * np.abs(valid_offsets)
        winner = int(np.argmax(scores))

        if float(vals[winner]) >= 25.0:
            found.append(points[valid][winner])

    return np.asarray(found, dtype=np.float32)


def _ransac_edge_line(
    points: np.ndarray,
    distance_threshold: float = 4.5,
    iterations: int = 400,
) -> Tuple[Optional[LineParam], np.ndarray]:
    if len(points) < 20:
        return None, np.array([], dtype=int)

    pts = np.asarray(points, dtype=np.float32)
    rng = np.random.default_rng(123)
    best_inliers = np.array([], dtype=int)

    for _ in range(iterations):
        i, j = rng.choice(len(pts), 2, replace=False)
        a, b = pts[i], pts[j]
        direction = b - a
        length = float(np.linalg.norm(direction))
        if length < 5:
            continue

        rel = pts - a
        distances = np.abs(direction[0] * rel[:, 1] - direction[1] * rel[:, 0]) / length
        inliers = np.where(distances <= distance_threshold)[0]

        if len(inliers) > len(best_inliers):
            best_inliers = inliers

    if len(best_inliers) < 20:
        return None, best_inliers

    line = cv2.fitLine(pts[best_inliers].reshape(-1, 1, 2), cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
    return tuple(float(v) for v in line), best_inliers  # type: ignore[return-value]


def _intersect_fitted_lines(a: LineParam, b: LineParam) -> Optional[np.ndarray]:
    vx1, vy1, x1, y1 = a
    vx2, vy2, x2, y2 = b
    matrix = np.array([[vx1, -vx2], [vy1, -vy2]], dtype=np.float64)
    vector = np.array([x2 - x1, y2 - y1], dtype=np.float64)
    if abs(float(np.linalg.det(matrix))) < 1e-6:
        return None
    t, _ = np.linalg.solve(matrix, vector)
    return np.array([x1 + t * vx1, y1 + t * vy1], dtype=np.float32)


def _edge_lines_from_list(lines: List[LineParam]) -> EdgeLines:
    if len(lines) != 4:
        return EdgeLines(all_four_confirmed=False)
    return EdgeLines(top=lines[0], right=lines[1], bottom=lines[2], left=lines[3], all_four_confirmed=True)


def _confirm_all_four_corners(
    image_bgr: np.ndarray,
    rough_box: np.ndarray,
) -> Tuple[Optional[np.ndarray], Dict[str, Any], Optional[Tuple[List[np.ndarray], List[LineParam]]]]:
    side_lengths = [float(np.linalg.norm(rough_box[(i + 1) % 4] - rough_box[i])) for i in range(4)]
    short_side = min(max(side_lengths[0], side_lengths[2]), max(side_lengths[1], side_lengths[3]))
    search_px = int(max(30, min(110, 0.12 * short_side)))

    edge_lines: List[LineParam] = []
    edge_inliers: List[int] = []

    for edge_index in range(4):
        p0 = rough_box[edge_index]
        p1 = rough_box[(edge_index + 1) % 4]
        points = _sample_boundary_points(image_bgr, p0, p1, search_px)
        line, inliers = _ransac_edge_line(points)

        if line is None or len(inliers) < 50:
            return None, {
                "confirmed": False,
                "reason": f"edge_{edge_index}_not_confirmed",
                "edge_inliers": edge_inliers + [int(len(inliers))],
            }, None

        edge_lines.append(line)
        edge_inliers.append(int(len(inliers)))

    raw_corners = [
        _intersect_fitted_lines(edge_lines[3], edge_lines[0]),
        _intersect_fitted_lines(edge_lines[0], edge_lines[1]),
        _intersect_fitted_lines(edge_lines[1], edge_lines[2]),
        _intersect_fitted_lines(edge_lines[2], edge_lines[3]),
    ]

    if any(point is None for point in raw_corners):
        return None, {
            "confirmed": False,
            "reason": "four_line_intersections_not_available",
            "edge_inliers": edge_inliers,
        }, None

    corners = order_corners(np.vstack(raw_corners).astype(np.float32))
    h, w = image_bgr.shape[:2]

    all_inside = bool(
        np.all(
            (corners[:, 0] >= -5)
            & (corners[:, 0] <= w + 5)
            & (corners[:, 1] >= -5)
            & (corners[:, 1] <= h + 5)
        )
    )

    tl, tr, br, bl = corners
    top = float(np.linalg.norm(tr - tl))
    bottom = float(np.linalg.norm(br - bl))
    left = float(np.linalg.norm(bl - tl))
    right = float(np.linalg.norm(br - tr))
    ratio = ((top + bottom) / 2.0) / (((left + right) / 2.0) + 1e-6)
    polygon_area = abs(float(cv2.contourArea(corners))) / float(h * w)
    angles = [angle_at(bl, tl, tr), angle_at(tl, tr, br), angle_at(tr, br, bl), angle_at(br, bl, tl)]
    max_angle_error = max(abs(value - 90.0) for value in angles)

    # Sandbox File-2 confirmation gates (verbatim).
    confirmed = bool(
        all_inside
        and 0.08 <= polygon_area <= 0.65
        and 1.25 <= ratio <= 1.95
        and max_angle_error <= 20.0
        and min(edge_inliers) >= 50
    )

    diagnostics = {
        "confirmed": confirmed,
        "all_four_corners_inside_source": all_inside,
        "edge_inliers": edge_inliers,
        "ratio": ratio,
        "ratio_error_percent": abs(ratio - DL_ASPECT) / DL_ASPECT * 100.0,
        "area_percent": polygon_area * 100.0,
        "corner_angles": angles,
        "max_angle_error_from_90": max_angle_error,
        "search_px": search_px,
        "corners": {
            "TL": corners[0].tolist(),
            "TR": corners[1].tolist(),
            "BR": corners[2].tolist(),
            "BL": corners[3].tolist(),
        },
    }

    return (corners if confirmed else None), diagnostics, ([], edge_lines)


def measure_quadrilateral(corners: np.ndarray, edge_lines: EdgeLines, image_shape: Tuple[int, int, int]) -> GeometryMetrics:
    corners = order_corners(corners).astype(np.float32)
    h, w = image_shape[:2]
    tl, tr, br, bl = corners

    top_len = float(np.linalg.norm(tr - tl))
    bottom_len = float(np.linalg.norm(br - bl))
    left_len = float(np.linalg.norm(bl - tl))
    right_len = float(np.linalg.norm(br - tr))
    d1 = float(np.linalg.norm(br - tl))
    d2 = float(np.linalg.norm(bl - tr))

    corner_angles = [
        angle_at(bl, tl, tr),
        angle_at(tl, tr, br),
        angle_at(tr, br, bl),
        angle_at(br, bl, tl),
    ]

    x_min, y_min = np.min(corners, axis=0)
    x_max, y_max = np.max(corners, axis=0)
    margin = max(4, int(max(w, h) * 0.006))
    border_touch = int(sum([x_min <= margin, y_min <= margin, x_max >= w - 1 - margin, y_max >= h - 1 - margin]))

    top_angle = line_angle_deg(edge_lines.top) if edge_lines.top else 0.0
    bottom_angle = line_angle_deg(edge_lines.bottom) if edge_lines.bottom else 0.0
    left_angle = line_angle_deg(edge_lines.left) if edge_lines.left else 0.0
    right_angle = line_angle_deg(edge_lines.right) if edge_lines.right else 0.0
    top_rot = deviation_from_horizontal_deg(top_angle)
    bottom_rot = deviation_from_horizontal_deg(bottom_angle)
    rotation_action = -axial_circular_mean_deg([top_angle, bottom_angle])

    return GeometryMetrics(
        top_angle_deg=top_angle,
        bottom_angle_deg=bottom_angle,
        left_angle_deg=left_angle,
        right_angle_deg=right_angle,
        corner_angles_deg=corner_angles,
        parallel_error_top_bottom_deg=angular_diff_deg(top_angle, bottom_angle),
        parallel_error_left_right_deg=angular_diff_deg(left_angle, right_angle),
        avg_long_edge_rotation_deg=(top_rot + bottom_rot) / 2.0,
        rotation_action_deg=rotation_action,
        top_bottom_length_delta_percent=abs(top_len - bottom_len) / (max(top_len, bottom_len) + 1e-6) * 100.0,
        left_right_length_delta_percent=abs(left_len - right_len) / (max(left_len, right_len) + 1e-6) * 100.0,
        diagonal_delta_percent=abs(d1 - d2) / (max(d1, d2) + 1e-6) * 100.0,
        quadrilateral_area_percent=abs(float(cv2.contourArea(corners))) / float(w * h) * 100.0,
        border_touch_count=border_touch,
        edge_inliers=[],
    )


def classify_geometry(corners: Optional[np.ndarray], edge_lines: EdgeLines, metrics: GeometryMetrics) -> GeometryClass:
    if corners is None or not edge_lines.all_four_confirmed:
        return "UNCONFIRMED"

    max_corner_dev = max(abs(a - 90.0) for a in metrics.corner_angles_deg)
    parallel_bad = (
        metrics.parallel_error_top_bottom_deg > PARALLEL_TOLERANCE_DEG
        or metrics.parallel_error_left_right_deg > PARALLEL_TOLERANCE_DEG
    )

    if parallel_bad or max_corner_dev > RECTANGLE_CORNER_TOLERANCE_DEG:
        return "PERSPECTIVE"

    if metrics.avg_long_edge_rotation_deg > LEVEL_TOLERANCE_DEG:
        return "FLAT_ROTATED"

    left_vert = deviation_from_vertical_deg(metrics.left_angle_deg)
    right_vert = deviation_from_vertical_deg(metrics.right_angle_deg)
    if left_vert > LEVEL_TOLERANCE_DEG or right_vert > LEVEL_TOLERANCE_DEG:
        return "FLAT_ROTATED"

    return "FLAT_LEVEL"


def resize_to_target(image_bgr: np.ndarray) -> np.ndarray:
    return cv2.resize(image_bgr, (TARGET_W, TARGET_H), interpolation=cv2.INTER_LANCZOS4)


def finalize_processed(image_bgr: np.ndarray) -> np.ndarray:
    return ensure_landscape_upright_for_dl(image_bgr)


def apply_flat_level_crop(image_bgr: np.ndarray, corners: np.ndarray) -> np.ndarray:
    c = order_corners(corners).astype(np.float32)
    x0 = int(max(0, math.floor(float(np.min(c[:, 0])))))
    y0 = int(max(0, math.floor(float(np.min(c[:, 1])))))
    x1 = int(min(image_bgr.shape[1], math.ceil(float(np.max(c[:, 0])))))
    y1 = int(min(image_bgr.shape[0], math.ceil(float(np.max(c[:, 1])))))
    if x1 <= x0 or y1 <= y0:
        raise ValueError("invalid_flat_level_bounds")
    cropped = image_bgr[y0:y1, x0:x1].copy()
    return finalize_processed(resize_to_target(cropped))


def apply_flat_rotated_deskew(image_bgr: np.ndarray, corners: np.ndarray, metrics: GeometryMetrics) -> np.ndarray:
    rotation_deg = metrics.rotation_action_deg
    c = order_corners(corners).astype(np.float32)
    center = tuple(np.mean(c, axis=0))
    matrix = cv2.getRotationMatrix2D(center, rotation_deg, 1.0)
    rotated = cv2.warpAffine(
        image_bgr,
        matrix,
        (image_bgr.shape[1], image_bgr.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    ones = np.ones((c.shape[0], 1), dtype=np.float32)
    pts = np.hstack([c, ones])
    transformed = (matrix @ pts.T).T
    x0 = int(max(0, math.floor(float(np.min(transformed[:, 0])))))
    y0 = int(max(0, math.floor(float(np.min(transformed[:, 1])))))
    x1 = int(min(rotated.shape[1], math.ceil(float(np.max(transformed[:, 0])))))
    y1 = int(min(rotated.shape[0], math.ceil(float(np.max(transformed[:, 1])))))
    if x1 <= x0 or y1 <= y0:
        raise ValueError("invalid_rotated_crop_bounds")
    cropped = rotated[y0:y1, x0:x1].copy()
    return finalize_processed(resize_to_target(cropped))


def apply_perspective_warp(image_bgr: np.ndarray, corners: np.ndarray) -> np.ndarray:
    src = order_corners(corners).astype(np.float32)
    dst = np.array(
        [[0, 0], [TARGET_W - 1, 0], [TARGET_W - 1, TARGET_H - 1], [0, TARGET_H - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(image_bgr, matrix, (TARGET_W, TARGET_H))
    return finalize_processed(warped)


def apply_geometry_correction(
    image_bgr: np.ndarray,
    corners: np.ndarray,
    geometry_class: GeometryClass,
    metrics: GeometryMetrics,
) -> Tuple[np.ndarray, str]:
    if geometry_class == "FLAT_LEVEL":
        return apply_flat_level_crop(image_bgr, corners), "flat_level_crop"
    if geometry_class == "FLAT_ROTATED":
        return apply_flat_rotated_deskew(image_bgr, corners, metrics), f"flat_rotated_deskew_{metrics.rotation_action_deg:.1f}deg"
    if geometry_class == "PERSPECTIVE":
        return apply_perspective_warp(image_bgr, corners), "perspective_warp"
    raise ValueError(f"no_correction_for_{geometry_class}")


def post_validate_processed(image_bgr: np.ndarray) -> Tuple[bool, Dict[str, Any]]:
    if image_bgr is None or image_bgr.size == 0:
        return False, {"error": "empty_image"}
    h, w = image_bgr.shape[:2]
    if w < 32 or h < 32:
        return False, {"error": "too_small", "width": w, "height": h}

    landscape = w >= h
    aspect = w / float(h)
    aspect_error_pct = abs(aspect - DL_ASPECT) / DL_ASPECT * 100.0

    report = {
        "width": int(w),
        "height": int(h),
        "landscape": landscape,
        "aspect": aspect,
        "aspect_error_percent": aspect_error_pct,
        "pass": landscape and aspect_error_pct <= POST_ASPECT_TOLERANCE_PERCENT,
    }
    return bool(report["pass"]), report


def _failure_result(image_bgr: np.ndarray, report: Dict[str, Any], candidate: CandidateResult) -> ProcessResult:
    return ProcessResult(
        "UNCONFIRMED",
        "none",
        False,
        {"pass": False, "reason": report.get("status", "preprocess_failed")},
        candidate,
        {"width": int(image_bgr.shape[1]), "height": int(image_bgr.shape[0])},
        report,
    )


def process_driver_license_image(image_bgr: np.ndarray, debug_dir: Optional[Path] = None) -> Tuple[ProcessResult, np.ndarray]:
    best: Optional[Dict[str, Any]] = None

    for orientation_rank, orientation in enumerate(ORIENTATION_ORDER):
        oriented = rotate_image(image_bgr, orientation)
        for candidate_rank, seed in enumerate(_rough_card_candidates(oriented)):
            corners, diagnostics, support = _confirm_all_four_corners(oriented, seed["rough_box"])
            if corners is None or support is None:
                continue

            edge_lines = _edge_lines_from_list(support[1])
            metrics = measure_quadrilateral(corners, edge_lines, oriented.shape)
            metrics.edge_inliers = list(diagnostics.get("edge_inliers") or [])
            geom_class = classify_geometry(corners, edge_lines, metrics)

            score = (
                seed["seed_score"]
                + diagnostics["ratio_error_percent"] / 50.0
                + diagnostics["max_angle_error_from_90"] / 100.0
                + orientation_rank * 0.002
                + candidate_rank * 0.001
            )

            if best is None or score < best["score"]:
                best = {
                    "score": float(score),
                    "orientation": orientation,
                    "oriented": oriented,
                    "seed_rank": candidate_rank,
                    "corners": corners,
                    "diagnostics": diagnostics,
                    "edge_lines": edge_lines,
                    "metrics": metrics,
                    "geometry_class": geom_class,
                }

    if best is None:
        candidate = CandidateResult("original", 0, -999.0, "UNCONFIRMED", None, None, None, None, None)
        report = {"four_edges_confirmed": False, "status": "FOUR_CORNERS_NOT_CONFIRMED", "preprocess_version": PREPROCESS_VERSION}
        return _failure_result(image_bgr, report, candidate), image_bgr.copy()

    corners = best["corners"]
    oriented = best["oriented"]
    edge_lines = best["edge_lines"]
    metrics = best["metrics"]
    geom_class = best["geometry_class"]
    diagnostics = best["diagnostics"]

    report: Dict[str, Any] = {
        "four_edges_confirmed": True,
        "status": "FOUR_CORNERS_CONFIRMED",
        "orientation_used": best["orientation"],
        "corners_tl_tr_br_bl": corners.tolist(),
        "source_corner_angles_deg": metrics.corner_angles_deg,
        "top_angle_deg": metrics.top_angle_deg,
        "bottom_angle_deg": metrics.bottom_angle_deg,
        "left_angle_deg": metrics.left_angle_deg,
        "right_angle_deg": metrics.right_angle_deg,
        "parallel_error_top_bottom_deg": metrics.parallel_error_top_bottom_deg,
        "parallel_error_left_right_deg": metrics.parallel_error_left_right_deg,
        "edge_inliers": metrics.edge_inliers,
        "classification": geom_class,
        "rotation_action_deg": metrics.rotation_action_deg if geom_class == "FLAT_ROTATED" else None,
        "confirm_diagnostics": diagnostics,
        "preprocess_version": PREPROCESS_VERSION,
    }

    candidate = CandidateResult(
        best["orientation"],
        best["seed_rank"],
        best["score"],
        geom_class,
        metrics,
        corners.tolist(),
        edge_lines,
        None,
        diagnostics,
    )

    try:
        corrected, correction = apply_geometry_correction(oriented, corners, geom_class, metrics)
        post_ok, post_report = post_validate_processed(corrected)
        candidate.post_validation = post_report
        report["correction_applied"] = correction
        report["post_validation"] = post_report
        report["final_dimensions"] = {"width": corrected.shape[1], "height": corrected.shape[0]}

        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            dbg = oriented.copy()
            q = np.round(corners).astype(int)
            labels = ["TL", "TR", "BR", "BL"]
            for i in range(4):
                p1 = tuple(q[i])
                p2 = tuple(q[(i + 1) % 4])
                cv2.line(dbg, p1, p2, (0, 0, 255), 5)
                cv2.circle(dbg, p1, 14, (0, 255, 0), -1)
                cv2.putText(dbg, labels[i], (p1[0] + 14, p1[1] - 14), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 0, 0), 3)
            cv2.imwrite(str(debug_dir / "four_confirmed_corners.jpg"), dbg)
            cv2.imwrite(str(debug_dir / "final.jpg"), corrected)
            (debug_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

        if not post_ok:
            report["status"] = "POST_VALIDATION_FAILED"
            return _failure_result(image_bgr, report, candidate), image_bgr.copy()

        ok = ProcessResult(geom_class, correction, True, post_report, candidate, {"width": corrected.shape[1], "height": corrected.shape[0]}, report)
        return ok, corrected
    except Exception as exc:  # noqa: BLE001
        post_report = {"pass": False, "error": type(exc).__name__}
        candidate.post_validation = post_report
        report["correction_applied"] = "failed"
        report["post_validation"] = post_report
        report["status"] = "CORRECTION_FAILED"
        return _failure_result(image_bgr, report, candidate), image_bgr.copy()


def process_applicant_dl_image_path(image_path: str | Path, debug_dir: Optional[Path] = None) -> Tuple[ProcessResult, np.ndarray]:
    path = Path(image_path)
    image = load_bgr_image_for_processing(path)
    if image is None:
        candidate = CandidateResult("original", 0, -999.0, "UNCONFIRMED", None, None, None, None, None)
        report = {"four_edges_confirmed": False, "status": "IMAGE_LOAD_FAILED", "preprocess_version": PREPROCESS_VERSION}
        return _failure_result(image_bgr=np.zeros((1, 1, 3), dtype=np.uint8), report=report, candidate=candidate), np.zeros((1, 1, 3), dtype=np.uint8)

    result, corrected = process_driver_license_image(image, debug_dir)
    result.report["input_path"] = str(path)
    result.report["opencv_input_shape"] = {"width": int(image.shape[1]), "height": int(image.shape[0])}
    return result, corrected


def encode_processed_jpeg(image_bgr: np.ndarray, quality: int = 92) -> bytes:
    ok, buf = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise ValueError("jpeg_encode_failed")
    return buf.tobytes()


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess driver ID — sandbox four-corner pipeline.")
    parser.add_argument("input", help="Input image path")
    parser.add_argument("output", help="Output image path")
    parser.add_argument("--debug-dir", default=None, help="Optional debug output folder")
    args = parser.parse_args()
    image = cv2.imread(args.input)
    if image is None:
        raise FileNotFoundError(args.input)
    debug_path = Path(args.debug_dir) if args.debug_dir else None
    result, final = process_driver_license_image(image, debug_path)
    if not result.post_validation_pass:
        raise SystemExit(json.dumps(result.report, indent=2))
    cv2.imwrite(args.output, final)
    print(json.dumps({"status": result.report.get("status"), "classification": result.geometry_class, "correction": result.correction_applied}, indent=2))


if __name__ == "__main__":
    main()
