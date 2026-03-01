"""
PDF417 (AAMVA) extraction for CDL_BACK. Runs synchronously in upload request.
Reads saved file from storage, decodes barcode, parses AAMVA, returns dl_extract_v1 shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.dl_extract_stub import DL_EXTRACT_V1_FIELDS

# Confidence when data comes from barcode (high)
BARCODE_CONFIDENCE = 0.95


def _image_from_path(file_path: Path, content_type: str | None) -> "PIL.Image.Image":
    """Load image as PIL Image; if PDF, render first page."""
    ct = (content_type or "").strip().lower()
    if ct == "application/pdf" or (file_path.suffix and file_path.suffix.lower() == ".pdf"):
        import fitz  # pymupdf

        doc = fitz.open(file_path)
        try:
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            from PIL import Image

            return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        finally:
            doc.close()
    from PIL import Image

    return Image.open(file_path).convert("RGB")


def _decode_pdf417_from_image(pil_image: "PIL.Image.Image") -> str | None:
    """Decode first PDF417 barcode from image. Returns raw AAMVA string or None."""
    from pdf417decoder import PDF417Decoder

    decoder = PDF417Decoder(pil_image)
    if decoder.decode() <= 0:
        return None
    return decoder.barcode_data_index_to_string(0)


def _parse_aamva(raw: str) -> dict[str, Any]:
    """Parse AAMVA string; returns dict with keys first, last, state, license_number, expiry, dob, address, class, endorsements, restrictions."""
    from aamva import AAMVA

    parser = AAMVA(format=[2], strict=False)  # 2 = PDF417
    return parser.decode(raw)


def _date_to_str(d: Any) -> str | None:
    """Convert date object or None to YYYY-MM-DD."""
    if d is None:
        return None
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, str) and len(d) >= 10:
        return d[:10]
    return None


def _format_address(aamva: dict[str, Any]) -> str:
    """Build single address line from AAMVA address fields."""
    parts = []
    if aamva.get("address"):
        parts.append(str(aamva["address"]).strip())
    if aamva.get("address2"):
        parts.append(str(aamva["address2"]).strip())
    city = aamva.get("city")
    state = aamva.get("state")
    zip_ = aamva.get("ZIP")
    if city or state or zip_:
        loc = " ".join(filter(None, [str(x).strip() if x else "" for x in [city, state, zip_]]))
        if loc.strip():
            parts.append(loc.strip())
    return ", ".join(parts) if parts else ""


def _aamva_to_dl_extract_fields(aamva: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map AAMVA decode result to dl_extract_v1 fields dict."""
    first = (aamva.get("first") or "").strip()
    last = (aamva.get("last") or "").strip()
    dob = _date_to_str(aamva.get("dob"))
    license_number = (aamva.get("license_number") or "").strip()
    state = (aamva.get("state") or "").strip()
    expiry = _date_to_str(aamva.get("expiry"))
    address = _format_address(aamva)
    class_ = (aamva.get("class") or "").strip()
    endorsements = (aamva.get("endorsements") or "").strip()
    restrictions = (aamva.get("restrictions") or "").strip()

    fields: dict[str, dict[str, Any]] = {}
    for key in DL_EXTRACT_V1_FIELDS:
        value = ""
        if key == "first_name":
            value = first
        elif key == "last_name":
            value = last
        elif key == "dob":
            value = dob or ""
        elif key == "license_number":
            value = license_number
        elif key == "issuing_state":
            value = state
        elif key == "expiry_date":
            value = expiry or ""
        elif key == "address":
            value = address
        elif key == "class":
            value = class_
        elif key == "endorsements":
            value = endorsements
        elif key == "restrictions":
            value = restrictions
        fields[key] = {"value": value, "confidence": BARCODE_CONFIDENCE}
    return fields


def run_dl_extract_v1_from_back_file(file_path: Path, content_type: str | None) -> dict[str, Any]:
    """
    Decode PDF417 from CDL back image/PDF and return dl_extract_v1 result.
    On success: returns full dl_extract_v1 with fields populated.
    On failure: returns { "dl_extract_status": "FAILED", "dl_extract_error": "short message" }.
    """
    try:
        img = _image_from_path(file_path, content_type)
    except Exception as e:
        return {
            "dl_extract_status": "FAILED",
            "dl_extract_error": f"Could not read image: {e!s}"[:200],
        }

    raw = _decode_pdf417_from_image(img)
    if not raw or not raw.strip():
        return {
            "dl_extract_status": "FAILED",
            "dl_extract_error": "Barcode not found. Try a clearer photo or enter manually.",
        }

    try:
        aamva = _parse_aamva(raw)
    except Exception as e:
        return {
            "dl_extract_status": "FAILED",
            "dl_extract_error": f"Could not read license data: {e!s}"[:200],
        }

    fields = _aamva_to_dl_extract_fields(aamva)
    return {
        "version": "dl_extract_v1",
        "doc_type": "CDL_BACK",
        "overall_confidence": BARCODE_CONFIDENCE,
        "fields": fields,
        "warnings": [],
        "conflicts": [],
    }
