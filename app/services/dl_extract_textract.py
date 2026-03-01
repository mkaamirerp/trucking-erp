"""
AWS Textract AnalyzeID for DL extraction. Fallback when PDF417 barcode fails.
Returns dl_extract_v1 shaped dict; on failure returns {"dl_extract_status": "FAILED", ...}.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# Map normalized Textract Type.Text (e.g. "first_name" from "First Name") to dl_extract_v1 field name
TEXTRACT_TYPE_TO_FIELD = {
    "first_name": "first_name",
    "last_name": "last_name",
    "date_of_birth": "dob",
    "document_number": "license_number",
    "expiration_date": "expiry_date",
    "date_of_issue": "issue_date",
    "issue_date": "issue_date",
    "state_name": "issuing_state",
    "address": "address",
    "class": "class",
    "restrictions": "restrictions",
    "endorsements": "endorsements",
    "gender": "sex",
    "sex": "sex",
    "height": "height",
}


def _ensure_image_bytes(file_path: Path, content_type: str | None) -> tuple[bytes, str]:
    """Return (image_bytes, content_type). If PDF, convert first page to JPEG."""
    ct = (content_type or "").strip().lower()
    if ct == "application/pdf" or (file_path.suffix and file_path.suffix.lower() == ".pdf"):
        import io
        import fitz  # pymupdf
        from PIL import Image

        doc = fitz.open(file_path)
        try:
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=92)
            return (buf.getvalue(), "image/jpeg")
        finally:
            doc.close()
    with open(file_path, "rb") as f:
        return (f.read(), ct or "image/jpeg")


def _parse_analyze_id_response(response: dict) -> dict[str, Any]:
    """Map AnalyzeID IdentityDocumentFields to dl_extract_v1 fields with confidence."""
    from app.services.dl_extract_stub import DL_EXTRACT_V1_FIELDS

    fields: dict[str, dict[str, Any]] = {k: {"value": "", "confidence": 0.0} for k in DL_EXTRACT_V1_FIELDS}
    confidences: list[float] = []

    docs = response.get("IdentityDocuments") or []
    if not docs:
        return {
            "version": "dl_extract_v1",
            "doc_type": "CDL_BACK",
            "overall_confidence": 0.0,
            "fields": fields,
            "warnings": [],
            "conflicts": [],
        }

    for field_item in docs[0].get("IdentityDocumentFields") or []:
        type_block = field_item.get("Type") or {}
        value_block = field_item.get("ValueDetection") or {}
        type_text = (type_block.get("Text") or "").strip().lower().replace(" ", "_")
        value_text = (value_block.get("Text") or "").strip()
        raw_confidence = value_block.get("Confidence")
        confidence = float(raw_confidence) / 100.0 if raw_confidence is not None else 0.0

        extract_key = TEXTRACT_TYPE_TO_FIELD.get(type_text)
        if extract_key and extract_key in fields:
            fields[extract_key] = {"value": value_text, "confidence": confidence}
            confidences.append(confidence)

    overall = sum(confidences) / len(confidences) if confidences else 0.0
    return {
        "version": "dl_extract_v1",
        "doc_type": "CDL_BACK",
        "overall_confidence": overall,
        "fields": fields,
        "warnings": [],
        "conflicts": [],
    }


async def extract_dl_with_textract(file_path: Path, content_type: str) -> dict[str, Any]:
    """
    Call AWS Textract AnalyzeID on the DL image.
    Returns dl_extract_v1 shaped dict on success, or {"dl_extract_status": "FAILED", ...} on failure.
    """
    import boto3

    try:
        image_bytes, used_content_type = _ensure_image_bytes(file_path, content_type)
        if not used_content_type.startswith("image/"):
            return {
                "dl_extract_status": "FAILED",
                "dl_extract_error": "Textract requires image (JPEG/PNG); conversion failed.",
            }
    except Exception as e:
        return {"dl_extract_status": "FAILED", "dl_extract_error": str(e)[:200]}

    try:
        client = boto3.client(
            "textract",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        response = client.analyze_id(DocumentPages=[{"Bytes": image_bytes}])
        return _parse_analyze_id_response(response)
    except Exception as e:
        return {"dl_extract_status": "FAILED", "dl_extract_error": str(e)[:200]}
