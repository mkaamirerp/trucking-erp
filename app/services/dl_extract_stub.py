"""Stub driver license extraction (dl_extract_v1). Runs synchronously; later replace with Lambda/Google."""

from __future__ import annotations

import json
from typing import Any

# Locked dl_extract_v1 field names for merge (see app.services.dl_merge.DL_EXTRACT_TO_INTAKE)
DL_EXTRACT_V1_FIELDS = (
    "first_name",
    "last_name",
    "dob",
    "license_number",
    "issuing_state",
    "expiry_date",
    "issue_date",
    "address",
    "class",
    "endorsements",
    "restrictions",
    "sex",
    "height",
    "conditions",
)


def run_dl_extract_v1_stub(doc_type: str) -> dict[str, Any]:
    """
    Return dl_extract_v1 shape for merge. Does not read file; stub values only.
    Used by POST /person-applications/{id}/dl-files. Replace with real OCR later.
    """
    fields = {}
    for f in DL_EXTRACT_V1_FIELDS:
        fields[f] = {"value": "", "confidence": 0.0}
    return {
        "version": "dl_extract_v1",
        "doc_type": doc_type,
        "overall_confidence": 0.0,
        "fields": fields,
        "warnings": [],
        "conflicts": [],
    }


def run_extraction_stub(submission_id: int, license_inputs: dict[str, Any]) -> dict[str, Any]:
    """
    Return a minimal ExtractionResult (schema_version dl_extract_v1) for UI prefill.
    Does not read files; used so upload → EXTRACTED flow works. Replace with real barcode/OCR later.
    """
    # Build inputs shape expected by contract (already have front/back from upload)
    # Minimal fields for prefill: first_name, last_name, license_number, issuing_region, expiry_date, etc.
    result: dict[str, Any] = {
        "schema_version": "dl_extract_v1",
        "submission_id": submission_id,
        "status": "EXTRACTED",
        "provider": {
            "name": "local",
            "engine_versions": {"barcode": "pdf417-decoder-stub", "ocr": "tesseract-stub"},
        },
        "inputs": license_inputs,
        "raw": {
            "barcode": {"present": False, "decode_ok": False, "symbology": "PDF417"},
            "ocr": {
                "front": {"text": "", "confidence_overall": 0.0},
                "back": {"text": "", "confidence_overall": 0.0},
            },
        },
        "fields": {
            "full_name": {"chosen": {"value": "", "source": "OCR_FRONT", "confidence": 0.0}, "candidates": []},
            "first_name": {"chosen": {"value": "", "source": "OCR_FRONT", "confidence": 0.0}, "candidates": []},
            "middle_name": {"chosen": {"value": "", "source": "OCR_FRONT", "confidence": 0.0}, "candidates": []},
            "last_name": {"chosen": {"value": "", "source": "OCR_FRONT", "confidence": 0.0}, "candidates": []},
            "license_number": {"chosen": {"value": "", "source": "BARCODE", "confidence": 0.0}, "candidates": []},
            "issuing_region": {"chosen": {"value": "", "source": "BARCODE", "confidence": 0.0}, "candidates": []},
            "country": {"chosen": {"value": "", "source": "INFERRED", "confidence": 0.0}, "candidates": []},
            "expiry_date": {"chosen": {"value": "", "source": "BARCODE", "confidence": 0.0}, "candidates": []},
            "address_street": {"chosen": {"value": "", "source": "BARCODE", "confidence": 0.0}, "candidates": []},
            "address_city": {"chosen": {"value": "", "source": "BARCODE", "confidence": 0.0}, "candidates": []},
            "address_region": {"chosen": {"value": "", "source": "BARCODE", "confidence": 0.0}, "candidates": []},
            "address_postal": {"chosen": {"value": "", "source": "BARCODE", "confidence": 0.0}, "candidates": []},
        },
        "diagnostics": {"warnings": [], "errors": [], "timing_ms": {"normalize": 0, "barcode": 0, "ocr": 0, "merge": 0}},
        "pii": {"contains_sensitive_pii": False, "sensitive_fields": []},
    }
    return result


def extraction_result_to_json(result: dict[str, Any]) -> str:
    return json.dumps(result)
