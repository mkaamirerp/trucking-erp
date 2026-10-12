"""DW-2 — load workspace draft PDF storage service (unit, no tenant DB)."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.storage import LocalStorageBackend, put_bytes_at_storage_key
from app.services.load_workspace_draft_storage import (
    RETENTION_COMMERCIAL_PERMANENT,
    RETENTION_WORKSPACE_TTL,
    Sha256MismatchError,
    allocate_pending_upload_key,
    assert_storage_key_matches_draft,
    build_workspace_draft_pdf_storage_key,
    evaluate_pdf_cleanup_candidate,
    object_exists,
    put_workspace_draft_pdf_bytes,
    read_object_bytes,
    attempt_safe_delete_pdf_object,
    sha256_hex,
)


@pytest.fixture
def local_storage(tmp_path: Path):
    patcher = patch("app.core.storage.settings")
    mock_settings = patcher.start()
    mock_settings.local_storage_dir = str(tmp_path)
    mock_settings.company_docs_dir = None
    try:
        yield tmp_path
    finally:
        patcher.stop()


@pytest.mark.asyncio
async def test_unique_keys_per_upload(local_storage) -> None:
    tenant_slug = "pytest"
    tenant_id = 42
    draft_id = uuid.uuid4()
    a = allocate_pending_upload_key(tenant_slug, tenant_id, draft_id)
    b = allocate_pending_upload_key(tenant_slug, tenant_id, draft_id)
    assert a.storage_key != b.storage_key
    assert a.upload_uuid != b.upload_uuid


def test_key_matches_draft_scope() -> None:
    tenant_slug = "demo"
    tenant_id = 1
    draft_id = uuid.uuid4()
    upload_id = uuid.uuid4()
    key = build_workspace_draft_pdf_storage_key(tenant_slug, tenant_id, draft_id, upload_id)
    assert_storage_key_matches_draft(
        key, tenant_slug=tenant_slug, tenant_id=tenant_id, draft_id=draft_id
    )
    with pytest.raises(Exception):
        assert_storage_key_matches_draft(
            f"{tenant_slug}/load_workspace_drafts/tenant_999/draft_{draft_id}/{upload_id}.pdf",
            tenant_slug=tenant_slug,
            tenant_id=tenant_id,
            draft_id=draft_id,
        )


@pytest.mark.asyncio
async def test_put_read_sha256_and_exists(local_storage) -> None:
    tenant_slug = "pytest"
    tenant_id = 7
    draft_id = uuid.uuid4()
    pending = allocate_pending_upload_key(tenant_slug, tenant_id, draft_id)
    body = b"%PDF-1.4 dw2 test"
    digest = sha256_hex(body)
    stored = await put_workspace_draft_pdf_bytes(
        pending.storage_key,
        body,
        tenant_slug=tenant_slug,
        tenant_id=tenant_id,
        draft_id=draft_id,
        expected_sha256=digest,
    )
    assert stored.sha256 == digest
    assert object_exists(pending.storage_key, tenant_slug=tenant_slug)
    read_back = read_object_bytes(
        pending.storage_key, tenant_slug=tenant_slug, expected_sha256=digest
    )
    assert read_back == body


@pytest.mark.asyncio
async def test_sha256_mismatch_rejected(local_storage) -> None:
    tenant_slug = "pytest"
    tenant_id = 7
    draft_id = uuid.uuid4()
    pending = allocate_pending_upload_key(tenant_slug, tenant_id, draft_id)
    with pytest.raises(Sha256MismatchError):
        await put_workspace_draft_pdf_bytes(
            pending.storage_key,
            b"data",
            tenant_slug=tenant_slug,
            tenant_id=tenant_id,
            draft_id=draft_id,
            expected_sha256="0" * 64,
        )


def test_cleanup_candidate_rules() -> None:
    key = "pytest/load_workspace_drafts/tenant_1/draft_x/u.pdf"
    perm = evaluate_pdf_cleanup_candidate(
        key,
        retention_class=RETENTION_COMMERCIAL_PERMANENT,
        draft_status="draft",
        is_pending_key=False,
        has_active_upload_lease=False,
        evidence_references_key=False,
        is_active_committed_key=False,
    )
    assert not perm.may_delete

    leased = evaluate_pdf_cleanup_candidate(
        key,
        retention_class=RETENTION_WORKSPACE_TTL,
        draft_status="draft",
        is_pending_key=True,
        has_active_upload_lease=True,
        evidence_references_key=False,
        is_active_committed_key=False,
    )
    assert not leased.may_delete

    expired = evaluate_pdf_cleanup_candidate(
        key,
        retention_class=RETENTION_WORKSPACE_TTL,
        draft_status="expired",
        is_pending_key=False,
        has_active_upload_lease=False,
        evidence_references_key=False,
        is_active_committed_key=False,
    )
    assert expired.may_delete


@pytest.mark.asyncio
async def test_put_bytes_at_key_rejects_overwrite_by_default(local_storage) -> None:
    key = "pytest/load_workspace_drafts/tenant_1/draft_x/u.pdf"
    await put_bytes_at_storage_key(key, b"a", module="load_workspace_drafts", tenant_slug="pytest")
    with pytest.raises(FileExistsError):
        await put_bytes_at_storage_key(key, b"b", module="load_workspace_drafts", tenant_slug="pytest")


@pytest.mark.asyncio
async def test_safe_delete_respects_decision(local_storage) -> None:
    tenant_slug = "pytest"
    tenant_id = 3
    draft_id = uuid.uuid4()
    pending = allocate_pending_upload_key(tenant_slug, tenant_id, draft_id)
    await put_workspace_draft_pdf_bytes(
        pending.storage_key,
        b"x",
        tenant_slug=tenant_slug,
        tenant_id=tenant_id,
        draft_id=draft_id,
    )
    assert not attempt_safe_delete_pdf_object(
        pending.storage_key,
        tenant_slug=tenant_slug,
        retention_class=RETENTION_WORKSPACE_TTL,
        draft_status="draft",
        is_pending_key=True,
        has_active_upload_lease=True,
        evidence_references_key=False,
        is_active_committed_key=False,
    )
    assert object_exists(pending.storage_key, tenant_slug=tenant_slug)

    assert attempt_safe_delete_pdf_object(
        pending.storage_key,
        tenant_slug=tenant_slug,
        retention_class=RETENTION_WORKSPACE_TTL,
        draft_status="expired",
        is_pending_key=False,
        has_active_upload_lease=False,
        evidence_references_key=False,
        is_active_committed_key=False,
    )
    assert not object_exists(pending.storage_key, tenant_slug=tenant_slug)
