from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

DEFAULT_LOCAL_DIR = Path("/home/admin/trucking_erp/storage/driver_docs")


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
