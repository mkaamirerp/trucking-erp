"""CDL back PDF417 decode for applicant onboarding (storage path + intake merge).

Kept separate from the FastAPI router so unit tests can import without pulling auth/DB deps.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.services.dl_pdf417 import (
    PDF417_APPLICANT_THREAD_TIMEOUT_SEC,
    apply_pdf417_to_intake,
    decode_pdf417_barcode_with_trace,
)


async def apply_stored_cdl_back_pdf417(
    intake: dict[str, Any],
    storage_key: str | None,
    tenant_slug: str,
) -> dict[str, Any]:
    """Decode PDF417 from a stored applicant DL back image and merge into ``intake`` with ``license_extract_*``."""
    if not storage_key:
        return apply_pdf417_to_intake(
            intake, raw_barcode_text=None, technical_error="missing_storage_key"
        )
    try:
        from app.core.storage import readable_path

        with readable_path(storage_key, "applicant_dl", tenant_slug) as path:
            if not path.is_file():
                return apply_pdf417_to_intake(
                    intake, raw_barcode_text=None, technical_error="source_file_missing"
                )
            raw, meta = await asyncio.wait_for(
                asyncio.to_thread(
                    decode_pdf417_barcode_with_trace,
                    path,
                    mode="applicant_two_phase",
                ),
                timeout=PDF417_APPLICANT_THREAD_TIMEOUT_SEC,
            )
    except asyncio.TimeoutError:
        return apply_pdf417_to_intake(
            intake, raw_barcode_text=None, technical_error="decode_timeout"
        )
    except Exception as exc:  # noqa: BLE001 — surface class name only
        return apply_pdf417_to_intake(
            intake, raw_barcode_text=None, technical_error=type(exc).__name__
        )
    return apply_pdf417_to_intake(
        intake, raw_barcode_text=raw, technical_error=None, decode_meta=meta
    )
