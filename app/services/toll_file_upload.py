"""Unified Toll file upload: detect kind, require provider, then gate on Toll evidence."""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.toll import PDF_PROFILE_EZPASS_WVPA_MONTHLY
from app.services.toll_pdf_review import persist_toll_pdf_file
from app.services.toll_provider_catalog import (
    INTAKE_NOT_WIRED,
    get_upload_provider,
    upload_provider_codes,
)
from app.services.toll_wvpa_pdf import TollPdfIntakeError

PROVIDER_EZPASS: Final[str] = "EZPASS"
PROVIDER_PREPASS: Final[str] = "PREPASS"
TOLL_UPLOAD_PROVIDERS: Final[frozenset[str]] = upload_provider_codes()

KIND_PDF: Final[str] = "PDF"
KIND_CSV: Final[str] = "CSV"
KIND_IMAGE: Final[str] = "IMAGE"
KIND_OTHER: Final[str] = "OTHER"

NOT_A_TOLL_FILE: Final[str] = "This is not a Toll file"


class TollFileUploadError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def classify_toll_upload_kind(
    *,
    filename: str,
    body: bytes,
    content_type: str | None,
) -> str:
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    name = (filename or "").lower()
    if body.startswith(b"%PDF"):
        return KIND_PDF
    if body.startswith(b"\xff\xd8\xff") or body.startswith(b"\x89PNG\r\n\x1a\n") or body.startswith(b"GIF8"):
        return KIND_IMAGE
    if name.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".heic")):
        return KIND_IMAGE
    if declared.startswith("image/"):
        return KIND_IMAGE
    if name.endswith(".pdf") or declared == "application/pdf":
        return KIND_OTHER
    if name.endswith(".csv") or declared in {"text/csv", "application/csv"}:
        return KIND_CSV
    head = body[:2048]
    if b"\x00" not in head:
        text = head.decode("utf-8", errors="ignore")
        if "," in text and ("\n" in text or "\r" in text):
            return KIND_CSV
    return KIND_OTHER


def _require_provider(provider_code: str | None):
    selected = (provider_code or "").strip().upper()
    if not selected:
        raise TollFileUploadError("TOLL_PROVIDER_REQUIRED", "Choose a provider before uploading")
    row = get_upload_provider(selected)
    if row is None:
        raise TollFileUploadError("TOLL_PROVIDER_UNKNOWN", "Unknown Toll provider")
    return row


async def ingest_toll_upload(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    filename: str,
    body: bytes,
    content_type: str | None,
    provider_code: str | None,
    created_by: str | None,
) -> dict[str, Any]:
    provider = _require_provider(provider_code)
    kind = classify_toll_upload_kind(filename=filename, body=body, content_type=content_type)
    if provider.intake_status == INTAKE_NOT_WIRED:
        raise TollFileUploadError(
            "TOLL_PROVIDER_NOT_IMPLEMENTED",
            f"{provider.provider_name} file intake is not wired yet",
        )
    if kind == KIND_CSV:
        raise TollFileUploadError(
            "TOLL_CSV_NOT_WIRED",
            "CSV intake will be wired later. Upload an E-ZPass PDF.",
        )
    if kind == KIND_IMAGE:
        raise TollFileUploadError("TOLL_NOT_A_TOLL_FILE", NOT_A_TOLL_FILE)
    if kind != KIND_PDF:
        raise TollFileUploadError("TOLL_NOT_A_TOLL_FILE", NOT_A_TOLL_FILE)
    try:
        result = await persist_toll_pdf_file(
            db,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            filename=filename,
            body=body,
            content_type=content_type,
            created_by=created_by,
            profile_code=PDF_PROFILE_EZPASS_WVPA_MONTHLY,
            provider_code=provider.provider_code,
        )
    except TollPdfIntakeError as exc:
        if exc.code in {
            "TOLL_PDF_PROFILE_MISMATCH",
            "TOLL_PDF_UNREADABLE",
            "TOLL_PDF_NOT_PDF",
            "TOLL_PDF_EMPTY",
        }:
            raise TollFileUploadError("TOLL_NOT_A_TOLL_FILE", NOT_A_TOLL_FILE) from exc
        raise TollFileUploadError(exc.code, exc.message, http_status=exc.http_status) from exc
    payload = result.as_api_dict()
    payload["detected_kind"] = KIND_PDF
    payload["provider_code"] = provider.provider_code
    return payload
