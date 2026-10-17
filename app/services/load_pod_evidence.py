"""Upload, list, and download Proof of Delivery evidence for a Load."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_storage
from app.models.load import Load
from app.models.load_pod_evidence import LoadPodEvidence
from app.services.loads import _write_load_audit

LOAD_POD_MODULE = "load_pod"
POD_MAX_BYTES = 20 * 1024 * 1024


class PodEvidenceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def classify_pod_bytes(data: bytes) -> tuple[str, str]:
    """Return (content_type, extension) from magic bytes."""
    if data.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", ".jpg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", ".png"
    raise PodEvidenceError(
        "INVALID_POD_FILE_TYPE",
        "Proof of delivery must be a PDF, JPEG, or PNG file",
        status.HTTP_400_BAD_REQUEST,
    )


async def read_bounded_pod_upload(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = await file.read(1024 * 1024)
        if not piece:
            break
        total += len(piece)
        if total > POD_MAX_BYTES:
            raise PodEvidenceError(
                "POD_FILE_TOO_LARGE",
                f"File exceeds {POD_MAX_BYTES} bytes",
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        chunks.append(piece)
    data = b"".join(chunks)
    if not data:
        raise PodEvidenceError("EMPTY_POD_FILE", "Empty file", status.HTTP_400_BAD_REQUEST)
    return data


async def upload_load_pod_evidence(
    db: AsyncSession,
    tenant_id: int,
    tenant_slug: str,
    load_id: int,
    file: UploadFile,
    *,
    actor_user_id: int | None,
    actor_label: str | None,
    request_id: str | None,
    source: str = "api",
) -> LoadPodEvidence:
    load = await db.scalar(select(Load).where(Load.id == load_id, Load.tenant_id == tenant_id))
    if load is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    data = await read_bounded_pod_upload(file)
    content_type, _ext = classify_pod_bytes(data)
    filename_hint = file.filename or f"pod{_ext}"
    sha256 = hashlib.sha256(data).hexdigest()

    stored = await get_storage().save_bytes(
        tenant_slug,
        LOAD_POD_MODULE,
        "load",
        load_id,
        data,
        filename_hint=filename_hint,
        content_type=content_type,
    )

    now = datetime.now(timezone.utc)
    row = LoadPodEvidence(
        tenant_id=tenant_id,
        load_id=load_id,
        storage_key=stored.storage_key,
        file_sha256=stored.sha256 or sha256,
        original_filename=stored.original_filename,
        content_type=stored.content_type or content_type,
        file_size_bytes=stored.file_size_bytes,
        uploaded_at=now,
        actor_user_id=actor_user_id,
        actor_label=(actor_label[:128] if actor_label else None),
    )
    db.add(row)
    try:
        await db.flush()
        await _write_load_audit(
            db,
            tenant_id=tenant_id,
            load=load,
            action="pod_evidence_uploaded",
            actor_user_id=actor_user_id,
            request_id=request_id,
            correlation_id=request_id,
            source=source if source in {"ui", "api"} else "api",
            changed_fields={"pod_evidence_id": {"before": None, "after": int(row.id)}},
            context_json={
                "pod_evidence_id": int(row.id),
                "file_sha256": row.file_sha256,
                "original_filename": row.original_filename,
                "content_type": row.content_type,
                "file_size_bytes": row.file_size_bytes,
            },
            best_effort=False,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        get_storage().delete(stored.storage_key, module=LOAD_POD_MODULE, tenant_slug=tenant_slug)
        raise

    await db.refresh(row)
    return row


async def list_load_pod_evidence(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
) -> list[LoadPodEvidence]:
    load = await db.scalar(select(Load).where(Load.id == load_id, Load.tenant_id == tenant_id))
    if load is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    result = await db.execute(
        select(LoadPodEvidence)
        .where(LoadPodEvidence.tenant_id == tenant_id, LoadPodEvidence.load_id == load_id)
        .order_by(LoadPodEvidence.id.asc())
    )
    return list(result.scalars().all())


async def get_load_pod_evidence_row(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
    pod_id: int,
) -> LoadPodEvidence:
    row = await db.scalar(
        select(LoadPodEvidence).where(
            LoadPodEvidence.id == pod_id,
            LoadPodEvidence.tenant_id == tenant_id,
            LoadPodEvidence.load_id == load_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POD evidence not found")
    return row


def assert_pod_storage_key_tenant(row: LoadPodEvidence, tenant_slug: str) -> None:
    prefix = f"{tenant_slug}/"
    if not row.storage_key.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid storage key for tenant")
