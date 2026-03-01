from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

DEFAULT_LOCAL_DIR = Path("/home/admin/trucking_erp/storage/driver_docs")
DEFAULT_PAY_DOCS_DIR = Path("/home/admin/trucking_erp/storage/pay_documents")
DEFAULT_COMPANY_DOCS_DIR = Path("/home/admin/trucking_erp/storage/company_docs")
DEFAULT_ONBOARDING_LICENSES_DIR = Path("/home/admin/trucking_erp/storage/onboarding_licenses")


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    original_filename: str | None
    content_type: str | None
    file_size_bytes: int
    sha256: str


def _safe_filename(name: str | None) -> str:
    if not name:
        return "upload"
    return os.path.basename(name).replace("\x00", "")


def _local_dir() -> Path:
    d = os.getenv("LOCAL_STORAGE_DIR")
    return Path(d) if d else DEFAULT_LOCAL_DIR


def _company_dir() -> Path:
    d = os.getenv("COMPANY_DOCS_DIR")
    return Path(d) if d else DEFAULT_COMPANY_DOCS_DIR


def _onboarding_licenses_dir() -> Path:
    d = os.getenv("ONBOARDING_LICENSES_DIR")
    return Path(d) if d else DEFAULT_ONBOARDING_LICENSES_DIR


def resolve_storage_path(storage_key: str, default_dir: Path | None = None) -> Path:
    """
    Resolve a storage key to a local filesystem path.
    Honors LOCAL_STORAGE_DIR if set; otherwise uses provided default_dir or DEFAULT_LOCAL_DIR.
    """
    base = os.getenv("LOCAL_STORAGE_DIR")
    root = Path(base) if base else (default_dir or DEFAULT_LOCAL_DIR)
    return root / storage_key


def get_onboarding_license_path(storage_key: str) -> Path:
    """Resolve onboarding license storage key to filesystem path (always under onboarding dir)."""
    return _onboarding_licenses_dir() / storage_key


async def save_driver_doc_upload_local(file: UploadFile) -> StoredFile:
    base = _local_dir()
    base.mkdir(parents=True, exist_ok=True)

    original = _safe_filename(file.filename)
    ext = Path(original).suffix.lower()[:10]
    key = f"{uuid.uuid4().hex}{ext}"
    dest = base / key

    h = hashlib.sha256()
    size = 0

    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)  # 1MB
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            size += len(chunk)

    return StoredFile(
        storage_key=key,
        original_filename=original,
        content_type=file.content_type,
        file_size_bytes=size,
        sha256=h.hexdigest(),
    )


async def save_company_doc_upload_local(file: UploadFile) -> StoredFile:
    base = _company_dir()
    base.mkdir(parents=True, exist_ok=True)

    original = _safe_filename(file.filename)
    ext = Path(original).suffix.lower()[:10]
    key = f"{uuid.uuid4().hex}{ext}"
    dest = base / key

    h = hashlib.sha256()
    size = 0

    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            size += len(chunk)

    return StoredFile(
        storage_key=key,
        original_filename=original,
        content_type=file.content_type,
        file_size_bytes=size,
        sha256=h.hexdigest(),
    )


# Allowed MIME types for driver license upload (Task 2)
ONBOARDING_LICENSE_ACCEPT = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/heic",
    "image/heif",
    "application/pdf",
}


async def save_onboarding_license_local(
    file: UploadFile, tenant_id: int, submission_id: int, side: str
) -> StoredFile:
    """Store one license image/PDF for a submission. side is FRONT or BACK."""
    base = _onboarding_licenses_dir() / str(tenant_id) / str(submission_id)
    base.mkdir(parents=True, exist_ok=True)

    original = _safe_filename(file.filename)
    ext = Path(original).suffix.lower()[:10] or ".bin"
    key = f"{side}_{uuid.uuid4().hex}{ext}"
    dest = base / key
    relative_key = f"{tenant_id}/{submission_id}/{key}"

    h = hashlib.sha256()
    size = 0
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            size += len(chunk)

    return StoredFile(
        storage_key=relative_key,
        original_filename=original,
        content_type=file.content_type,
        file_size_bytes=size,
        sha256=h.hexdigest(),
    )


def save_onboarding_license_from_path(
    file_path: Path,
    tenant_id: int,
    submission_id: int,
    side: str,
    content_type: str = "image/jpeg",
) -> StoredFile:
    """Save an existing file (e.g. enhanced image) to onboarding licenses dir. side e.g. FRONT_ENH, BACK_ENH."""
    base = _onboarding_licenses_dir() / str(tenant_id) / str(submission_id)
    base.mkdir(parents=True, exist_ok=True)
    ext = ".jpg" if "image/jpeg" in (content_type or "") else (file_path.suffix or ".bin")
    key = f"{side}_{uuid.uuid4().hex}{ext}"
    dest = base / key
    relative_key = f"{tenant_id}/{submission_id}/{key}"
    h = hashlib.sha256()
    size = 0
    with open(file_path, "rb") as src:
        with open(dest, "wb") as f:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                size += len(chunk)
    return StoredFile(
        storage_key=relative_key,
        original_filename=file_path.name,
        content_type=content_type,
        file_size_bytes=size,
        sha256=h.hexdigest(),
    )


def delete_onboarding_license(storage_key: str) -> None:
    """Delete onboarding license file by storage_key (relative key under onboarding dir)."""
    path = resolve_storage_path(storage_key, default_dir=_onboarding_licenses_dir())
    if path.is_file():
        path.unlink()
