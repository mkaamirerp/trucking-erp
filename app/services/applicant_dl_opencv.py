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

PREPROCESS_VERSION = "2026-08-29-hsv-canny-rough-v1"
GEOMETRY_ENGINE_VERSION = "2026-08-28-sandbox-exact"
SANDBOX_BASE_SHA256 = "ac008e5b3583dee103d975fd08c61dacc2076a768ed10fa39ab737ff2c097d8a"
SANDBOX_REFINEMENT_SHA256 = "bade5f5a34beb2537750235c3525fbd6420bc28b255518d55a4701531908f6d4"

DL_ASPECT = 85.60 / 53.98
TARGET_W = 1000
TARGET_H = int(round(TARGET_W / DL_ASPECT))
NORMAL_MAX_AREA_RATIO = 0.65
CLOSEUP_ROUGH_MAX_AREA_RATIO = 1.00
CLOSEUP_CONFIRM_MAX_AREA_RATIO = 0.98
# Close-up candidates are much larger in pixel terms, so require
# stronger four-edge evidence than the normal path.
CLOSEUP_MIN_EDGE_INLIERS = 80
SOURCE_FRAME_MARGIN_PX = 8
ORIENTATION_ORDER = ["original", "cw90", "ccw90", "rotate180"]

# Short-side repair is a FALLBACK only. These do not loosen confirmer gates.
# A candidate must already fail the existing 1.25–1.95 ratio band.
SHORT_SIDE_REPAIR_RATIO_MIN = 1.95
SHORT_SIDE_REPAIR_RATIO_MAX = 2.55
SHORT_SIDE_REPAIR_OTHER_MIN_INLIERS = 80
SHORT_SIDE_REPAIR_MIN_INLIER_GAP = 20
SHORT_SIDE_REPAIR_MIN_SHORTFALL_FRAC = 0.08
SHORT_SIDE_REPAIR_INSIDE_MARGIN_PX = 8
SHORT_SIDE_REPAIR_SEARCH_FRAC = 0.18
SHORT_SIDE_REPAIR_SEARCH_MIN_PX = 24
SHORT_SIDE_REPAIR_SEARCH_MAX_PX = 70
SHORT_SIDE_REPAIR_VERSION = "2026-08-31-short-side-repair-v1"

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


def _hsv_scene_profile(image_bgr):
    """
    Classify only the surrounding scene/background.

    IMPORTANT:
    - This is NOT card geometry.
    - This does NOT decide whether a crop is valid.
    - It only decides which HSV masks should be tried first.

    Hue is not trusted when saturation is low.
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h_chan, s_chan, v_chan = cv2.split(hsv)

    h, w = s_chan.shape

    # Sample only the outside border of the photograph.
    # Avoid the center because that is where the licence normally sits.
    border_ratio = 0.12
    bx = max(1, int(round(w * border_ratio)))
    by = max(1, int(round(h * border_ratio)))

    border_mask = np.zeros((h, w), dtype=np.uint8)
    border_mask[:by, :] = 255
    border_mask[h - by :, :] = 255
    border_mask[:, :bx] = 255
    border_mask[:, w - bx :] = 255

    s_values = s_chan[border_mask > 0].astype(np.float32)
    v_values = v_chan[border_mask > 0].astype(np.float32)

    if s_values.size == 0 or v_values.size == 0:
        return {
            "family": "CHROMATIC",
            "s50": 0.0,
            "s75": 0.0,
            "v25": 0.0,
            "v50": 0.0,
            "v75": 0.0,
        }

    s50 = float(np.percentile(s_values, 50))
    s75 = float(np.percentile(s_values, 75))
    v25 = float(np.percentile(v_values, 25))
    v50 = float(np.percentile(v_values, 50))
    v75 = float(np.percentile(v_values, 75))

    # Initial evidence thresholds from current real DL photo set.
    #
    # IMG_9084 dark:
    #   S50 ~23, V50 ~63
    #
    # IMG_9083 gray couch:
    #   S50 ~30, V50 ~93
    #
    # white backgrounds:
    #   S50 ~10-30, V50 ~188-201
    #
    # wood/red backgrounds are clearly more saturated.
    neutral = s50 < 55.0

    if neutral:
        if v50 < 85.0:
            family = "NEUTRAL_DARK"
        elif v50 < 170.0:
            family = "NEUTRAL_MID"
        else:
            family = "NEUTRAL_LIGHT"
    else:
        family = "CHROMATIC"

    return {
        "family": family,
        "s50": s50,
        "s75": s75,
        "v25": v25,
        "v50": v50,
        "v75": v75,
    }


def _clean_cool_mask(mask):
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
    )
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19)),
    )
    return mask


def _build_hsv_seed_masks(image_bgr):
    """
    Return HSV masks in preferred search order.

    The first mask is scene-specific.
    Additional masks are conservative secondary searches.

    The old legacy mask remains last for compatibility, but it is no longer
    allowed to be the only way to locate the card.
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    profile = _hsv_scene_profile(image_bgr)

    family = profile["family"]
    masks = []

    if family == "NEUTRAL_DARK":
        # Dark/black background:
        # require card pixels to be brighter and somewhat saturated.
        v_low = int(max(90, min(160, profile["v50"] + 25)))

        mask = cv2.inRange(
            hsv,
            np.array([35, 30, v_low], dtype=np.uint8),
            np.array([135, 255, 255], dtype=np.uint8),
        )
        masks.append(("neutral_dark", _clean_cool_mask(mask), 0))

    elif family == "NEUTRAL_MID":
        # Gray background:
        # H alone is dangerous because gray pixels can carry arbitrary hue.
        # Require both meaningful saturation and brightness separation.
        v_low = int(max(120, min(185, profile["v50"] + 30)))

        mask = cv2.inRange(
            hsv,
            np.array([35, 40, v_low], dtype=np.uint8),
            np.array([135, 255, 255], dtype=np.uint8),
        )
        masks.append(("neutral_mid", _clean_cool_mask(mask), 0))

    elif family == "NEUTRAL_LIGHT":
        # White/light neutral background:
        # brightness is not useful because the background is already bright.
        # Saturation is the stronger separator.
        s_low = int(max(35, min(90, profile["s75"] + 12)))

        mask = cv2.inRange(
            hsv,
            np.array([35, s_low, 60], dtype=np.uint8),
            np.array([135, 255, 255], dtype=np.uint8),
        )
        masks.append(("neutral_light", _clean_cool_mask(mask), 0))

    else:
        # Saturated/chromatic background such as wood/red.
        # The historical cool range is normally meaningful because H is
        # trustworthy when saturation is not near zero.
        mask = cv2.inRange(
            hsv,
            np.array([35, 25, 60], dtype=np.uint8),
            np.array([135, 255, 255], dtype=np.uint8),
        )
        masks.append(("chromatic_cool", _clean_cool_mask(mask), 0))

    # Secondary stricter cool mask.
    strict = cv2.inRange(
        hsv,
        np.array([35, 40, 60], dtype=np.uint8),
        np.array([135, 255, 255], dtype=np.uint8),
    )
    masks.append(("strict_cool", _clean_cool_mask(strict), 1))

    # Historical mask is retained only as the LAST candidate source.
    legacy = cv2.inRange(
        hsv,
        np.array([35, 18, 60], dtype=np.uint8),
        np.array([135, 255, 255], dtype=np.uint8),
    )
    masks.append(("legacy_cool", _clean_cool_mask(legacy), 2))

    return profile, masks


def _rough_card_candidates(image_bgr):
    """
    Adaptive HSV scene preflight -> rough search seeds.

    Color remains only a rough locator.
    Final truth still requires the existing four independent edge lines and
    their theoretical intersections.
    """
    profile, seed_masks = _build_hsv_seed_masks(image_bgr)

    all_candidates = []

    for mask_name, cool, mask_priority in seed_masks:
        h, w = cool.shape

        n, labels, stats, _ = cv2.connectedComponentsWithStats(cool, 8)

        components = []

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

        candidates_for_mask = []

        for count in range(1, min(4, len(components) + 1)):
            for indices in itertools.combinations(
                range(len(components)),
                count,
            ):
                pts = np.vstack(
                    [
                        components[i][1].reshape(-1, 2)
                        for i in indices
                    ]
                ).astype(np.float32)

                hull = cv2.convexHull(pts)
                rect = cv2.minAreaRect(hull)

                (_, _), (rw, rh), _ = rect

                if min(rw, rh) < 20:
                    continue

                ratio = max(rw, rh) / min(rw, rh)
                area_ratio = (rw * rh) / float(h * w)

                is_normal_area = (
                    0.06 <= area_ratio <= NORMAL_MAX_AREA_RATIO
                )

                is_closeup_area = (
                    NORMAL_MAX_AREA_RATIO < area_ratio <= CLOSEUP_ROUGH_MAX_AREA_RATIO
                    and 1.25 <= ratio <= 1.95
                )

                if not (is_normal_area or is_closeup_area):
                    continue

                is_closeup_seed = bool(is_closeup_area)

                box = order_corners(
                    cv2.boxPoints(rect).astype(np.float32)
                )

                top_len = float(
                    np.linalg.norm(box[1] - box[0])
                )
                left_len = float(
                    np.linalg.norm(box[3] - box[0])
                )

                # Search only when the licence long edge is horizontal
                # for this orientation candidate.
                if top_len < left_len:
                    continue

                polygon_mask = np.zeros_like(cool)

                cv2.fillConvexPoly(
                    polygon_mask,
                    np.round(box).astype(np.int32),
                    255,
                )

                inside = polygon_mask > 0

                density = (
                    float(np.mean(cool[inside] > 0))
                    if inside.any()
                    else 0.0
                )

                ratio_error = (
                    abs(ratio - DL_ASPECT) / DL_ASPECT
                )

                historical_seed_score = (
                    ratio_error * 4.0
                    - density * 0.6
                )

                candidates_for_mask.append(
                    {
                        "seed_score": float(
                            historical_seed_score
                        ),
                        "rough_box": box,
                        "component_indices": indices,
                        "area_ratio": float(area_ratio),
                        "rough_ratio": float(ratio),
                        "cool_density": float(density),
                        "mask_name": mask_name,
                        "mask_priority": int(mask_priority),
                        "scene_profile": dict(profile),
                        "is_closeup_seed": is_closeup_seed,
                    }
                )

        candidates_for_mask.sort(
            key=lambda item: item["seed_score"]
        )

        normal_candidates = [
            c for c in candidates_for_mask
            if not c.get("is_closeup_seed")
        ]

        closeup_candidates = [
            c for c in candidates_for_mask
            if c.get("is_closeup_seed")
        ]

        if mask_priority == 0:
            keep_normal = 4
        elif mask_priority == 1:
            keep_normal = 2
        else:
            keep_normal = 1

        selected = normal_candidates[:keep_normal]

        # Always preserve at least the best plausible close-up seed.
        if closeup_candidates:
            selected.append(closeup_candidates[0])

        all_candidates.extend(selected)

    # Preferred scene mask first, then strict mask, then legacy.
    # Within each mask preserve the historical seed ranking.
    all_candidates.sort(
        key=lambda item: (
            item["mask_priority"],
            item["seed_score"],
        )
    )

    for candidate in all_candidates[:7]:
        candidate.setdefault("rough_locator", "HSV")
        candidate.setdefault("source_frame_rejected", False)
    return all_candidates[:7]


def _is_source_frame_candidate(box: np.ndarray, width: int, height: int) -> bool:
    """True when the rough box is effectively the photograph border, not the card."""
    xs = box[:, 0]
    ys = box[:, 1]
    margin = SOURCE_FRAME_MARGIN_PX
    return bool(
        float(xs.min()) <= margin
        and float(ys.min()) <= margin
        and float(xs.max()) >= width - margin
        and float(ys.max()) >= height - margin
    )


def _canny_rough_card_candidates(image_bgr):
    """
    Second rough locator: external physical-edge contour -> minAreaRect.

    Proposes candidate boxes only. Final truth remains _confirm_all_four_corners().
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    edges = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        np.ones((9, 9), np.uint8),
        iterations=2,
    )

    height, width = edges.shape
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[dict[str, Any]] = []
    source_frame_rejected = 0

    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
        contour_area = float(cv2.contourArea(contour))
        if contour_area < 0.04 * height * width:
            continue

        rect = cv2.minAreaRect(contour)
        (_center), (rw, rh), _angle = rect
        if min(rw, rh) < 20:
            continue

        ratio = max(rw, rh) / max(min(rw, rh), 1e-6)
        area_ratio = (rw * rh) / float(height * width)
        box = order_corners(cv2.boxPoints(rect).astype(np.float32))

        if _is_source_frame_candidate(box, width, height):
            source_frame_rejected += 1
            continue

        is_normal_area = 0.06 <= area_ratio <= NORMAL_MAX_AREA_RATIO
        is_closeup_area = (
            NORMAL_MAX_AREA_RATIO < area_ratio <= CLOSEUP_ROUGH_MAX_AREA_RATIO
            and 1.25 <= ratio <= 1.95
        )
        if not (is_normal_area or is_closeup_area):
            continue

        top_len = float(np.linalg.norm(box[1] - box[0]))
        left_len = float(np.linalg.norm(box[3] - box[0]))
        if top_len < left_len:
            continue

        ratio_error = abs(ratio - DL_ASPECT) / DL_ASPECT
        seed_score = ratio_error * 4.0 - area_ratio * 0.5

        candidates.append(
            {
                "seed_score": float(seed_score),
                "rough_box": box,
                "area_ratio": float(area_ratio),
                "rough_ratio": float(ratio),
                "is_closeup_seed": bool(is_closeup_area),
                "rough_locator": "CANNY",
                "source_frame_rejected": False,
                "mask_name": "canny_external",
                "mask_priority": 10,
            }
        )

    candidates.sort(key=lambda item: item["seed_score"])
    # Preserve best close-up alongside top normal seeds (same spirit as HSV keep).
    normal = [c for c in candidates if not c.get("is_closeup_seed")]
    closeup = [c for c in candidates if c.get("is_closeup_seed")]
    selected = normal[:4]
    if closeup:
        selected.append(closeup[0])
    for candidate in selected:
        candidate["source_frame_hits_in_locator"] = int(source_frame_rejected)
    return selected[:5]


def _search_confirmed_seed(
    image_bgr: np.ndarray,
    seed_fn,
    *,
    locator_name: str,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Run orientation loop + confirmer for one rough locator.

    Returns (best_normal, best_repaired). Repair is never applied to a
    candidate that already passed _confirm_all_four_corners().
    """
    best_normal: Optional[dict[str, Any]] = None
    best_repaired: Optional[dict[str, Any]] = None
    source_frame_hits = 0

    def _pack(orientation, orientation_rank, candidate_rank, seed, oriented, corners, diagnostics, support, repaired: bool):
        score = (
            seed["seed_score"]
            + diagnostics["ratio_error_percent"] / 50.0
            + diagnostics["max_angle_error_from_90"] / 100.0
            + orientation_rank * 0.002
            + candidate_rank * 0.001
        )
        return {
            "score": float(score),
            "orientation": orientation,
            "oriented": oriented,
            "seed_rank": candidate_rank,
            "corners": corners,
            "diagnostics": diagnostics,
            "support": support,
            "seed_mask": seed.get("mask_name"),
            "scene_profile": seed.get("scene_profile"),
            "is_closeup_seed": bool(seed.get("is_closeup_seed")),
            "rough_locator": locator_name,
            "rough_area_ratio": float(seed.get("area_ratio") or 0.0),
            "rough_ratio": float(seed.get("rough_ratio") or 0.0),
            "source_frame_rejected": False,
            "source_frame_hits": int(source_frame_hits),
            "edge_repair_applied": bool(repaired),
        }

    for orientation_rank, orientation in enumerate(ORIENTATION_ORDER):
        oriented = rotate_image(image_bgr, orientation)
        seeds = seed_fn(oriented)
        if seeds and "source_frame_hits_in_locator" in seeds[0]:
            source_frame_hits = max(
                source_frame_hits,
                int(seeds[0].get("source_frame_hits_in_locator") or 0),
            )

        for candidate_rank, seed in enumerate(seeds):
            corners, diagnostics, support = _confirm_all_four_corners(
                oriented,
                seed["rough_box"],
                is_closeup_seed=bool(seed.get("is_closeup_seed")),
            )
            if corners is not None:
                packed = _pack(
                    orientation, orientation_rank, candidate_rank, seed, oriented,
                    corners, diagnostics, support, False,
                )
                if best_normal is None or packed["score"] < best_normal["score"]:
                    best_normal = packed
                continue

            if best_normal is not None:
                continue

            repaired = _attempt_short_side_edge_repair(
                oriented,
                diagnostics,
                support,
                is_closeup_seed=bool(seed.get("is_closeup_seed")),
            )
            if not repaired or repaired.get("corners") is None:
                continue
            packed = _pack(
                orientation, orientation_rank, candidate_rank, seed, oriented,
                repaired["corners"], repaired["diagnostics"], support, True,
            )
            if best_repaired is None or packed["score"] < best_repaired["score"]:
                best_repaired = packed

    if best_normal is not None:
        best_normal["source_frame_hits"] = int(source_frame_hits)
    if best_repaired is not None:
        best_repaired["source_frame_hits"] = int(source_frame_hits)
    return best_normal, best_repaired


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


def _line_point_distance(line, pt) -> float:
    vx, vy, x0, y0 = (float(v) for v in line)
    relx = float(pt[0]) - x0
    rely = float(pt[1]) - y0
    return abs(vx * rely - vy * relx) / (float(np.hypot(vx, vy)) + 1e-6)


def _line_unit_tangent(line) -> np.ndarray:
    vx, vy = float(line[0]), float(line[1])
    length = float(np.hypot(vx, vy)) + 1e-6
    return np.array([vx / length, vy / length], dtype=np.float32)


def _evaluate_four_edge_geometry(
    image_bgr,
    corners: np.ndarray,
    edge_inliers: list[int],
    is_closeup_seed: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """Exact confirmer acceptance rules. Shared by the normal path and repair fallback."""
    h, w = image_bgr.shape[:2]
    corners = np.asarray(corners, dtype=np.float32).reshape(4, 2)

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

    max_polygon_area = (
        CLOSEUP_CONFIRM_MAX_AREA_RATIO
        if is_closeup_seed
        else NORMAL_MAX_AREA_RATIO
    )
    required_min_edge_inliers = (
        CLOSEUP_MIN_EDGE_INLIERS
        if is_closeup_seed
        else 50
    )

    confirmed = bool(
        all_inside
        and 0.08 <= polygon_area <= max_polygon_area
        and 1.25 <= ratio <= 1.95
        and max_angle_error <= 20.0
        and min(edge_inliers) >= required_min_edge_inliers
    )

    diagnostics = {
        "confirmed": confirmed,
        "all_four_corners_inside_source": all_inside,
        "edge_inliers": list(edge_inliers),
        "ratio": ratio,
        "ratio_error_percent": abs(ratio - DL_ASPECT) / DL_ASPECT * 100.0,
        "area_percent": polygon_area * 100.0,
        "corner_angles": angles,
        "max_angle_error_from_90": max_angle_error,
        "is_closeup_seed": bool(is_closeup_seed),
        "max_polygon_area_allowed": float(max_polygon_area),
        "required_min_edge_inliers": int(required_min_edge_inliers),
        "long_side_length": (top + bottom) / 2.0,
        "short_side_length": (left + right) / 2.0,
        "corners": {
            "TL": corners[0].tolist(),
            "TR": corners[1].tolist(),
            "BR": corners[2].tolist(),
            "BL": corners[3].tolist(),
        },
    }
    return confirmed, diagnostics

def _confirm_all_four_corners(
    image_bgr,
    rough_box,
    is_closeup_seed=False,
):
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
    confirmed, diagnostics = _evaluate_four_edge_geometry(
        image_bgr,
        corners,
        edge_inliers,
        is_closeup_seed=is_closeup_seed,
    )
    diagnostics["search_px"] = search_px

    return (corners if confirmed else None), diagnostics, (edge_points, edge_lines)


def _map_fitted_lines_to_ordered_sides(edge_lines, corners) -> dict[str, int]:
    """Assign each fitted line to TL-TR / TR-BR / BR-BL / BL-TL after order_corners."""
    corners = np.asarray(corners, dtype=np.float32).reshape(4, 2)
    sides = (
        ("top", corners[0], corners[1]),
        ("right", corners[1], corners[2]),
        ("bottom", corners[2], corners[3]),
        ("left", corners[3], corners[0]),
    )
    unused = list(range(len(edge_lines)))
    mapping: dict[str, int] = {}
    for name, p0, p1 in sides:
        best_i = min(
            unused,
            key=lambda i: (
                _line_point_distance(edge_lines[i], p0)
                + _line_point_distance(edge_lines[i], p1)
            ),
        )
        mapping[name] = best_i
        unused.remove(best_i)
    return mapping


def _expected_short_length(long_side_length: float) -> float:
    return float(long_side_length) / float(DL_ASPECT)


def _is_short_side_repairable(
    diagnostics: dict[str, Any],
    edge_lines,
    image_shape,
    is_closeup_seed: bool = False,
) -> tuple[bool, str, Optional[dict[str, Any]]]:
    """Conservative eligibility for one-side short-dimension repair. Does not search."""
    if not diagnostics or not edge_lines or len(edge_lines) != 4:
        return False, "need_four_fitted_lines", None
    inliers = diagnostics.get("edge_inliers") or []
    if len(inliers) != 4:
        return False, "need_four_edge_inliers", None
    corners_d = diagnostics.get("corners")
    if not isinstance(corners_d, dict) or not all(k in corners_d for k in ("TL", "TR", "BR", "BL")):
        return False, "need_four_intersections", None
    if not diagnostics.get("all_four_corners_inside_source"):
        return False, "corners_not_inside_source", None

    ratio = diagnostics.get("ratio")
    if ratio is None:
        return False, "missing_ratio", None
    if ratio <= SHORT_SIDE_REPAIR_RATIO_MIN:
        return False, "ratio_not_above_confirm_upper_bound", None
    if ratio > SHORT_SIDE_REPAIR_RATIO_MAX:
        return False, "ratio_absurdly_wide", None

    corners = np.array(
        [corners_d["TL"], corners_d["TR"], corners_d["BR"], corners_d["BL"]],
        dtype=np.float32,
    )
    long_len = float(diagnostics.get("long_side_length") or 0.0)
    short_len = float(diagnostics.get("short_side_length") or 0.0)
    if long_len < 1 or short_len < 1:
        return False, "missing_side_lengths", None
    expected_short = _expected_short_length(long_len)
    if expected_short <= 0:
        return False, "invalid_expected_short", None
    if short_len > expected_short * (1.0 - SHORT_SIDE_REPAIR_MIN_SHORTFALL_FRAC):
        return False, "short_side_not_sufficiently_truncated", None

    mapping = _map_fitted_lines_to_ordered_sides(edge_lines, corners)
    # Short dimension of a landscape ID-1 polygon is the gap between the two
    # long edges (top/bottom). Left/right are the physical short card edges.
    short_dim_names = ("top", "bottom")
    a_name, b_name = short_dim_names
    a_idx, b_idx = mapping[a_name], mapping[b_name]
    a_in, b_in = int(inliers[a_idx]), int(inliers[b_idx])
    if a_in <= b_in:
        suspect_name, trusted_name = a_name, b_name
        suspect_idx, trusted_idx = a_idx, b_idx
        suspect_in, trusted_in = a_in, b_in
    else:
        suspect_name, trusted_name = b_name, a_name
        suspect_idx, trusted_idx = b_idx, a_idx
        suspect_in, trusted_in = b_in, a_in

    other_idx = [i for i in range(4) if i != suspect_idx]
    other_inliers = [int(inliers[i]) for i in other_idx]
    if min(other_inliers) < SHORT_SIDE_REPAIR_OTHER_MIN_INLIERS:
        return False, "other_sides_lack_support", None
    if trusted_in - suspect_in < SHORT_SIDE_REPAIR_MIN_INLIER_GAP:
        return False, "suspect_not_clearly_weaker", None

    centroid = corners.mean(axis=0)
    side_pts = {
        "top": (corners[0], corners[1]),
        "right": (corners[1], corners[2]),
        "bottom": (corners[2], corners[3]),
        "left": (corners[3], corners[0]),
    }
    trusted_p0, trusted_p1 = side_pts[trusted_name]
    suspect_p0, suspect_p1 = side_pts[suspect_name]
    trusted_mid = (np.asarray(trusted_p0) + np.asarray(trusted_p1)) / 2.0
    suspect_mid = (np.asarray(suspect_p0) + np.asarray(suspect_p1)) / 2.0
    outward = suspect_mid - centroid
    outward_norm = float(np.linalg.norm(outward))
    if outward_norm < 1e-3:
        return False, "cannot_determine_outward_direction", None
    outward_u = outward / outward_norm

    # Parallel offset from the trusted opposite line, outward through the card.
    trusted_line = edge_lines[trusted_idx]
    tangent = _line_unit_tangent(trusted_line)
    n1 = np.array([-tangent[1], tangent[0]], dtype=np.float32)
    n2 = -n1
    n = n1 if float(np.dot(n1, outward_u)) >= float(np.dot(n2, outward_u)) else n2
    predicted_mid = trusted_mid + n * expected_short
    if float(np.linalg.norm(predicted_mid - centroid)) <= float(np.linalg.norm(suspect_mid - centroid)) + 1.0:
        return False, "predicted_shift_not_outward", None

    h, w = int(image_shape[0]), int(image_shape[1])
    margin = SHORT_SIDE_REPAIR_INSIDE_MARGIN_PX
    if not (margin <= float(predicted_mid[0]) <= w - margin and margin <= float(predicted_mid[1]) <= h - margin):
        return False, "predicted_edge_outside_source", None

    predicted_shift = float(np.linalg.norm(predicted_mid - suspect_mid))
    search_px = int(
        max(
            SHORT_SIDE_REPAIR_SEARCH_MIN_PX,
            min(SHORT_SIDE_REPAIR_SEARCH_MAX_PX, SHORT_SIDE_REPAIR_SEARCH_FRAC * expected_short),
        )
    )
    ctx = {
        "suspect_name": suspect_name,
        "trusted_name": trusted_name,
        "suspect_idx": int(suspect_idx),
        "trusted_idx": int(trusted_idx),
        "suspect_inliers": int(suspect_in),
        "expected_short_length": float(expected_short),
        "original_short_length": float(short_len),
        "original_long_length": float(long_len),
        "predicted_mid": predicted_mid.astype(np.float32),
        "predicted_tangent": tangent,
        "predicted_shift_px": predicted_shift,
        "search_band_px": search_px,
        "mapping": mapping,
        "is_closeup_seed": bool(is_closeup_seed),
    }
    return True, "short_side_truncated", ctx


def _attempt_short_side_edge_repair(
    image_bgr,
    diagnostics: dict[str, Any],
    support,
    is_closeup_seed: bool = False,
) -> Optional[dict[str, Any]]:
    """Search for a real missing short-dimension edge. Never synthesizes corners from aspect math."""
    repair_meta = {
        "edge_repair_attempted": True,
        "edge_repair_version": SHORT_SIDE_REPAIR_VERSION,
        "edge_repair_passed": False,
    }
    if not support or support[1] is None:
        repair_meta["edge_repair_reason"] = "no_fitted_lines"
        return {"corners": None, "diagnostics": {**(diagnostics or {}), **repair_meta}, "edge_lines": None}

    edge_points, edge_lines = support
    eligible, reason, ctx = _is_short_side_repairable(
        diagnostics,
        edge_lines,
        image_bgr.shape,
        is_closeup_seed=is_closeup_seed,
    )
    repair_meta["edge_repair_reason"] = reason
    if diagnostics:
        repair_meta["edge_repair_original_ratio"] = diagnostics.get("ratio")
    if not eligible or ctx is None:
        return {"corners": None, "diagnostics": {**(diagnostics or {}), **repair_meta}, "edge_lines": None}

    repair_meta.update(
        {
            "edge_repair_suspect_edge": ctx["suspect_name"],
            "edge_repair_expected_short_length": ctx["expected_short_length"],
            "edge_repair_original_short_length": ctx["original_short_length"],
            "edge_repair_predicted_shift_px": ctx["predicted_shift_px"],
            "edge_repair_search_band_px": ctx["search_band_px"],
        }
    )

    mid = ctx["predicted_mid"]
    tangent = ctx["predicted_tangent"]
    half = 0.5 * float(ctx["original_long_length"])
    p0 = mid - tangent * half
    p1 = mid + tangent * half
    points = _sample_boundary_points(image_bgr, p0, p1, int(ctx["search_band_px"]))
    new_line, new_inliers = _ransac_edge_line(points)
    required_min = CLOSEUP_MIN_EDGE_INLIERS if is_closeup_seed else 50
    if new_line is None or len(new_inliers) < required_min:
        repair_meta["edge_repair_reason"] = "no_replacement_physical_line"
        repair_meta["edge_repair_new_edge_inliers"] = int(len(new_inliers))
        return {"corners": None, "diagnostics": {**(diagnostics or {}), **repair_meta}, "edge_lines": None}

    repair_meta["edge_repair_new_edge_inliers"] = int(len(new_inliers))
    repaired_lines = list(edge_lines)
    repaired_inliers = list(diagnostics.get("edge_inliers") or [0, 0, 0, 0])
    repaired_lines[ctx["suspect_idx"]] = new_line
    repaired_inliers[ctx["suspect_idx"]] = int(len(new_inliers))

    raw_corners = [
        _intersect_fitted_lines(repaired_lines[3], repaired_lines[0]),
        _intersect_fitted_lines(repaired_lines[0], repaired_lines[1]),
        _intersect_fitted_lines(repaired_lines[1], repaired_lines[2]),
        _intersect_fitted_lines(repaired_lines[2], repaired_lines[3]),
    ]
    if any(point is None for point in raw_corners):
        repair_meta["edge_repair_reason"] = "repaired_intersections_unavailable"
        return {"corners": None, "diagnostics": {**(diagnostics or {}), **repair_meta}, "edge_lines": None}

    corners = order_corners(np.vstack(raw_corners).astype(np.float32))
    confirmed, new_diag = _evaluate_four_edge_geometry(
        image_bgr,
        corners,
        repaired_inliers,
        is_closeup_seed=is_closeup_seed,
    )
    new_diag.update(repair_meta)
    new_diag["edge_repair_final_ratio"] = new_diag.get("ratio")
    new_diag["edge_repair_final_angle_error"] = new_diag.get("max_angle_error_from_90")
    if not confirmed:
        if not new_diag.get("all_four_corners_inside_source"):
            new_diag["edge_repair_reason"] = "repaired_corners_outside_source"
        elif not (1.25 <= float(new_diag.get("ratio") or 0) <= 1.95):
            new_diag["edge_repair_reason"] = "repaired_ratio_invalid"
        elif float(new_diag.get("max_angle_error_from_90") or 99) > 20.0:
            new_diag["edge_repair_reason"] = "repaired_angles_invalid"
        else:
            new_diag["edge_repair_reason"] = "repaired_geometry_rejected"
        return {"corners": None, "diagnostics": new_diag, "edge_lines": repaired_lines}

    new_diag["edge_repair_passed"] = True
    new_diag["edge_repair_reason"] = "repaired_and_confirmed"
    return {
        "corners": corners,
        "diagnostics": new_diag,
        "edge_lines": repaired_lines,
        "edge_points": edge_points,
    }

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

    Rough locators (proposals only):
      1) HSV scene seeds (unchanged)
      2) if HSV never confirms -> Canny external-contour seeds
    Final authority remains _confirm_all_four_corners().
    """
    hsv_normal, hsv_repaired = _search_confirmed_seed(
        image_bgr,
        _rough_card_candidates,
        locator_name="HSV",
    )
    best = hsv_normal
    if best is None:
        canny_normal, canny_repaired = _search_confirmed_seed(
            image_bgr,
            _canny_rough_card_candidates,
            locator_name="CANNY",
        )
        best = canny_normal or hsv_repaired or canny_repaired
    # HSV normal never runs Canny. HSV-only repaired still allows Canny to
    # supply a normal confirm, which always outranks repair.

    if best is None:
        report = {
            "four_edges_confirmed": False,
            "status": "FOUR_CORNERS_NOT_CONFIRMED",
            "rough_locator_used": None,
            "hsv_locator_attempted": True,
            "canny_locator_attempted": True,
            "source_frame_rejected": False,
            "source_frame_margin_px": SOURCE_FRAME_MARGIN_PX,
            "preprocess_version": PREPROCESS_VERSION,
            "sandbox_base_sha256": SANDBOX_BASE_SHA256,
            "sandbox_refinement_sha256": SANDBOX_REFINEMENT_SHA256,
        }
        return _failure_result(image_bgr, report)

    oriented = best["oriented"]
    corners = best["corners"]
    diagnostics = best["diagnostics"]

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
        "seed_mask_used": best.get("seed_mask"),
        "hsv_scene_profile": best.get("scene_profile"),
        "rough_locator_used": best.get("rough_locator", "HSV"),
        "rough_area_ratio": best.get("rough_area_ratio"),
        "rough_ratio": best.get("rough_ratio"),
        "source_frame_rejected": bool(best.get("source_frame_hits", 0) > 0),
        "source_frame_hits": int(best.get("source_frame_hits") or 0),
        "source_frame_margin_px": SOURCE_FRAME_MARGIN_PX,
        "closeup_mode_used": bool(
            best.get("is_closeup_seed", False)
        ),
        "geometry_engine_version": GEOMETRY_ENGINE_VERSION,
        "corners_tl_tr_br_bl": corners.tolist(),
        "edge_inliers": diagnostics.get("edge_inliers"),
        "confirmed_polygon_area": (
            None
            if diagnostics.get("area_percent") is None
            else float(diagnostics["area_percent"]) / 100.0
        ),
        "final_ratio": diagnostics.get("ratio"),
        "max_angle_error": diagnostics.get("max_angle_error_from_90"),
        "confirm_diagnostics": diagnostics,
        "classification": "FOUR_CORNER_WARP",
        "correction_applied": "sandbox_four_corner_perspective_warp",
        "edge_repair_attempted": bool(diagnostics.get("edge_repair_attempted", False)),
        "edge_repair_applied": bool(best.get("edge_repair_applied")),
        "edge_repair_reason": diagnostics.get("edge_repair_reason"),
        "edge_repair_suspect_edge": diagnostics.get("edge_repair_suspect_edge"),
        "edge_repair_original_ratio": diagnostics.get("edge_repair_original_ratio"),
        "edge_repair_expected_short_length": diagnostics.get("edge_repair_expected_short_length"),
        "edge_repair_original_short_length": diagnostics.get("edge_repair_original_short_length"),
        "edge_repair_predicted_shift_px": diagnostics.get("edge_repair_predicted_shift_px"),
        "edge_repair_search_band_px": diagnostics.get("edge_repair_search_band_px"),
        "edge_repair_new_edge_inliers": diagnostics.get("edge_repair_new_edge_inliers"),
        "edge_repair_final_ratio": diagnostics.get("edge_repair_final_ratio"),
        "edge_repair_final_angle_error": diagnostics.get("edge_repair_final_angle_error"),
        "edge_repair_passed": bool(diagnostics.get("edge_repair_passed", False)),
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
        if best.get("edge_repair_applied"):
            suspect = str(diagnostics.get("edge_repair_suspect_edge") or "")
            side_idx = {"top": 0, "right": 1, "bottom": 2, "left": 3}.get(suspect)
            if side_idx is not None:
                p1 = tuple(q[side_idx])
                p2 = tuple(q[(side_idx + 1) % 4])
                cv2.line(dbg, p1, p2, (255, 255, 0), 7)
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
