"""
TruckERP applicant DL OpenCV processor.

Canonical engine: exact successful sandbox edge/corner functions, preserved verbatim
from the two frozen sandbox sources below. Production wrapper intentionally does not
reinterpret the detector.

Sandbox source SHA-256:
- 01_may12_base_exact_executed.py:
  ac008e5b3583dee103d975fd08c61dacc2076a768ed10fa39ab737ff2c097d8a
- 02_four_corner_refinement_exact_executed.py:
  bade5f5a34beb2537750235c3525fbd6420bc28b255518d55a4701531908f6d4
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

PREPROCESS_VERSION = "2026-08-28-sandbox-exact"
SANDBOX_BASE_SHA256 = "ac008e5b3583dee103d975fd08c61dacc2076a768ed10fa39ab737ff2c097d8a"
SANDBOX_REFINEMENT_SHA256 = "bade5f5a34beb2537750235c3525fbd6420bc28b255518d55a4701531908f6d4"

DL_ASPECT = 85.60 / 53.98
TARGET_W = 1000
TARGET_H = int(round(TARGET_W / DL_ASPECT))
ORIENTATION_ORDER = ["original", "cw90", "ccw90", "rotate180"]

@dataclass
class CandidateResult:
    orientation_name: str
    seed_rank: int
    score: float
    corners: Optional[list[list[float]]]
    confirm_diagnostics: Optional[dict[str, Any]]

@dataclass
class ProcessResult:
    geometry_class: str
    correction_applied: str
    post_validation_pass: bool
    post_validation: dict[str, Any]
    candidate: CandidateResult
    final_shape: dict[str, int]
    report: dict[str, Any]

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

def _rough_card_candidates(image_bgr):
    """Color is only a seed for where to search; it is never accepted as final card geometry."""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    cool = cv2.inRange(hsv, np.array([35, 18, 60]), np.array([135, 255, 255]))
    cool = cv2.morphologyEx(
        cool, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    )
    cool = cv2.morphologyEx(
        cool, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
    )

    h, w = cool.shape
    n, labels, stats, _ = cv2.connectedComponentsWithStats(cool, 8)

    components = []
    for label in range(1, n):
        x, y, cw, ch, area = stats[label]
        if area < 0.004 * h * w:
            continue
        mask = (labels == label).astype(np.uint8) * 255
        contour = largest_contour(mask)
        if contour is not None:
            components.append((int(area), contour))

    components.sort(key=lambda item: item[0], reverse=True)
    components = components[:6]

    candidates = []
    for count in range(1, min(4, len(components) + 1)):
        for indices in itertools.combinations(range(len(components)), count):
            pts = np.vstack(
                [components[i][1].reshape(-1, 2) for i in indices]
            ).astype(np.float32)

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

            # Search in an orientation where the DL's long edge is horizontal.
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

def _gradient_magnitude(image_bgr):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gx, gy)

def _sample_boundary_points(image_bgr, p0, p1, search_px, sample_count=180):
    """For one proposed edge, search normal to it for the strongest real image boundary."""
    mag = _gradient_magnitude(image_bgr)
    h, w = mag.shape

    p0 = np.asarray(p0, dtype=np.float32)
    p1 = np.asarray(p1, dtype=np.float32)
    edge = p1 - p0
    edge_len = float(np.linalg.norm(edge))
    tangent = edge / (edge_len + 1e-6)
    normal = np.array([-tangent[1], tangent[0]], dtype=np.float32)

    offsets = np.arange(-search_px, search_px + 1, dtype=np.float32)
    found = []

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

        # Prefer a strong boundary near the rough edge, not internal text several inches away.
        scores = vals - 0.6 * np.abs(valid_offsets)
        winner = int(np.argmax(scores))

        if float(vals[winner]) >= 25.0:
            found.append(points[valid][winner])

    return np.asarray(found, dtype=np.float32)

def _ransac_edge_line(points, distance_threshold=4.5, iterations=400):
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

        # 2-D point-to-line distance.
        rel = pts - a
        distances = np.abs(direction[0] * rel[:, 1] - direction[1] * rel[:, 0]) / length
        inliers = np.where(distances <= distance_threshold)[0]

        if len(inliers) > len(best_inliers):
            best_inliers = inliers

    if len(best_inliers) < 20:
        return None, best_inliers

    line = cv2.fitLine(
        pts[best_inliers].reshape(-1, 1, 2),
        cv2.DIST_L2, 0, 0.01, 0.01
    ).reshape(-1)

    return tuple(float(v) for v in line), best_inliers

def _intersect_fitted_lines(a, b):
    vx1, vy1, x1, y1 = a
    vx2, vy2, x2, y2 = b

    matrix = np.array([[vx1, -vx2], [vy1, -vy2]], dtype=np.float64)
    vector = np.array([x2 - x1, y2 - y1], dtype=np.float64)

    if abs(float(np.linalg.det(matrix))) < 1e-6:
        return None

    t, _ = np.linalg.solve(matrix, vector)
    return np.array([x1 + t * vx1, y1 + t * vy1], dtype=np.float32)

def _confirm_all_four_corners(image_bgr, rough_box):
    """Four edge lines must independently succeed. Only their intersections become corners."""
    side_lengths = [
        float(np.linalg.norm(rough_box[(i + 1) % 4] - rough_box[i]))
        for i in range(4)
    ]
    short_side = min(
        max(side_lengths[0], side_lengths[2]),
        max(side_lengths[1], side_lengths[3]),
    )
    search_px = int(max(30, min(110, 0.12 * short_side)))

    edge_lines = []
    edge_points = []
    edge_inliers = []

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
        edge_points.append(points)
        edge_inliers.append(int(len(inliers)))

    # TL, TR, BR, BL from the four independent straight-edge intersections.
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

    # Every corner must actually land inside the source image.
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

    angles = [
        angle_at(bl, tl, tr),
        angle_at(tl, tr, br),
        angle_at(tr, br, bl),
        angle_at(br, bl, tl),
    ]
    max_angle_error = max(abs(value - 90.0) for value in angles)

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

    return (corners if confirmed else None), diagnostics, (edge_points, edge_lines)

def _warp_confirmed_card(image_bgr, corners):
    src = order_corners(corners).astype(np.float32)
    dst = np.array(
        [
            [0, 0],
            [TARGET_W - 1, 0],
            [TARGET_W - 1, TARGET_H - 1],
            [0, TARGET_H - 1],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(image_bgr, matrix, (TARGET_W, TARGET_H))
    return ensure_landscape_upright_for_dl(warped)


def _failure_result(image_bgr: np.ndarray, report: dict[str, Any]) -> tuple[ProcessResult, np.ndarray]:
    candidate = CandidateResult("original", 0, -999.0, None, report)
    result = ProcessResult(
        geometry_class="UNCONFIRMED",
        correction_applied="none",
        post_validation_pass=False,
        post_validation={"pass": False, "reason": report.get("status", "preprocess_failed")},
        candidate=candidate,
        final_shape={"width": int(image_bgr.shape[1]), "height": int(image_bgr.shape[0])},
        report=report,
    )
    return result, image_bgr.copy()


def process_driver_license_image(
    image_bgr: np.ndarray,
    debug_dir: Optional[Path] = None,
) -> tuple[ProcessResult, np.ndarray]:
    """
    Production wrapper around the exact successful sandbox processor.

    Exact sandbox decision:
      no 4 confirmed corners -> FAILED
      4 confirmed corners    -> exact sandbox four-corner perspective warp
    """
    best: Optional[dict[str, Any]] = None

    for orientation_rank, orientation in enumerate(ORIENTATION_ORDER):
        oriented = rotate_image(image_bgr, orientation)

        for candidate_rank, seed in enumerate(_rough_card_candidates(oriented)):
            corners, diagnostics, support = _confirm_all_four_corners(
                oriented, seed["rough_box"]
            )
            if corners is None:
                continue

            # Exact sandbox ranking formula.
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
                    "support": support,
                }

    if best is None:
        report = {
            "four_edges_confirmed": False,
            "status": "FOUR_CORNERS_NOT_CONFIRMED",
            "preprocess_version": PREPROCESS_VERSION,
            "sandbox_base_sha256": SANDBOX_BASE_SHA256,
            "sandbox_refinement_sha256": SANDBOX_REFINEMENT_SHA256,
        }
        return _failure_result(image_bgr, report)

    oriented = best["oriented"]
    corners = best["corners"]

    # Exact historical sandbox final correction. Do not classify/reinterpret.
    final = _warp_confirmed_card(oriented, corners)

    post_ok = bool(
        final is not None
        and final.size > 0
        and final.shape[1] == TARGET_W
        and final.shape[0] == TARGET_H
    )
    post_report = {
        "pass": post_ok,
        "width": int(final.shape[1]),
        "height": int(final.shape[0]),
    }

    report: dict[str, Any] = {
        "four_edges_confirmed": True,
        "status": "FOUR_CORNERS_CONFIRMED" if post_ok else "POST_VALIDATION_FAILED",
        "orientation_used": best["orientation"],
        "corners_tl_tr_br_bl": corners.tolist(),
        "edge_inliers": best["diagnostics"].get("edge_inliers"),
        "confirm_diagnostics": best["diagnostics"],
        "classification": "FOUR_CORNER_WARP",
        "correction_applied": "sandbox_four_corner_perspective_warp",
        "post_validation": post_report,
        "final_dimensions": {"width": int(final.shape[1]), "height": int(final.shape[0])},
        "preprocess_version": PREPROCESS_VERSION,
        "sandbox_base_sha256": SANDBOX_BASE_SHA256,
        "sandbox_refinement_sha256": SANDBOX_REFINEMENT_SHA256,
    }

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
            cv2.putText(
                dbg,
                labels[i],
                (p1[0] + 14, p1[1] - 14),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.1,
                (255, 0, 0),
                3,
            )
        cv2.imwrite(str(debug_dir / "four_confirmed_corners.jpg"), dbg)
        cv2.imwrite(str(debug_dir / "final.jpg"), final)
        (debug_dir / "report.json").write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )

    candidate = CandidateResult(
        orientation_name=best["orientation"],
        seed_rank=best["seed_rank"],
        score=best["score"],
        corners=corners.tolist(),
        confirm_diagnostics=best["diagnostics"],
    )
    result = ProcessResult(
        geometry_class="FOUR_CORNER_WARP",
        correction_applied="sandbox_four_corner_perspective_warp",
        post_validation_pass=post_ok,
        post_validation=post_report,
        candidate=candidate,
        final_shape={"width": int(final.shape[1]), "height": int(final.shape[0])},
        report=report,
    )
    return result, final


def process_applicant_dl_image_path(
    image_path: str | Path,
    debug_dir: Optional[Path] = None,
) -> tuple[ProcessResult, np.ndarray]:
    image = cv2.imread(str(image_path))
    if image is None:
        blank = np.zeros((1, 1, 3), dtype=np.uint8)
        report = {
            "four_edges_confirmed": False,
            "status": "IMAGE_LOAD_FAILED",
            "preprocess_version": PREPROCESS_VERSION,
            "sandbox_base_sha256": SANDBOX_BASE_SHA256,
            "sandbox_refinement_sha256": SANDBOX_REFINEMENT_SHA256,
        }
        return _failure_result(blank, report)
    return process_driver_license_image(image, debug_dir)


def encode_processed_jpeg(image_bgr: np.ndarray, quality: int = 92) -> bytes:
    ok, buf = cv2.imencode(
        ".jpg",
        image_bgr,
        [int(cv2.IMWRITE_JPEG_QUALITY), quality],
    )
    if not ok:
        raise ValueError("jpeg_encode_failed")
    return buf.tobytes()
