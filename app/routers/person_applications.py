"""
Person-application (applicant) API: GET by token, GET by id, POST dl-files, reextract.
Tenant from onboarding token only (platform DB resolves token → tenant_id, application_id).
All application/file/merge/reextract logic uses tenant DB only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.storage import (
    ONBOARDING_LICENSE_ACCEPT,
    delete_onboarding_license,
    get_onboarding_license_path,
    save_onboarding_license_from_path,
    save_onboarding_license_local,
)
from app.deps.tenant_db import get_tenant_db
from app.models.person_application import PersonApplication
from app.models.person_application_file import PersonApplicationFile
from app.schemas.driver_onboarding import DriverOnboardingStatus
from app.services.dl_enhance import enhance_dl_image
from app.services.dl_extract_pdf417 import run_dl_extract_v1_from_back_file
from app.services.dl_extract_stub import run_dl_extract_v1_stub
from app.services.dl_extract_textract import extract_dl_with_textract
from app.services.dl_merge import apply_dl_extract_to_intake
from app.services.onboarding_token_resolver import set_applicant_context_from_token

router = APIRouter(prefix="/api/v1/person-applications", tags=["person-applications"])

DOC_TYPES = ("CDL_FRONT", "CDL_BACK")
THUMBNAIL_DOC_TYPES = ("CDL_FRONT", "CDL_BACK", "CDL_FRONT_ENH", "CDL_BACK_ENH")


# ---------- Token resolution: platform DB only; sets request.state.tenant_id and onboarding_application_id ----------


async def applicant_context_from_query(
    request: Request,
    token: str = Query(..., alias="token", description="Onboarding invite token"),
    platform_db: AsyncSession = Depends(get_db),
) -> tuple[int, int]:
    """Resolve token via platform DB, set request.state, return (tenant_id, application_id). For GET /by-token."""
    return await set_applicant_context_from_token(request, token, platform_db)


async def applicant_context_from_header(
    request: Request,
    x_onboarding_token: str = Header(..., alias="X-Onboarding-Token"),
    platform_db: AsyncSession = Depends(get_db),
) -> tuple[int, int]:
    """Resolve token via platform DB, set request.state. For GET /{id}, POST dl-files, reextract."""
    if not (x_onboarding_token and x_onboarding_token.strip()):
        raise HTTPException(status_code=401, detail="X-Onboarding-Token required")
    return await set_applicant_context_from_token(request, x_onboarding_token.strip(), platform_db)


# ---------- Response models ----------


class ApplicationOut(BaseModel):
    id: int
    tenant_id: int
    status: str
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    intake_payload: dict | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DlFileUploadResponse(BaseModel):
    file_id: int
    dl_extract_status: str
    license_extract_status: str
    intake_payload: dict | None


# ---------- Serialize application for API ----------


def _serialize_app(app: PersonApplication) -> dict:
    return {
        "id": app.id,
        "tenant_id": app.tenant_id,
        "status": app.status,
        "first_name": app.first_name,
        "last_name": app.last_name,
        "email": app.email,
        "phone": app.phone,
        "intake_payload": app.intake_payload,
        "created_at": app.created_at,
        "updated_at": app.updated_at,
    }


# ---------- GET by token (applicant: load application when landing with invite link) ----------


@router.get("/by-token", response_model=dict)
async def get_application_by_token_endpoint(
    request: Request,
    _ctx: tuple[int, int] = Depends(applicant_context_from_query),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Return application for the given onboarding token. Tenant from token (platform DB resolution only)."""
    tenant_id = request.state.tenant_id
    application_id = request.state.onboarding_application_id
    app = await db.scalar(
        select(PersonApplication).where(
            PersonApplication.tenant_id == tenant_id,
            PersonApplication.id == application_id,
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return _serialize_app(app)


# ---------- GET by appId (applicant with token header) ----------


@router.get("/{app_id}", response_model=dict)
async def get_application(
    app_id: int,
    request: Request,
    _ctx: tuple[int, int] = Depends(applicant_context_from_header),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Return application by id. Authorized by X-Onboarding-Token; tenant from token."""
    if request.state.onboarding_application_id != app_id:
        raise HTTPException(status_code=403, detail="Token does not match application")
    app = await db.scalar(
        select(PersonApplication).where(
            PersonApplication.tenant_id == request.state.tenant_id,
            PersonApplication.id == app_id,
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return _serialize_app(app)


# ---------- POST dl-files: discard old, save new, sync extract, merge ----------


def _check_mime(file: UploadFile) -> None:
    ct = (file.content_type or "").strip().lower()
    if ct not in ONBOARDING_LICENSE_ACCEPT and not ct.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ct}. Allowed: jpeg, png, heic, heif, pdf",
        )


def _validate_extraction(extract_result: dict) -> tuple[bool, str]:
    """
    Returns (is_valid, error_message).
    Valid means ALL required fields are present and non-empty:
    first_name, last_name, license_number, expiry_date.
    """
    fields = extract_result.get("fields") or {}
    required = ["first_name", "last_name", "license_number", "expiry_date"]
    for f in required:
        val = (fields.get(f) or {}).get("value", "")
        if not val or not str(val).strip():
            return False, f"Could not read {f.replace('_', ' ')}. Please upload a clearer photo of the back of your license."
    return True, ""


def _ensure_intake_files_structure(payload: dict, doc_type: str, file_id: int, storage_key: str) -> dict:
    """Ensure intake_payload has files + license_extract + extraction.license; set files[doc_type] for upload."""
    if "files" not in payload:
        payload["files"] = {}
    payload["files"][doc_type] = {
        "file_id": file_id,
        "upload_status": "UPLOADED",
        "enhance_status": "PENDING",
        "storage_key": storage_key,
        "thumbnail_url": None,
    }
    if "license_extract_status" not in payload:
        payload["license_extract_status"] = "NOT_STARTED"
    if "license_extract_error" not in payload:
        payload["license_extract_error"] = None
    if "extraction" not in payload:
        payload["extraction"] = {}
    if "license" not in payload["extraction"]:
        payload["extraction"]["license"] = {"status": "NOT_STARTED", "confidence": None, "updated_at": None}
    return payload


@router.post("/{app_id}/dl-files", response_model=DlFileUploadResponse)
async def upload_dl_file(
    request: Request,
    app_id: int,
    doc_type: Literal["CDL_FRONT", "CDL_BACK"] = Form(...),
    file: UploadFile = File(...),
    _ctx: tuple[int, int] = Depends(applicant_context_from_header),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Upload one DL (front or back). Save ORIG → enhance → extract (back only: PDF417 then Textract) → validate → merge."""
    if request.state.onboarding_application_id != app_id:
        raise HTTPException(status_code=403, detail="Token does not match application")
    tenant_id = request.state.tenant_id
    app = await db.scalar(
        select(PersonApplication).where(
            PersonApplication.tenant_id == tenant_id,
            PersonApplication.id == app_id,
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    _check_mime(file)

    # 1) Discard old: this doc_type and its _ENH variant
    enh_type = "CDL_FRONT_ENH" if doc_type == "CDL_FRONT" else "CDL_BACK_ENH"
    old_files = (
        await db.execute(
            select(PersonApplicationFile).where(
                PersonApplicationFile.tenant_id == tenant_id,
                PersonApplicationFile.application_id == app_id,
                PersonApplicationFile.doc_type.in_([doc_type, enh_type]),
            )
        )
    ).scalars().all()
    for f in old_files:
        delete_onboarding_license(f.storage_key)
        await db.delete(f)
    await db.flush()

    # 2) Save new file (ORIG)
    side = "FRONT" if doc_type == "CDL_FRONT" else "BACK"
    stored = await save_onboarding_license_local(file, tenant_id, app_id, side)
    rec = PersonApplicationFile(
        tenant_id=tenant_id,
        application_id=app_id,
        doc_type=doc_type,
        storage_key=stored.storage_key,
        original_filename=stored.original_filename,
        content_type=stored.content_type,
        size_bytes=stored.file_size_bytes,
        sha256=stored.sha256,
        is_active=True,
    )
    db.add(rec)
    await db.flush()

    if app.intake_payload is None:
        app.intake_payload = {}
    payload = dict(app.intake_payload)
    payload = _ensure_intake_files_structure(payload, doc_type, rec.id, stored.storage_key)
    payload["license_extract_status"] = "RUNNING"
    app.intake_payload = payload

    # 3) Enhance image
    license_path = get_onboarding_license_path(stored.storage_key)
    enh_path, enh_content_type = enhance_dl_image(license_path, stored.content_type)
    enh_stored = None
    if enh_path != license_path:
        enh_side = "FRONT_ENH" if doc_type == "CDL_FRONT" else "BACK_ENH"
        enh_stored = save_onboarding_license_from_path(enh_path, tenant_id, app_id, enh_side, enh_content_type)
        rec_enh = PersonApplicationFile(
            tenant_id=tenant_id,
            application_id=app_id,
            doc_type=enh_type,
            storage_key=enh_stored.storage_key,
            original_filename=enh_stored.original_filename,
            content_type=enh_stored.content_type,
            size_bytes=enh_stored.file_size_bytes,
            sha256=enh_stored.sha256,
            is_active=True,
        )
        db.add(rec_enh)
        await db.flush()
        payload["files"][doc_type]["enhance_status"] = "SUCCESS"
        payload["files"][doc_type]["enh_file_id"] = rec_enh.id
    else:
        payload["files"][doc_type]["enhance_status"] = "FAILED"
    app.intake_payload = payload

    # 4) Extract only for CDL_BACK (PDF417 first; Textract fallback when AWS is available)
    if doc_type == "CDL_BACK":
        extract_path = get_onboarding_license_path(enh_stored.storage_key) if enh_stored else license_path
        extract_content_type = (enh_stored.content_type if enh_stored else stored.content_type) or "image/jpeg"
        result = run_dl_extract_v1_from_back_file(Path(extract_path), extract_content_type)
        if result.get("dl_extract_status") == "FAILED":
            try:
                result = await extract_dl_with_textract(Path(extract_path), extract_content_type)
            except Exception:
                result = {
                    "dl_extract_status": "FAILED",
                    "dl_extract_error": "Barcode not readable. Please upload a clearer photo of the back of your license. (OCR available when AWS is configured.)",
                }
        rec.extract_payload = result

        if result.get("dl_extract_status") == "FAILED" or "dl_extract_error" in result:
            payload["license_extract_status"] = "NEEDS_REUPLOAD"
            payload["license_extract_error"] = result.get(
                "dl_extract_error",
                "Barcode not readable and OCR failed. Please upload a clearer photo of the back of your license.",
            )[:500]
            app.intake_payload = payload
        else:
            valid, err_msg = _validate_extraction(result)
            if valid:
                apply_dl_extract_to_intake(app, result)
                # Update in place so we keep the merged fields from apply_dl_extract_to_intake
                app.intake_payload["license_extract_status"] = "SUCCESS"
                app.intake_payload["license_extract_error"] = None
                app.intake_payload.setdefault("extraction", {})["license"] = {
                    "status": "SUCCESS",
                    "confidence": result.get("overall_confidence"),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                payload["license_extract_status"] = "NEEDS_REVIEW"
                payload["license_extract_error"] = err_msg[:500]
                app.intake_payload = payload
    else:
        payload["license_extract_status"] = "NOT_STARTED"
        app.intake_payload = payload

    await db.commit()
    await db.refresh(app)
    await db.refresh(rec)

    license_status = (app.intake_payload or {}).get("license_extract_status", "NOT_STARTED")
    dl_status = (app.intake_payload or {}).get("dl_extract_status", "PENDING")
    return DlFileUploadResponse(
        file_id=rec.id,
        dl_extract_status=dl_status,
        license_extract_status=license_status,
        intake_payload=app.intake_payload,
    )


# ---------- POST reextract ----------


@router.post("/{app_id}/files/{file_id}/reextract", response_model=DlFileUploadResponse)
async def reextract_dl_file(
    app_id: int,
    file_id: int,
    request: Request,
    _ctx: tuple[int, int] = Depends(applicant_context_from_header),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Re-run extraction on an existing file and re-apply merge. Token required."""
    if request.state.onboarding_application_id != app_id:
        raise HTTPException(status_code=403, detail="Token does not match application")
    tenant_id = request.state.tenant_id
    app = await db.scalar(
        select(PersonApplication).where(
            PersonApplication.tenant_id == tenant_id,
            PersonApplication.id == app_id,
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    file_row = await db.scalar(
        select(PersonApplicationFile).where(
            PersonApplicationFile.tenant_id == tenant_id,
            PersonApplicationFile.application_id == app_id,
            PersonApplicationFile.id == file_id,
        )
    )
    if not file_row:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        doc_type = file_row.doc_type or "CDL_FRONT"
        if doc_type == "CDL_BACK":
            license_path = get_onboarding_license_path(file_row.storage_key)
            result = run_dl_extract_v1_from_back_file(license_path, file_row.content_type)
            file_row.extract_payload = result
            if result.get("dl_extract_status") == "FAILED":
                if app.intake_payload is None:
                    app.intake_payload = {}
                app.intake_payload["dl_extract_status"] = "FAILED"
                app.intake_payload["dl_extract_error"] = result.get("dl_extract_error", "Barcode not found.")[:500]
            else:
                apply_dl_extract_to_intake(app, result)
        else:
            result = run_dl_extract_v1_stub(doc_type)
            file_row.extract_payload = result
            apply_dl_extract_to_intake(app, result)
    except Exception as e:
        if app.intake_payload is None:
            app.intake_payload = {}
        app.intake_payload["dl_extract_status"] = "FAILED"
        app.intake_payload["dl_extract_error"] = str(e)[:500]
    await db.commit()
    await db.refresh(app)

    status_val = (app.intake_payload or {}).get("dl_extract_status", "FAILED")
    license_status = (app.intake_payload or {}).get("license_extract_status", "NOT_STARTED")
    return DlFileUploadResponse(
        file_id=file_row.id,
        dl_extract_status=status_val,
        license_extract_status=license_status,
        intake_payload=app.intake_payload,
    )


# ---------- GET thumbnail (applicant: show uploaded license image) ----------


@router.get("/{app_id}/files/{file_id}/thumbnail")
async def get_file_thumbnail(
    app_id: int,
    file_id: int,
    request: Request,
    _ctx: tuple[int, int] = Depends(applicant_context_from_header),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Return the image file for a DL upload. Token required. Only CDL_FRONT, CDL_BACK, CDL_FRONT_ENH, CDL_BACK_ENH."""
    if request.state.onboarding_application_id != app_id:
        raise HTTPException(status_code=403, detail="Token does not match application")
    file_row = await db.scalar(
        select(PersonApplicationFile).where(
            PersonApplicationFile.tenant_id == request.state.tenant_id,
            PersonApplicationFile.application_id == app_id,
            PersonApplicationFile.id == file_id,
        )
    )
    if not file_row or file_row.doc_type not in THUMBNAIL_DOC_TYPES:
        raise HTTPException(status_code=404, detail="File not found")
    path = get_onboarding_license_path(file_row.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = file_row.content_type or "image/jpeg"
    return FileResponse(path, media_type=media_type)


# ---------- Sync intake_payload to model columns (for admin display) ----------


def _sync_intake_to_model(app: PersonApplication, payload: dict | None) -> None:
    """Write intake_payload fields to PersonApplication columns so admin views show data."""
    if not payload:
        return
    if payload.get("first_name") is not None:
        app.first_name = str(payload["first_name"]).strip() or None
    if payload.get("last_name") is not None:
        app.last_name = str(payload["last_name"]).strip() or None
    if payload.get("email") is not None:
        app.email = str(payload["email"]).strip() or None
    if payload.get("phone") is not None:
        app.phone = str(payload["phone"]).strip() or None
    # support both address_street (new form) and address_line (legacy)
    street = payload.get("address_street") or payload.get("address_line")
    if street is not None:
        app.street_address = str(street).strip() or None
    if payload.get("address_city") is not None:
        app.city = str(payload["address_city"]).strip() or None
    if payload.get("address_region") is not None:
        app.region = str(payload["address_region"]).strip() or None
    if payload.get("address_postal") is not None:
        app.postal_code = str(payload["address_postal"]).strip() or None
    if payload.get("address_country") is not None:
        app.country = str(payload["address_country"]).strip() or None


# ---------- POST submit (applicant submits form) ----------


class SubmitApplicationBody(BaseModel):
    """Current form state; server persists and then marks SUBMITTED."""
    intake_payload: dict | None = None


@router.post("/{app_id}/submit", response_model=dict)
async def submit_application(
    app_id: int,
    request: Request,
    body: SubmitApplicationBody,
    _ctx: tuple[int, int] = Depends(applicant_context_from_header),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Applicant submits the form. Requires DRAFT. Persists intake_payload, syncs to model, sets SUBMITTED."""
    if request.state.onboarding_application_id != app_id:
        raise HTTPException(status_code=403, detail="Token does not match application")
    app = await db.scalar(
        select(PersonApplication).where(
            PersonApplication.tenant_id == request.state.tenant_id,
            PersonApplication.id == app_id,
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="Application already submitted or not in draft")

    payload = body.intake_payload if body.intake_payload is not None else (app.intake_payload or {})
    app.intake_payload = dict(payload)
    _sync_intake_to_model(app, app.intake_payload)
    app.status = DriverOnboardingStatus.SUBMITTED.value
    app.submitted_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(app)
    return _serialize_app(app)


# ---------- PATCH intake (save progress between steps without submitting) ----------

class SaveIntakeBody(BaseModel):
    intake_payload: dict | None = None

@router.patch("/{app_id}/intake", response_model=dict)
async def save_intake(
    app_id: int,
    request: Request,
    body: SaveIntakeBody,
    _ctx: tuple[int, int] = Depends(applicant_context_from_header),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Save form progress without submitting. Merges intake_payload fields, syncs to model columns."""
    if request.state.onboarding_application_id != app_id:
        raise HTTPException(status_code=403, detail="Token does not match application")
    app = await db.scalar(
        select(PersonApplication).where(
            PersonApplication.tenant_id == request.state.tenant_id,
            PersonApplication.id == app_id,
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.status not in (DriverOnboardingStatus.DRAFT.value, DriverOnboardingStatus.IN_PROGRESS.value):
        raise HTTPException(status_code=409, detail="Application already submitted")

    existing = dict(app.intake_payload or {})
    incoming = dict(body.intake_payload or {})
    existing.update(incoming)
    app.intake_payload = existing
    _sync_intake_to_model(app, existing)
    await db.commit()
    await db.refresh(app)
    return _serialize_app(app)
