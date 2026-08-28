"""Production Driver Licence preprocessing.

This module intentionally uses the exact successful sandbox four-corner algorithm.
The only production adaptation is bytes-in / JPEG-bytes-out instead of sandbox paths.
No browser geometry, no safe component crop, no alternate classifier.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

DL_ASPECT = 85.60 / 53.98
TARGET_W = 1000
TARGET_H = int(round(TARGET_W / DL_ASPECT))


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


def largest_contour(mask: np.ndarray):
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


ORIENTATION_ORDER = ["original", "cw90", "ccw90", "rotate180"]


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


@dataclass(frozen=True)
class DLPreprocessResult:
    status: str
    processed_jpeg: bytes | None
    diagnostics: dict[str, Any]


def preprocess_driver_license_bytes(source_bytes: bytes) -> DLPreprocessResult:
    """Run the proven sandbox algorithm on an uploaded DL image.

    Hard rule preserved from sandbox: if all four independent edges/corners are
    not confirmed, return no processed derivative. The caller keeps the raw upload.
    """
    source = cv2.imdecode(np.frombuffer(source_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if source is None:
        return DLPreprocessResult(
            status="FOUR_CORNERS_NOT_CONFIRMED",
            processed_jpeg=None,
            diagnostics={"reason": "image_decode_failed"},
        )

    best = None
    for orientation_rank, orientation in enumerate(ORIENTATION_ORDER):
        oriented = rotate_image(source, orientation)
        for candidate_rank, seed in enumerate(_rough_card_candidates(oriented)):
            corners, diagnostics, support = _confirm_all_four_corners(oriented, seed["rough_box"])
            if corners is None:
                continue
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
                    "seed": seed,
                    "corners": corners,
                    "diagnostics": diagnostics,
                    "support": support,
                }

    if best is None:
        return DLPreprocessResult(
            status="FOUR_CORNERS_NOT_CONFIRMED",
            processed_jpeg=None,
            diagnostics={"confirmed": False},
        )

    final = _warp_confirmed_card(best["oriented"], best["corners"])
    ok, encoded = cv2.imencode(".jpg", final, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        return DLPreprocessResult(
            status="FOUR_CORNERS_NOT_CONFIRMED",
            processed_jpeg=None,
            diagnostics={"confirmed": False, "reason": "jpeg_encode_failed"},
        )

    diagnostics = dict(best["diagnostics"])
    diagnostics.update({
        "orientation_used": best["orientation"],
        "final_width": int(final.shape[1]),
        "final_height": int(final.shape[0]),
    })
    return DLPreprocessResult(
        status="FOUR_CORNERS_CONFIRMED",
        processed_jpeg=encoded.tobytes(),
        diagnostics=diagnostics,
    )
