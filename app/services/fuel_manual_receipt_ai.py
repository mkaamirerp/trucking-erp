"""OpenAI vision/text extraction for manual fuel receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.openai_chat_json_schema import openai_chat_json_schema_content

_CONTRACT_PATH = (
    Path(__file__).resolve().parents[1] / "contracts" / "manual_fuel_receipt_extraction_v1.json"
)

_SYSTEM = """You extract fields from a single fuel receipt for trucking fleet manual entry.

Rules:
- Return only values visibly printed on the receipt. Use null when not evidenced.
- Do NOT infer currency from US/Canada address alone; set currency only if USD/CAD (or $ with clear label) is printed.
- If multiple per-unit prices are printed (e.g. 2.699 and 2.709 per litre), list ALL in unit_price_candidates and leave unit_price null.
- If vehicle/unit id is masked (XXXX, ***, etc.), put it in vehicle_id, not unit_number.
- Preserve tax-inclusive language in tax_included_note. Printed Sales Tax 0.00 does NOT mean no tax when a note says tax is included in price.
- Do not invent GST/HST/PST/QST amounts unless explicitly broken out on the receipt.
- Use decimal strings without currency symbols for money and quantity fields.
- Dates: prefer ISO YYYY-MM-DD.
"""


def _load_schema() -> tuple[dict[str, Any], str]:
    payload = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
    return payload["schema"], payload["name"]


def openai_configured() -> bool:
    return bool((settings.openai_api_key or "").strip())


async def extract_receipt_fields_via_openai(
    file_bytes: bytes,
    filename: str | None,
    ocr_text: str | None = None,
) -> dict[str, Any]:
    """Call OpenAI with receipt image/PDF + optional OCR hint; return extraction dict."""
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    schema, schema_name = _load_schema()
    model = (settings.openai_extraction_model or "gpt-4o-mini").strip() or "gpt-4o-mini"
    hint = (ocr_text or "").strip()
    user_text = (
        "Extract fuel receipt fields from the attached receipt image or document. "
        "Output JSON matching the schema."
    )
    if hint:
        user_text += "\n\nOCR text (untrusted hint, receipt image/document is primary):\n" + hint[:12000]

    name = filename or "receipt.jpg"
    obj = await openai_chat_json_schema_content(
        api_key=api_key,
        model=model,
        system=_SYSTEM,
        user_text=user_text,
        schema=schema,
        schema_name=schema_name,
        input_file_bytes=file_bytes,
        input_filename=name,
    )
    return _normalize_ai_payload(obj)


def _normalize_ai_payload(obj: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in obj.items():
        if val is None:
            continue
        if key == "unit_price_candidates" and isinstance(val, list):
            out[key] = [str(x).strip() for x in val if str(x).strip()]
            continue
        if isinstance(val, str):
            text = val.strip()
            if text:
                out[key] = text
        elif isinstance(val, (int, float)):
            out[key] = str(val)
    return out
