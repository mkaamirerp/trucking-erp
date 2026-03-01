"""
Deskew, rotate (EXIF), normalize and sharpen DL images. Used after saving ORIG, before extraction.
Returns path to enhanced JPEG; on error returns original path unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Skip rotation for very small angles (noise)
DESKEW_ANGLE_THRESHOLD_DEG = 0.4


def _image_from_path(file_path: Path, content_type: str | None) -> "PIL.Image.Image":
    """Load image as PIL Image; if PDF, render first page. Same logic as dl_extract_pdf417."""
    ct = (content_type or "").strip().lower()
    if ct == "application/pdf" or (file_path.suffix and file_path.suffix.lower() == ".pdf"):
        import fitz  # pymupdf
        from PIL import Image

        doc = fitz.open(file_path)
        try:
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        finally:
            doc.close()
    from PIL import Image

    return Image.open(file_path).convert("RGB")


def _deskew_cv(img_rgb: "PIL.Image.Image") -> "PIL.Image.Image":
    """
    Detect skew angle from document edges/lines and rotate to correct.
    Uses OpenCV: grayscale -> threshold -> minAreaRect angle -> warpAffine.
    Returns rotated PIL Image (RGB); on any failure returns img_rgb unchanged.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        arr = np.array(img_rgb)
        if arr.size == 0:
            return img_rgb
        # OpenCV uses BGR
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        coords = cv2.findNonZero(thresh)
        if coords is None:
            return img_rgb
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        # Normalize OpenCV angle to a deskew angle (stable)
        # rect[-1] is typically in [-90, 0)
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < DESKEW_ANGLE_THRESHOLD_DEG:
            return img_rgb
        h, w = arr.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, -angle, 1.0)
        rotated = cv2.warpAffine(
            arr,
            M,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return Image.fromarray(rotated)
    except Exception as e:
        logger.debug("Deskew skipped: %s", e)
        return img_rgb


def enhance_dl_image(file_path: Path, content_type: str | None) -> tuple[Path, str]:
    """
    Rotate (EXIF), deskew, normalize and sharpen the DL image.
    Returns (enhanced_file_path, new_content_type).
    On any error: return (file_path, content_type) unchanged (never crash).
    """
    try:
        from PIL import Image, ImageFilter, ImageOps

        img = _image_from_path(file_path, content_type)
        # 1) Apply EXIF orientation so image is right-side-up
        img = ImageOps.exif_transpose(img)
        # 2) Deskew (OpenCV) so document is aligned
        img = _deskew_cv(img)
        # 3) Resize to max 1800px on longest side
        w, h = img.size
        max_side = 1800
        if max(w, h) > max_side:
            if w >= h:
                new_w = max_side
                new_h = int(round(h * max_side / w))
            else:
                new_h = max_side
                new_w = int(round(w * max_side / h))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        # 4) Sharpen
        img = img.filter(ImageFilter.SHARPEN).filter(ImageFilter.SHARPEN)
        out_path = file_path.parent / f"{file_path.stem}_enh.jpg"
        img.save(out_path, "JPEG", quality=92)
        return (out_path, "image/jpeg")
    except Exception as e:
        logger.warning("Enhance failed, using original: %s", e)
        return (file_path, content_type or "image/jpeg")
