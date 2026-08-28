"""Unified storage abstraction: local filesystem or S3.

All document storage goes through this module. No boto3 outside this file.
Key pattern: <tenant_slug>/<module>/<entity_type>/<entity_id>/<filename>
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import tempfile
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

from fastapi import UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.core.config import settings

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
    base = os.path.basename(name).replace("\x00", "")
    base = re.sub(r"[^\w.\-]", "_", base)[:200]
    return base or "upload"


def build_storage_key(
    tenant_slug: str,
    module: str,
    entity_type: str,
    entity_id: str | int,
    filename: str,
) -> str:
    """Build stable storage key. First segment is tenant slug."""
    safe_mod = re.sub(r"[^\w\-]", "_", module)
    safe_entity = re.sub(r"[^\w\-]", "_", str(entity_type))
    safe_id = str(entity_id)
    safe_name = _safe_filename(filename)
    return f"{tenant_slug}/{safe_mod}/{safe_entity}/{safe_id}/{safe_name}"


def _resolve_legacy_key(storage_key: str, module: str, tenant_slug: str | None) -> str:
    """For legacy keys (no path), build full key for S3 or path for local."""
    if "/" in storage_key:
        return storage_key
    if tenant_slug:
        return f"{tenant_slug}/{module}/legacy/0/{storage_key}"
    return storage_key


class StorageBackend(ABC):
    @abstractmethod
    async def save_upload(
        self,
        tenant_slug: str,
        module: str,
        entity_type: str,
        entity_id: str | int,
        file: UploadFile,
    ) -> StoredFile:
        ...

    @abstractmethod
    async def save_bytes(
        self,
        tenant_slug: str,
        module: str,
        entity_type: str,
        entity_id: str | int,
        body: bytes,
        *,
        filename_hint: str = "upload.bin",
        content_type: str | None = None,
    ) -> StoredFile:
        ...

    @abstractmethod
    def read_bytes(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
    ) -> bytes:
        ...

    @abstractmethod
    def exists(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
    ) -> bool:
        ...

    @abstractmethod
    def delete(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
    ) -> None:
        ...

    def resolve_path(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
    ) -> Path | None:
        """Local only: return filesystem path for FileResponse. S3 returns None."""
        return None


class LocalStorageBackend(StorageBackend):
    def _storage_root(self) -> Path:
        return Path(settings.local_storage_dir or str(STORAGE_ROOT)).resolve()

    def _module_dir(self, module: str) -> Path:
        roots = {
            "driver_docs": DEFAULT_LOCAL_DIR,
            "applicant_dl": DEFAULT_APPLICANT_DL_DIR,
            "applicant_docs": DEFAULT_LOCAL_DIR / "applicant_docs",
            "company_docs": DEFAULT_COMPANY_DOCS_DIR,
            "pay_documents": DEFAULT_PAY_DOCS_DIR,
        }
        base = roots.get(module, DEFAULT_LOCAL_DIR)
        if settings.company_docs_dir and module == "company_docs":
            base = Path(settings.company_docs_dir)
        elif settings.local_storage_dir:
            try:
                rel = base.relative_to(STORAGE_ROOT)
                base = Path(settings.local_storage_dir) / rel
            except ValueError:
                base = Path(settings.local_storage_dir)
        return Path(base).resolve()

    def _key_to_path(self, storage_key: str, module: str | None, tenant_slug: str | None) -> Path:
        if "/" in storage_key:
            return self._storage_root() / storage_key
        mod = module or "driver_docs"
        base = self._module_dir(mod)
        return base / storage_key

    async def save_upload(
        self,
        tenant_slug: str,
        module: str,
        entity_type: str,
        entity_id: str | int,
        file: UploadFile,
    ) -> StoredFile:
        original = _safe_filename(file.filename)
        ext = Path(original).suffix.lower()[:10] or ".bin"
        key = build_storage_key(tenant_slug, module, entity_type, entity_id, f"{uuid.uuid4().hex}{ext}")
        dest = self._storage_root() / key
        dest.parent.mkdir(parents=True, exist_ok=True)

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

    async def save_bytes(
        self,
        tenant_slug: str,
        module: str,
        entity_type: str,
        entity_id: str | int,
        body: bytes,
        *,
        filename_hint: str = "upload.bin",
        content_type: str | None = None,
    ) -> StoredFile:
        original = _safe_filename(filename_hint)
        ext = Path(original).suffix.lower()[:10] or ".bin"
        key = build_storage_key(tenant_slug, module, entity_type, entity_id, f"{uuid.uuid4().hex}{ext}")
        dest = self._storage_root() / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return StoredFile(
            storage_key=key,
            original_filename=original,
            content_type=content_type,
            file_size_bytes=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
        )

    def read_bytes(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
    ) -> bytes:
        path = self._key_to_path(storage_key, module, tenant_slug)
        return path.read_bytes()

    def stream_chunks(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
        chunk_size: int = 1024 * 256,
    ) -> Iterator[bytes]:
        """Stream file in chunks. Avoids loading entire file into memory."""
        path = self._key_to_path(storage_key, module, tenant_slug)
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    def exists(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
    ) -> bool:
        path = self._key_to_path(storage_key, module, tenant_slug)
        return path.is_file()

    def delete(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
    ) -> None:
        path = self._key_to_path(storage_key, module, tenant_slug)
        if path.is_file():
            path.unlink()

    def resolve_path(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
    ) -> Path | None:
        return self._key_to_path(storage_key, module, tenant_slug)


class S3StorageBackend(StorageBackend):
    def __init__(self) -> None:
        import boto3
        self._client = boto3.client("s3", region_name=settings.aws_region)
        self._bucket = settings.s3_bucket
        self._prefix = (settings.s3_prefix or "").rstrip("/")

    def _full_key(self, storage_key: str, module: str | None, tenant_slug: str | None) -> str:
        if "/" in storage_key:
            k = storage_key
        else:
            k = _resolve_legacy_key(storage_key, module or "driver_docs", tenant_slug)
        if self._prefix:
            return f"{self._prefix}/{k}".lstrip("/")
        return k

    async def save_upload(
        self,
        tenant_slug: str,
        module: str,
        entity_type: str,
        entity_id: str | int,
        file: UploadFile,
    ) -> StoredFile:
        original = _safe_filename(file.filename)
        ext = Path(original).suffix.lower()[:10] or ".bin"
        key = build_storage_key(tenant_slug, module, entity_type, entity_id, f"{uuid.uuid4().hex}{ext}")
        full_key = self._full_key(key, module, tenant_slug)

        h = hashlib.sha256()
        body = b""
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            body += chunk
            h.update(chunk)

        extra = {}
        if file.content_type:
            extra["ContentType"] = file.content_type

        self._client.put_object(
            Bucket=self._bucket,
            Key=full_key,
            Body=body,
            **extra,
        )

        return StoredFile(
            storage_key=key,
            original_filename=original,
            content_type=file.content_type,
            file_size_bytes=len(body),
            sha256=h.hexdigest(),
        )

    async def save_bytes(
        self,
        tenant_slug: str,
        module: str,
        entity_type: str,
        entity_id: str | int,
        body: bytes,
        *,
        filename_hint: str = "upload.bin",
        content_type: str | None = None,
    ) -> StoredFile:
        original = _safe_filename(filename_hint)
        ext = Path(original).suffix.lower()[:10] or ".bin"
        key = build_storage_key(tenant_slug, module, entity_type, entity_id, f"{uuid.uuid4().hex}{ext}")
        full_key = self._full_key(key, module, tenant_slug)
        extra: dict[str, str] = {}
        if content_type:
            extra["ContentType"] = content_type
        self._client.put_object(
            Bucket=self._bucket,
            Key=full_key,
            Body=body,
            **extra,
        )
        return StoredFile(
            storage_key=key,
            original_filename=original,
            content_type=content_type,
            file_size_bytes=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
        )

    def read_bytes(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
    ) -> bytes:
        full_key = self._full_key(storage_key, module, tenant_slug)
        resp = self._client.get_object(Bucket=self._bucket, Key=full_key)
        return resp["Body"].read()

    def stream_chunks(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
        chunk_size: int = 1024 * 256,
    ) -> Iterator[bytes]:
        """Stream file in chunks. Avoids loading entire file into memory."""
        full_key = self._full_key(storage_key, module, tenant_slug)
        resp = self._client.get_object(Bucket=self._bucket, Key=full_key)
        body = resp["Body"]
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            yield chunk

    def exists(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
    ) -> bool:
        full_key = self._full_key(storage_key, module, tenant_slug)
        try:
            self._client.head_object(Bucket=self._bucket, Key=full_key)
            return True
        except Exception:
            return False

    def delete(
        self,
        storage_key: str,
        module: str | None = None,
        tenant_slug: str | None = None,
    ) -> None:
        full_key = self._full_key(storage_key, module, tenant_slug)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=full_key)
        except Exception:
            pass


_engine: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _engine
    if _engine is None:
        provider = (settings.storage_provider or "local").lower()
        if provider == "s3":
            _engine = S3StorageBackend()
        else:
            _engine = LocalStorageBackend()
    return _engine


def resolve_storage_path(storage_key: str, default_dir: Path | None = None) -> Path:
    """Resolve storage key to local path. Local backend only; use stream_for_download for S3."""
    backend = get_storage()
    if isinstance(backend, LocalStorageBackend):
        mod = "pay_documents" if (default_dir and DEFAULT_PAY_DOCS_DIR == default_dir) else "driver_docs"
        return backend._key_to_path(storage_key, mod, None)
    raise RuntimeError("resolve_storage_path only supported for local storage")


def resolve_applicant_dl_path(storage_key: str) -> Path:
    backend = get_storage()
    if isinstance(backend, LocalStorageBackend):
        return backend._key_to_path(storage_key, "applicant_dl", None)
    raise RuntimeError("resolve_applicant_dl_path only supported for local storage (PDF417)")


def resolve_applicant_doc_path(storage_key: str) -> Path:
    backend = get_storage()
    if isinstance(backend, LocalStorageBackend):
        return backend._key_to_path(storage_key, "applicant_docs", None)
    raise RuntimeError("resolve_applicant_doc_path only supported for local storage")


@contextmanager
def readable_path(storage_key: str, module: str, tenant_slug: str | None = None):
    """Yield a Path for reading. For S3, uses temp file (auto-cleaned)."""
    backend = get_storage()
    if isinstance(backend, LocalStorageBackend):
        yield backend._key_to_path(storage_key, module, tenant_slug)
        return
    data = backend.read_bytes(storage_key, module, tenant_slug)
    suffix = Path(storage_key).suffix or ".bin"
    fd, path_str = tempfile.mkstemp(suffix=suffix)
    try:
        os.write(fd, data)
        os.close(fd)
        yield Path(path_str)
    finally:
        Path(path_str).unlink(missing_ok=True)


async def save_driver_doc_upload(tenant_slug: str, document_id: int, file: UploadFile) -> StoredFile:
    return await get_storage().save_upload(
        tenant_slug, "driver_docs", "document", document_id, file
    )


async def save_applicant_dl_upload(
    tenant_slug: str, application_id: int, file: UploadFile
) -> StoredFile:
    return await get_storage().save_upload(
        tenant_slug, "applicant_dl", "application", application_id, file
    )


async def save_applicant_dl_processed_bytes(
    tenant_slug: str,
    application_id: int,
    body: bytes,
    *,
    original_storage_key: str,
) -> StoredFile:
    stem = Path(original_storage_key).name.rsplit(".", 1)[0]
    return await get_storage().save_bytes(
        tenant_slug,
        "applicant_dl",
        "application",
        application_id,
        body,
        filename_hint=f"{stem}_processed.jpg",
        content_type="image/jpeg",
    )


async def save_applicant_doc_upload(
    tenant_slug: str, application_id: int, file: UploadFile
) -> StoredFile:
    return await get_storage().save_upload(
        tenant_slug, "applicant_docs", "application", application_id, file
    )


async def save_company_doc_upload(tenant_slug: str, company_id: int, file: UploadFile) -> StoredFile:
    return await get_storage().save_upload(
        tenant_slug, "company_docs", "company", company_id, file
    )


def _content_type_from_suffix(storage_key: str, default: str = "application/octet-stream") -> str:
    suf = Path(storage_key).suffix.lower()
    if suf in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suf == ".png":
        return "image/png"
    if suf == ".pdf":
        return "application/pdf"
    return default


def serve_file(
    storage_key: str,
    module: str,
    tenant_slug: str | None = None,
    filename: str | None = None,
    content_type: str | None = None,
) -> Response:
    """Serve a file (inline display). Works for local and S3. Streams for large files."""
    from fastapi import HTTPException
    backend = get_storage()
    ct = content_type or _content_type_from_suffix(storage_key)
    fname = filename or Path(storage_key).name or "file"
    if isinstance(backend, LocalStorageBackend):
        path = backend._key_to_path(storage_key, module, tenant_slug)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path, media_type=ct, filename=fname, content_disposition_type="inline")
    if not backend.exists(storage_key, module, tenant_slug):
        raise HTTPException(status_code=404, detail="File not found")
    headers = {"Content-Disposition": f'inline; filename="{fname}"'}
    return StreamingResponse(
        backend.stream_chunks(storage_key, module, tenant_slug),
        media_type=ct,
        headers=headers,
    )


def download_response(
    storage_key: str,
    module: str = "pay_documents",
    tenant_slug: str | None = None,
    content_type: str = "application/pdf",
    filename: str | None = None,
) -> Response:
    """Return FileResponse (local) or StreamingResponse (S3) for document download. Streams for large files."""
    from fastapi import HTTPException
    backend = get_storage()
    fname = filename or Path(storage_key).name or "document.pdf"
    if isinstance(backend, LocalStorageBackend):
        path = backend._key_to_path(storage_key, module, tenant_slug)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Document file not found")
        return FileResponse(path, media_type=content_type, filename=fname, content_disposition_type="attachment")
    if not backend.exists(storage_key, module, tenant_slug):
        raise HTTPException(status_code=404, detail="Document file not found")
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    return StreamingResponse(
        backend.stream_chunks(storage_key, module, tenant_slug),
        media_type=content_type,
        headers=headers,
    )
