"""CDL back PDF417 decode for applicant onboarding (storage path + intake merge).

Kept separate from the FastAPI router so unit tests can import without pulling auth/DB deps.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.services.dl_pdf417 import (
    PDF417_APPLICANT_THREAD_TIMEOUT_SEC,
    Pdf417DecodeMeta,
    apply_pdf417_to_intake,
    decode_pdf417_barcode_with_trace,
)


def pdf417_enabled_for_doc_type(doc_type: str) -> bool:
    """PDF417 runs only on the licence back. Front is never a barcode source."""
    return doc_type == "CDL_BACK"


async def _decode_stored_key(
    storage_key: str,
    tenant_slug: str,
) -> tuple[str | None, Pdf417DecodeMeta | None, str | None]:
    """Return ``(raw_text, meta, technical_error)`` for one stored applicant_dl key."""
    try:
        from app.core.storage import readable_path

        with readable_path(storage_key, "applicant_dl", tenant_slug) as path:
            if not path.is_file():
                return None, None, "source_file_missing"
            raw, meta = await asyncio.wait_for(
                asyncio.to_thread(
                    decode_pdf417_barcode_with_trace,
                    path,
                    mode="applicant_two_phase",
                ),
                timeout=PDF417_APPLICANT_THREAD_TIMEOUT_SEC,
            )
            return raw, meta, None
    except asyncio.TimeoutError:
        return None, None, "decode_timeout"
    except Exception as exc:  # noqa: BLE001 — surface class name only
        return None, None, type(exc).__name__


def _attach_source_debug(
    out: dict[str, Any],
    *,
    barcode_image_source: str,
    processed_fallback_used: bool,
) -> dict[str, Any]:
    debug = dict(out.get("license_extract_debug") or {})
    debug["barcode_image_source"] = barcode_image_source
    debug["processed_fallback_used"] = processed_fallback_used
    debug.pop("pdf417_text", None)
    debug.pop("raw_barcode_text", None)
    out["license_extract_debug"] = debug
    return out


async def apply_stored_cdl_back_pdf417(
    intake: dict[str, Any],
    storage_key: str | None,
    tenant_slug: str,
    *,
    processed_storage_key: str | None = None,
) -> dict[str, Any]:
    """Decode PDF417 from the original stored BACK upload (processed warp is fallback only)."""
    if not storage_key:
        return _attach_source_debug(
            apply_pdf417_to_intake(
                intake, raw_barcode_text=None, technical_error="missing_storage_key"
            ),
            barcode_image_source="original",
            processed_fallback_used=False,
        )

    raw, meta, tech = await _decode_stored_key(storage_key, tenant_slug)
    source = "original"
    fallback_used = False

    can_fallback = (
        not raw
        and tech != "decode_timeout"
        and bool(processed_storage_key)
        and processed_storage_key != storage_key
    )
    if can_fallback:
        assert processed_storage_key is not None
        raw2, meta2, tech2 = await _decode_stored_key(processed_storage_key, tenant_slug)
        fallback_used = True
        if raw2:
            raw, meta, tech = raw2, meta2, None
            source = "processed"
        elif tech is None:
            meta = meta2 or meta
        elif tech == "source_file_missing" and tech2 is None and not raw2:
            meta = meta2 or meta
            tech = None

    out = apply_pdf417_to_intake(
        intake, raw_barcode_text=raw, technical_error=tech, decode_meta=meta
    )
    return _attach_source_debug(
        out,
        barcode_image_source=source,
        processed_fallback_used=fallback_used,
    )
