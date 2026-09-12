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

# Extract debug keys dropped when replacing a back image.
_PDF417_EXTRACT_META_KEYS = (
    "license_extract_status",
    "license_extract_debug",
    "license_extract_error",
)


def pdf417_enabled_for_doc_type(doc_type: str) -> bool:
    """PDF417 runs only on the licence back. Front is never a barcode source."""
    return doc_type == "CDL_BACK"


def clear_pdf417_extract_from_intake(intake: dict[str, Any]) -> dict[str, Any]:
    """Drop PDF417-sourced values and extract debug so a new back photo cannot keep stale fields."""
    out = dict(intake)
    user_edited = out.get("user_edited_fields") if isinstance(out.get("user_edited_fields"), dict) else {}
    sources = dict(out.get("field_sources") or {})

    drop_keys: set[str] = set(_PDF417_EXTRACT_META_KEYS)
    drop_keys.add("pdf417_text")
    for key, meta in list(sources.items()):
        if not (isinstance(meta, dict) and meta.get("source") == "pdf417"):
            continue
        if user_edited.get(key) is True:
            continue
        sources.pop(key, None)
        drop_keys.add(key)

    if "license_number" in drop_keys:
        drop_keys.add("driver_license_number")
    if "license_state" in drop_keys:
        drop_keys.add("license_region")
    if "license_class" in drop_keys:
        drop_keys.add("cdl_class")

    for key in drop_keys:
        if user_edited.get(key) is True:
            continue
        out.pop(key, None)

    if sources:
        out["field_sources"] = sources
    else:
        out.pop("field_sources", None)
    return out


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
    original_fallback_used: bool,
) -> dict[str, Any]:
    debug = dict(out.get("license_extract_debug") or {})
    debug["barcode_image_source"] = barcode_image_source
    debug["original_fallback_used"] = original_fallback_used
    # Processed is primary; this flag stays false so old debug readers are not inverted.
    debug["processed_fallback_used"] = False
    debug.pop("pdf417_text", None)
    debug.pop("raw_barcode_text", None)
    out["license_extract_debug"] = debug
    return out


def _original_back_storage_key(
    intake: dict[str, Any],
    *,
    explicit: str | None = None,
) -> str | None:
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    meta = (intake.get("files") or {}).get("CDL_BACK")
    if not isinstance(meta, dict):
        return None
    key = meta.get("storage_key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def _extract_succeeded(out: dict[str, Any]) -> bool:
    return out.get("license_extract_status") == "SUCCESS"


async def apply_stored_cdl_back_pdf417(
    intake: dict[str, Any],
    processed_storage_key: str | None,
    tenant_slug: str,
    *,
    original_storage_key: str | None = None,
) -> dict[str, Any]:
    """Decode the confirmed processed BACK JPEG first; original upload is PDF417 fallback only."""
    if not processed_storage_key:
        return _attach_source_debug(
            apply_pdf417_to_intake(
                intake, raw_barcode_text=None, technical_error="missing_processed_image"
            ),
            barcode_image_source="processed",
            original_fallback_used=False,
        )

    raw, meta, tech = await _decode_stored_key(processed_storage_key, tenant_slug)
    out = apply_pdf417_to_intake(
        intake, raw_barcode_text=raw, technical_error=tech, decode_meta=meta
    )
    if _extract_succeeded(out):
        return _attach_source_debug(
            out,
            barcode_image_source="processed",
            original_fallback_used=False,
        )

    original_key = _original_back_storage_key(intake, explicit=original_storage_key)
    if not original_key or original_key == processed_storage_key:
        return _attach_source_debug(
            out,
            barcode_image_source="processed",
            original_fallback_used=False,
        )

    raw, meta, tech = await _decode_stored_key(original_key, tenant_slug)
    fallback = apply_pdf417_to_intake(
        intake, raw_barcode_text=raw, technical_error=tech, decode_meta=meta
    )
    return _attach_source_debug(
        fallback,
        barcode_image_source="original",
        original_fallback_used=True,
    )
