"""Orchestrate applicant DL OpenCV preprocessing for onboarding upload."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def run_applicant_dl_opencv(image_path: str | Path, side: str = "CDL_FRONT") -> ApplicantDlPreprocessOutcome:
    """Run the exact frozen sandbox processor. `side` is accepted for router compatibility only."""
    _ = side
    result, corrected = process_applicant_dl_image_path(image_path)
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
