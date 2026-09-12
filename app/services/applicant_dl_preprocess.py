"""Orchestrate applicant DL OpenCV preprocessing for onboarding upload."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.services.applicant_dl_opencv import (
    PREPROCESS_VERSION,
    encode_processed_jpeg,
    process_applicant_dl_image_path,
    warp_confirmed_card_from_original,
)

# Temporary OpenCV detection working copy only — not the stored image size.
# Browser ingestion may keep sources up to 2400px; that file stays as stored.
# Only this working copy is scaled to 1544 when the long side exceeds 1544.
# 1544 is the validated OpenCV detection scale (IMG6446: Canny PASS at 1544,
# four-corner FAIL at direct 2400). Do not change without the frozen DL battery.
WORKING_COPY_MAX_SIDE = 1544
WORKING_COPY_PREP_VERSION = "2026-08-29-working-copy-v1"


@dataclass(frozen=True)
class ApplicantDlPreprocessOutcome:
    success: bool
    jpeg_bytes: bytes | None
    debug: dict[str, Any]
    classification: str
    correction_applied: str


def _load_bgr_with_exif(path: Path) -> np.ndarray | None:
    try:
        with Image.open(path) as pil_image:
            pil_image = ImageOps.exif_transpose(pil_image)
            rgb = pil_image.convert("RGB")
            return cv2.cvtColor(
                np.asarray(rgb),
                cv2.COLOR_RGB2BGR,
            )
    except Exception:
        return cv2.imread(str(path), cv2.IMREAD_COLOR)


def _prepare_working_copy(image_path: Path) -> tuple[Path, Path | None, dict[str, Any]]:
    """
    Build an EXIF-corrected, optionally downscaled temp JPEG for OpenCV.

    Does not mutate the stored original. No EDGE_WARP / STORAGE_NORMALIZE.
    """
    image = _load_bgr_with_exif(image_path)
    if image is None:
        return image_path, None, {
            "working_copy_prep_version": WORKING_COPY_PREP_VERSION,
            "working_copy_error": "load_failed",
        }

    height, width = image.shape[:2]
    meta: dict[str, Any] = {
        "working_copy_prep_version": WORKING_COPY_PREP_VERSION,
        "original_input_shape": {"width": int(width), "height": int(height)},
        "working_copy_downscaled": False,
    }

    long_side = max(height, width)
    if long_side > WORKING_COPY_MAX_SIDE:
        scale = WORKING_COPY_MAX_SIDE / long_side
        width = max(1, int(width * scale))
        height = max(1, int(height * scale))
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
        meta["working_copy_downscaled"] = True
        meta["working_copy_max_side"] = WORKING_COPY_MAX_SIDE

    meta["opencv_input_shape"] = {"width": int(width), "height": int(height)}

    fd, tmp = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    temp_path = Path(tmp)
    cv2.imwrite(str(temp_path), image)
    return temp_path, temp_path, meta


def _source_shape(image_bgr: np.ndarray | None) -> dict[str, int] | None:
    if image_bgr is None or image_bgr.size == 0:
        return None
    return {"width": int(image_bgr.shape[1]), "height": int(image_bgr.shape[0])}


def run_applicant_dl_opencv(image_path: str | Path, side: str = "CDL_FRONT") -> ApplicantDlPreprocessOutcome:
    """Detect on the 1544 working copy; warp the stored preview from original pixels."""
    _ = side
    source_path = Path(image_path)
    original_bgr = _load_bgr_with_exif(source_path)
    work_path, temp_path, prep_meta = _prepare_working_copy(source_path)
    working_bgr: np.ndarray | None = None
    try:
        working_bgr = cv2.imread(str(work_path), cv2.IMREAD_COLOR)
        result, working_warp = process_applicant_dl_image_path(work_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    debug = dict(result.report)
    debug.update(prep_meta)
    debug["preprocess_version"] = PREPROCESS_VERSION
    detection_shape = _source_shape(working_bgr) or prep_meta.get("opencv_input_shape")
    original_shape = _source_shape(original_bgr) or prep_meta.get("original_input_shape")
    if detection_shape:
        debug["detection_source_dimensions"] = detection_shape
    if original_shape:
        debug["original_source_dimensions"] = original_shape

    if not result.post_validation_pass:
        debug.setdefault("final_warp_source", None)
        return ApplicantDlPreprocessOutcome(
            success=False,
            jpeg_bytes=None,
            debug=debug,
            classification=result.geometry_class,
            correction_applied=result.correction_applied,
        )

    warped = working_warp
    debug["final_warp_source"] = "working_copy_pixels"
    debug["final_processed_dimensions"] = {
        "width": int(working_warp.shape[1]),
        "height": int(working_warp.shape[0]),
    }
    corners = result.report.get("corners_tl_tr_br_bl")
    orientation = str(result.report.get("orientation_used") or "original")
    if original_bgr is not None and working_bgr is not None and corners is not None:
        try:
            warped, warp_meta = warp_confirmed_card_from_original(
                original_bgr,
                working_bgr,
                np.asarray(corners, dtype=np.float32),
                orientation,
            )
            debug.update(warp_meta)
        except Exception as exc:
            debug["warp_from_original_error"] = type(exc).__name__
            debug["final_warp_source"] = "working_copy_pixels"

    return ApplicantDlPreprocessOutcome(
        success=True,
        jpeg_bytes=encode_processed_jpeg(warped),
        debug=debug,
        classification=result.geometry_class,
        correction_applied=result.correction_applied,
    )
