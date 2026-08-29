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
)


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


def _opencv_input_path(image_path: Path) -> tuple[Path, Path | None]:
    """Write EXIF-corrected pixels for the frozen path-based OpenCV processor."""
    image = _load_bgr_with_exif(image_path)
    if image is None:
        return image_path, None

    fd, tmp = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    temp_path = Path(tmp)
    cv2.imwrite(str(temp_path), image)
    return temp_path, temp_path


def run_applicant_dl_opencv(image_path: str | Path, side: str = "CDL_FRONT") -> ApplicantDlPreprocessOutcome:
    """Run the exact frozen sandbox processor. `side` is accepted for router compatibility only."""
    _ = side
    source_path = Path(image_path)
    work_path, temp_path = _opencv_input_path(source_path)
    try:
        result, corrected = process_applicant_dl_image_path(work_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    debug = dict(result.report)
    debug["preprocess_version"] = PREPROCESS_VERSION

    if not result.post_validation_pass:
        return ApplicantDlPreprocessOutcome(
            success=False,
            jpeg_bytes=None,
            debug=debug,
            classification=result.geometry_class,
            correction_applied=result.correction_applied,
        )

    return ApplicantDlPreprocessOutcome(
        success=True,
        jpeg_bytes=encode_processed_jpeg(corrected),
        debug=debug,
        classification=result.geometry_class,
        correction_applied=result.correction_applied,
    )
