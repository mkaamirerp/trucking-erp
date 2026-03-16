from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = PROJECT_ROOT / "storage"
DEFAULT_LOCAL_DIR = STORAGE_ROOT / "driver_docs"
DEFAULT_PAY_DOCS_DIR = STORAGE_ROOT / "pay_documents"
DEFAULT_COMPANY_DOCS_DIR = STORAGE_ROOT / "company_docs"
DEFAULT_APPLICANT_DL_DIR = DEFAULT_LOCAL_DIR / "applicant_dl"


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


def _applicant_dl_dir() -> Path:
    d = os.getenv("APPLICANT_DL_DIR")
    if d:
        return Path(d)
    # Use same base as driver_docs so LOCAL_STORAGE_DIR applies (e.g. in container)
    return _local_dir() / "applicant_dl"


def resolve_storage_path(storage_key: str, default_dir: Path | None = None) -> Path:
    """
    Resolve a storage key to a local filesystem path.
    Honors LOCAL_STORAGE_DIR if set; otherwise uses provided default_dir or DEFAULT_LOCAL_DIR.
    """
    base = os.getenv("LOCAL_STORAGE_DIR")
    root = Path(base) if base else (default_dir or DEFAULT_LOCAL_DIR)
    return root / storage_key


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


async def save_applicant_dl_upload_local(file: UploadFile) -> StoredFile:
    """Save applicant driver license upload (CDL front/back) to applicant_dl storage."""
    base = _applicant_dl_dir()
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


def resolve_applicant_dl_path(storage_key: str) -> Path:
    """Resolve applicant DL storage key to filesystem path."""
    base = _applicant_dl_dir()
    return base / storage_key


def _applicant_docs_dir() -> Path:
    """Directory for applicant step-4 documents (medical, MVR, etc.)."""
    return _local_dir() / "applicant_docs"


async def save_applicant_doc_upload_local(file: UploadFile) -> StoredFile:
    """Save applicant document (DOT medical, MVR, etc.) to applicant_docs storage."""
    base = _applicant_docs_dir()
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


def resolve_applicant_doc_path(storage_key: str) -> Path:
    """Resolve applicant document storage key to filesystem path."""
    return _applicant_docs_dir() / storage_key


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
