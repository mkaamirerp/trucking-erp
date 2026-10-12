"""Load workspace draft PDF object storage (DW-2 foundation).

Uses ``app.core.storage`` only. Keys are tenant-scoped, unique per upload, never shared
across drafts (DRAFT_WORKSPACE_SPEC §4.1).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Final

from app.core.storage import StoredFile, get_storage, put_bytes_at_storage_key
from app.models.load_workspace_draft import LOAD_WORKSPACE_RETENTION_CLASSES

STORAGE_MODULE: Final[str] = "load_workspace_drafts"
RETENTION_WORKSPACE_TTL: Final[str] = "workspace_ttl"
RETENTION_COMMERCIAL_PERMANENT: Final[str] = "commercial_permanent"
PDF_CONTENT_TYPE: Final[str] = "application/pdf"


class LoadWorkspaceDraftStorageError(ValueError):
    """Invalid key, retention, or object state for workspace draft PDF storage."""


class Sha256MismatchError(LoadWorkspaceDraftStorageError):
    """Uploaded or read bytes do not match expected SHA-256."""


@dataclass(frozen=True)
class PendingUploadKey:
    """Reserved object key for Transaction A (upload begin)."""

    upload_uuid: uuid.UUID
    storage_key: str


@dataclass(frozen=True)
class PdfCleanupDecision:
    storage_key: str
    may_delete: bool
    reason: str


def sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def verify_sha256(body: bytes, expected_hex: str | None) -> None:
    if not expected_hex:
        return
    actual = sha256_hex(body)
    if actual.lower() != expected_hex.lower():
        raise Sha256MismatchError(f"sha256 mismatch (expected {expected_hex[:8]}…, got {actual[:8]}…)")


def build_workspace_draft_pdf_storage_key(
    tenant_slug: str,
    tenant_id: int,
    draft_id: uuid.UUID,
    upload_uuid: uuid.UUID,
) -> str:
    """``{tenant_slug}/load_workspace_drafts/tenant_{id}/draft_{id}/{upload}.pdf`` (spec §4.1)."""
    if not tenant_slug or tenant_id <= 0:
        raise LoadWorkspaceDraftStorageError("invalid tenant scope for storage key")
    return (
        f"{tenant_slug}/{STORAGE_MODULE}/tenant_{tenant_id}/draft_{draft_id}/{upload_uuid}.pdf"
    )


def assert_storage_key_matches_draft(
    storage_key: str,
    *,
    tenant_slug: str,
    tenant_id: int,
    draft_id: uuid.UUID,
) -> None:
    prefix = f"{tenant_slug}/{STORAGE_MODULE}/tenant_{tenant_id}/draft_{draft_id}/"
    if not storage_key.startswith(prefix) or not storage_key.endswith(".pdf"):
        raise LoadWorkspaceDraftStorageError("storage_key outside draft tenant scope")


def allocate_pending_upload_key(
    tenant_slug: str,
    tenant_id: int,
    draft_id: uuid.UUID,
) -> PendingUploadKey:
    upload_uuid = uuid.uuid4()
    key = build_workspace_draft_pdf_storage_key(tenant_slug, tenant_id, draft_id, upload_uuid)
    return PendingUploadKey(upload_uuid=upload_uuid, storage_key=key)


async def put_workspace_draft_pdf_bytes(
    storage_key: str,
    body: bytes,
    *,
    tenant_slug: str,
    tenant_id: int,
    draft_id: uuid.UUID,
    filename_hint: str = "rate_confirmation.pdf",
    expected_sha256: str | None = None,
) -> StoredFile:
    if not body:
        raise LoadWorkspaceDraftStorageError("empty PDF body")
    verify_sha256(body, expected_sha256)
    assert_storage_key_matches_draft(
        storage_key, tenant_slug=tenant_slug, tenant_id=tenant_id, draft_id=draft_id
    )
    stored = await put_bytes_at_storage_key(
        storage_key,
        body,
        filename_hint=filename_hint,
        content_type=PDF_CONTENT_TYPE,
        module=STORAGE_MODULE,
        tenant_slug=tenant_slug,
        allow_overwrite=True,
    )
    verify_sha256(body, stored.sha256)
    return stored


def object_exists(
    storage_key: str,
    *,
    tenant_slug: str | None = None,
) -> bool:
    if not storage_key:
        return False
    return get_storage().exists(storage_key, module=STORAGE_MODULE, tenant_slug=tenant_slug)


def read_object_bytes(
    storage_key: str,
    *,
    tenant_slug: str | None = None,
    expected_sha256: str | None = None,
) -> bytes:
    if not storage_key:
        raise LoadWorkspaceDraftStorageError("missing storage_key")
    backend = get_storage()
    if not backend.exists(storage_key, module=STORAGE_MODULE, tenant_slug=tenant_slug):
        raise LoadWorkspaceDraftStorageError("object not found")
    body = backend.read_bytes(storage_key, module=STORAGE_MODULE, tenant_slug=tenant_slug)
    verify_sha256(body, expected_sha256)
    return body


def _delete_object_if_present(
    storage_key: str,
    *,
    tenant_slug: str | None = None,
) -> bool:
    """Low-level delete — not for direct use; see ``attempt_safe_delete_pdf_object``."""
    if not storage_key:
        return False
    backend = get_storage()
    if not backend.exists(storage_key, module=STORAGE_MODULE, tenant_slug=tenant_slug):
        return False
    backend.delete(storage_key, module=STORAGE_MODULE, tenant_slug=tenant_slug)
    return True


def evaluate_pdf_cleanup_candidate(
    storage_key: str,
    *,
    retention_class: str,
    draft_status: str | None,
    is_pending_key: bool,
    has_active_upload_lease: bool,
    evidence_references_key: bool,
    is_active_committed_key: bool,
) -> PdfCleanupDecision:
    """Whether object deletion is allowed per DRAFT_WORKSPACE_SPEC §4.4 (storage layer only)."""
    if not storage_key:
        return PdfCleanupDecision(storage_key="", may_delete=False, reason="empty_key")
    if retention_class not in LOAD_WORKSPACE_RETENTION_CLASSES:
        return PdfCleanupDecision(storage_key=storage_key, may_delete=False, reason="invalid_retention_class")
    if retention_class == RETENTION_COMMERCIAL_PERMANENT:
        return PdfCleanupDecision(storage_key=storage_key, may_delete=False, reason="commercial_permanent")
    if evidence_references_key:
        return PdfCleanupDecision(storage_key=storage_key, may_delete=False, reason="referenced_by_evidence")
    if is_active_committed_key:
        return PdfCleanupDecision(storage_key=storage_key, may_delete=False, reason="active_committed_pdf")
    if is_pending_key and has_active_upload_lease:
        return PdfCleanupDecision(storage_key=storage_key, may_delete=False, reason="active_upload_lease")
    if draft_status == "promoted":
        return PdfCleanupDecision(storage_key=storage_key, may_delete=False, reason="promoted_draft")
    if draft_status in {"discarded", "expired"}:
        return PdfCleanupDecision(storage_key=storage_key, may_delete=True, reason="terminal_workspace_ttl")
    if is_pending_key and not has_active_upload_lease:
        return PdfCleanupDecision(storage_key=storage_key, may_delete=True, reason="orphaned_pending_upload")
    return PdfCleanupDecision(storage_key=storage_key, may_delete=False, reason="still_active_draft_reference")


def attempt_safe_delete_pdf_object(
    storage_key: str,
    *,
    tenant_slug: str | None,
    retention_class: str,
    draft_status: str | None,
    is_pending_key: bool,
    has_active_upload_lease: bool,
    evidence_references_key: bool,
    is_active_committed_key: bool,
) -> bool:
    """Delete only when ``evaluate_pdf_cleanup_candidate`` allows (DW-3 passes DB-derived flags).

    Callers must not delete from storage based on a pre-built ``PdfCleanupDecision`` alone.
    """
    decision = evaluate_pdf_cleanup_candidate(
        storage_key,
        retention_class=retention_class,
        draft_status=draft_status,
        is_pending_key=is_pending_key,
        has_active_upload_lease=has_active_upload_lease,
        evidence_references_key=evidence_references_key,
        is_active_committed_key=is_active_committed_key,
    )
    if not decision.may_delete:
        return False
    return _delete_object_if_present(storage_key, tenant_slug=tenant_slug)
