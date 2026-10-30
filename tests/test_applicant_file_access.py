"""Applicant file access: intake cannot set storage pointers, and downloads are ownership-checked.

Uses the dedicated integration tenant (pytest / tenant_pytest), never tenant_demo.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db_url import to_async_pg_url
from app.core.storage import S3StorageBackend
from app.main import app as fastapi_app
from app.models.application_access_token import ApplicationAccessToken
from app.models.person_application import PersonApplication
from app.routers import driver_onboarding as onboarding
from app.schemas.driver_onboarding import DriverOnboardingStatus
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

REQUIRES_DB = not os.environ.get("DATABASE_URL")
JPEG = b"\xff\xd8\xff\xd9"
PDF = b"%PDF-1.4\n%applicant-doc\n"
VICTIM_BYTES = b"VICTIM-APPLICATION-FILE"
OTHER_TENANT_BYTES = b"OTHER-TENANT-FILE"
LEGACY_BYTES = b"LEGACY-FLAT-FILE"


def _tenant_async_url() -> str | None:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return None
    return to_async_pg_url(raw)


REQUIRES_TENANT_DB = _tenant_async_url() is None


def _token_sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def test_merge_ignores_server_owned_files_and_documents() -> None:
    existing = {
        "first_name": "A",
        "files": {"CDL_FRONT": {"storage_key": "keep-dl"}},
        "documents": {"mvr": {"storage_key": "keep-doc"}},
    }
    incoming = {
        "first_name": "B",
        "phone": "   ",
        "files": None,
        "documents": {"mvr": {"storage_key": "../secret"}},
    }
    merged = onboarding._merge_applicant_intake_payload(existing, incoming)
    assert merged["first_name"] == "B"
    assert "phone" not in merged
    assert merged["files"] == existing["files"]
    assert merged["documents"] == existing["documents"]

    created = onboarding._merge_applicant_intake_payload(
        {"step": "dl_upload"},
        {"city": "Austin", "files": {"CDL_FRONT": {"storage_key": "../etc/passwd"}}, "documents": {}},
    )
    assert created["city"] == "Austin"
    assert "files" not in created
    assert "documents" not in created


def test_storage_key_must_match_tenant_and_application() -> None:
    bound = onboarding._storage_key_bound_to_application
    ok = bound(
        "pytest/applicant_dl/application/4/abc.jpg",
        tenant_slug="pytest",
        application_id=4,
        module="applicant_dl",
    )
    assert ok == "pytest/applicant_dl/application/4/abc.jpg"
    flat_uuid = "a" * 32 + ".jpg"
    assert bound(flat_uuid, tenant_slug="pytest", application_id=4, module="applicant_dl") is None
    assert bound("old-license.jpg", tenant_slug="pytest", application_id=4, module="applicant_dl") is None
    refused = [
        "pytest/applicant_dl/application/5/abc.jpg",
        "acme/applicant_dl/application/4/abc.jpg",
        "pytest/applicant_docs/application/4/abc.pdf",
        "../secret.txt",
        "/etc/passwd",
        "pytest/applicant_dl/application/4/../../secret.txt",
        "pytest/applicant_dl/application/4/extra/abc.jpg",
        "",
    ]
    for key in refused:
        assert (
            bound(key, tenant_slug="pytest", application_id=4, module="applicant_dl") is None
        ), key


@pytest.fixture(autouse=True)
def test_bypass_env():
    old = os.environ.get("TEST_BYPASS_AUTH")
    os.environ["TEST_BYPASS_AUTH"] = "1"
    yield
    if old is None:
        os.environ.pop("TEST_BYPASS_AUTH", None)
    else:
        os.environ["TEST_BYPASS_AUTH"] = old


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def tenant_id():
    return await platform_tenant_id_for_slug()


@pytest.fixture
async def tenant_session():
    url = _tenant_async_url()
    if not url:
        pytest.skip("TENANT_DATABASE_URL or ALEMBIC_TENANT_DATABASE_URL required")
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            yield session
    finally:
        await engine.dispose()


def _slug() -> str:
    from tests.support.integration_isolation import integration_tenant_slug

    return integration_tenant_slug()


async def _add_app(
    session: AsyncSession,
    *,
    tenant_id: int,
    intake: dict | None = None,
    status: str = DriverOnboardingStatus.DRAFT.value,
) -> tuple[int, str]:
    suffix = uuid.uuid4().hex[:10]
    row = PersonApplication(
        tenant_id=tenant_id,
        source="file_access_security_test",
        status=status,
        requested_role_code="DRIVER",
        application_type="DRIVER",
        email=f"fileaccess.{suffix}@test.invalid",
        intake_payload=intake or {"step": "dl_upload"},
    )
    session.add(row)
    await session.flush()
    raw = f"invite_{uuid.uuid4().hex}"
    session.add(
        ApplicationAccessToken(
            tenant_id=tenant_id,
            application_id=row.id,
            token=raw,
            token_hash=_token_sha256_hex(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(days=2),
            revoked_at=None,
            purpose=onboarding.TOKEN_PURPOSE_INVITE,
        )
    )
    await session.commit()
    return int(row.id), raw


async def _add_token(session: AsyncSession, *, tenant_id: int, application_id: int, purpose: str) -> str:
    raw = f"{purpose}_{uuid.uuid4().hex}"
    session.add(
        ApplicationAccessToken(
            tenant_id=tenant_id,
            application_id=application_id,
            token=raw,
            token_hash=_token_sha256_hex(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(days=2),
            revoked_at=None,
            purpose=purpose,
        )
    )
    await session.commit()
    return raw


async def _cleanup(session: AsyncSession, application_ids: list[int]) -> None:
    if not application_ids:
        return
    await session.rollback()
    for app_id in application_ids:
        await session.execute(
            text("DELETE FROM domain_event_outbox WHERE aggregate_id = :id"),
            {"id": str(app_id)},
        )
    await session.execute(
        delete(ApplicationAccessToken).where(ApplicationAccessToken.application_id.in_(application_ids))
    )
    await session.execute(delete(PersonApplication).where(PersonApplication.id.in_(application_ids)))
    await session.commit()


def _stored_files(root) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
async def test_dl_capture_cannot_upload_step4_document(
    client: AsyncClient,
    tenant_id: int,
    tenant_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A phone-capture link cannot upload a step-4 document. Invite and document-resume still can."""
    import app.core.storage as storage_mod

    slug = _slug()
    headers = {"host": f"{slug}.truckerp.me"}
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    monkeypatch.setattr(storage_mod.settings, "local_storage_dir", str(storage_root))
    monkeypatch.setattr(storage_mod.settings, "company_docs_dir", None)
    monkeypatch.setattr(storage_mod.settings, "storage_provider", "local")
    monkeypatch.setattr(storage_mod, "_engine", storage_mod.LocalStorageBackend())

    created: list[int] = []
    try:
        draft_id, invite = await _add_app(tenant_session, tenant_id=tenant_id)
        submitted_id, _submitted_invite = await _add_app(
            tenant_session,
            tenant_id=tenant_id,
            status=DriverOnboardingStatus.SUBMITTED.value,
        )
        created.extend([draft_id, submitted_id])
        capture = await _add_token(
            tenant_session,
            tenant_id=tenant_id,
            application_id=draft_id,
            purpose=onboarding.TOKEN_PURPOSE_DL_CAPTURE,
        )
        resume = await _add_token(
            tenant_session,
            tenant_id=tenant_id,
            application_id=submitted_id,
            purpose=onboarding.TOKEN_PURPOSE_DOCUMENT_RESUME,
        )
        before_files = _stored_files(storage_root)

        denied = await client.post(
            "/api/v1/driver-onboarding/applicant/application/document-upload",
            params={"token": capture},
            headers=headers,
            data={"doc_type": "mvr"},
            files={"file": ("mvr.pdf", PDF, "application/pdf")},
        )
        assert denied.status_code == 404
        assert denied.json()["detail"] == "Invalid or expired invite link"
        await tenant_session.rollback()
        draft = await tenant_session.get(PersonApplication, draft_id)
        assert draft is not None
        assert (draft.intake_payload or {}).get("documents") in (None, {})
        assert _stored_files(storage_root) == before_files

        uploaded = await client.post(
            "/api/v1/driver-onboarding/applicant/application/document-upload",
            params={"token": invite},
            headers=headers,
            data={"doc_type": "mvr"},
            files={"file": ("mvr.pdf", PDF, "application/pdf")},
        )
        assert uploaded.status_code == 200, uploaded.text
        invite_key = uploaded.json()["intake_payload"]["documents"]["mvr"]["storage_key"]
        assert re.fullmatch(
            rf"{re.escape(slug)}/applicant_docs/application/{draft_id}/[0-9a-f]{{32}}\.pdf",
            invite_key,
        )

        resumed = await client.post(
            "/api/v1/driver-onboarding/applicant/application/document-upload",
            params={"token": resume},
            headers=headers,
            data={"doc_type": "dot_medical"},
            files={"file": ("medical.pdf", PDF, "application/pdf")},
        )
        assert resumed.status_code == 200, resumed.text
        resume_key = resumed.json()["intake_payload"]["documents"]["dot_medical"]["storage_key"]
        assert re.fullmatch(
            rf"{re.escape(slug)}/applicant_docs/application/{submitted_id}/[0-9a-f]{{32}}\.pdf",
            resume_key,
        )
    finally:
        await _cleanup(tenant_session, created)


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
async def test_applicant_file_exploit_is_blocked_and_owned_downloads_work(
    client: AsyncClient,
    tenant_id: int,
    tenant_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.storage as storage_mod

    slug = _slug()
    headers = {"host": f"{slug}.truckerp.me"}
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    monkeypatch.setattr(storage_mod.settings, "local_storage_dir", str(storage_root))
    monkeypatch.setattr(storage_mod.settings, "company_docs_dir", None)
    monkeypatch.setattr(storage_mod.settings, "storage_provider", "local")
    monkeypatch.setattr(storage_mod, "_engine", storage_mod.LocalStorageBackend())
    backend = storage_mod.get_storage()

    created: list[int] = []
    try:
        attacker_id, invite = await _add_app(tenant_session, tenant_id=tenant_id)
        victim_id, _victim_invite = await _add_app(tenant_session, tenant_id=tenant_id)
        created.extend([attacker_id, victim_id])

        victim_key = f"{slug}/applicant_dl/application/{victim_id}/victim.jpg"
        other_tenant_key = f"acme/applicant_dl/application/{attacker_id}/foreign.jpg"
        own_dl = f"{slug}/applicant_dl/application/{attacker_id}/front.jpg"
        own_enh = f"{slug}/applicant_dl/application/{attacker_id}/front-processed.jpg"
        traversal = f"{slug}/applicant_dl/application/{attacker_id}/../../../../secret.txt"
        secret = tmp_path / "secret.txt"
        secret.write_bytes(b"ABSOLUTE-SECRET")

        def plant(key: str, body: bytes, module: str = "applicant_dl") -> None:
            path = backend._key_to_path(key, module, slug)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)

        plant(victim_key, VICTIM_BYTES)
        plant(other_tenant_key, OTHER_TENANT_BYTES)
        plant(own_dl, b"own-front")
        plant(own_enh, b"own-processed")
        legacy_name = f"{uuid.uuid4().hex}.jpg"
        legacy_path = backend._key_to_path(legacy_name, "applicant_dl", slug)
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_bytes(LEGACY_BYTES)
        other_legacy = f"other-{uuid.uuid4().hex}.jpg"
        other_legacy_path = backend._key_to_path(other_legacy, "applicant_dl", slug)
        other_legacy_path.write_bytes(b"OTHER-LEGACY")

        # Exploit: applicant JSON tries to replace server-owned file pointers.
        planted = await tenant_session.get(PersonApplication, attacker_id)
        assert planted is not None
        planted.intake_payload = {
            "step": "dl_upload",
            "files": {"CDL_FRONT": {"storage_key": own_dl, "file_id": own_dl}},
            "documents": {},
        }
        await tenant_session.commit()

        injected = await client.post(
            "/api/v1/driver-onboarding/applicant/application/intake",
            params={"token": invite},
            headers=headers,
            json={
                "submit": False,
                "intake_payload": {
                    "first_name": "Pat",
                    "files": {
                        "CDL_FRONT": {
                            "storage_key": victim_key,
                            "file_id": victim_key,
                            "enh_file_id": traversal,
                            "dl_preprocess_status": "PROCESSED",
                        }
                    },
                    "documents": {
                        "mvr": {"storage_key": other_tenant_key, "file_id": other_tenant_key},
                    },
                },
            },
        )
        assert injected.status_code == 200, injected.text
        saved = injected.json()["intake_payload"]
        assert saved["first_name"] == "Pat"
        assert saved["files"]["CDL_FRONT"]["storage_key"] == own_dl
        assert saved["documents"] == {}

        async def fetch(token: str, file_id: str, path: str = "/api/v1/driver-onboarding/applicant/application/file"):
            return await client.get(path, params={"token": token, "file_id": file_id}, headers=headers)

        blocked = await fetch(invite, victim_key)
        assert blocked.status_code == 404
        assert VICTIM_BYTES not in blocked.content

        # Directly poisoned intake still cannot read another application, another tenant, or a path escape.
        poisoned = await tenant_session.get(PersonApplication, attacker_id)
        assert poisoned is not None
        poisoned.intake_payload = {
            "step": "dl_upload",
            "files": {
                "CDL_FRONT": {
                    "storage_key": own_dl,
                    "file_id": own_dl,
                    "enh_file_id": victim_key,
                    "dl_preprocess_status": "PROCESSED",
                },
                "CDL_BACK": {
                    "storage_key": other_tenant_key,
                    "file_id": other_tenant_key,
                },
                "TRAVERSAL": {"storage_key": traversal, "file_id": traversal},
                "ABSOLUTE": {"storage_key": str(secret), "file_id": str(secret)},
                "FILENAME_ONLY": {"storage_key": "victim.jpg", "file_id": "victim.jpg"},
            },
            "documents": {
                "mvr": {"storage_key": victim_key, "file_id": victim_key},
            },
        }
        await tenant_session.commit()

        for stolen in (victim_key, other_tenant_key, traversal, str(secret), "victim.jpg"):
            denied = await fetch(invite, stolen)
            assert denied.status_code == 404, stolen
            assert VICTIM_BYTES not in denied.content
            assert OTHER_TENANT_BYTES not in denied.content
            assert b"ABSOLUTE-SECRET" not in denied.content
        # Requesting the real front id must not fall back to a poisoned processed key.
        poisoned_preview = await fetch(invite, own_dl)
        assert poisoned_preview.status_code == 404
        assert VICTIM_BYTES not in poisoned_preview.content

        # Owned processed preview, legacy flat key, and a flat name that is not on this application.
        poisoned.intake_payload = {
            "step": "documents",
            "files": {
                "CDL_FRONT": {
                    "storage_key": own_dl,
                    "file_id": own_dl,
                    "enh_file_id": own_enh,
                    "dl_preprocess_status": "PROCESSED",
                    "original_filename": "front.jpg",
                },
                "LEGACY": {"storage_key": legacy_name, "file_id": legacy_name},
                "PLAIN": {"storage_key": "old-license.jpg", "file_id": "old-license.jpg"},
            },
        }
        await tenant_session.commit()
        preview = await fetch(invite, own_dl)
        assert preview.status_code == 200, preview.text
        assert preview.content == b"own-processed"
        legacy = await fetch(invite, legacy_name)
        assert legacy.status_code == 200, legacy.text
        assert legacy.content == LEGACY_BYTES
        plain = await fetch(invite, "old-license.jpg")
        assert plain.status_code == 404
        missing_legacy = await fetch(invite, other_legacy)
        assert missing_legacy.status_code == 404
        assert b"OTHER-LEGACY" not in missing_legacy.content

        victim = await tenant_session.get(PersonApplication, victim_id)
        assert victim is not None
        victim.intake_payload = {
            "files": {"CDL_FRONT": {"storage_key": legacy_name, "file_id": legacy_name}},
        }
        await tenant_session.commit()
        shared = await fetch(invite, legacy_name)
        assert shared.status_code == 404
        assert LEGACY_BYTES not in shared.content
        victim.intake_payload = {}
        await tenant_session.commit()
        restored = await fetch(invite, legacy_name)
        assert restored.status_code == 200, restored.text
        assert restored.content == LEGACY_BYTES

        # General file endpoint accepts invite and document_resume, and refuses dl_capture.
        resume = await _add_token(
            tenant_session,
            tenant_id=tenant_id,
            application_id=attacker_id,
            purpose=onboarding.TOKEN_PURPOSE_DOCUMENT_RESUME,
        )
        capture = await _add_token(
            tenant_session,
            tenant_id=tenant_id,
            application_id=attacker_id,
            purpose=onboarding.TOKEN_PURPOSE_DL_CAPTURE,
        )
        resume_dl = await fetch(resume, own_enh)
        assert resume_dl.status_code == 200
        assert resume_dl.content == b"own-processed"
        capture_general = await fetch(capture, own_enh)
        assert capture_general.status_code == 404
        capture_file = await fetch(
            capture,
            own_enh,
            path=f"/api/v1/driver-onboarding/applicant/dl-capture/{capture}/file",
        )
        assert capture_file.status_code == 200, capture_file.text
        assert capture_file.content == b"own-processed"
        capture_doc_attempt = await fetch(
            capture,
            victim_key,
            path=f"/api/v1/driver-onboarding/applicant/dl-capture/{capture}/file",
        )
        assert capture_doc_attempt.status_code == 404

        # Submitted document-resume link still cannot overwrite file pointers.
        poisoned.status = DriverOnboardingStatus.SUBMITTED.value
        poisoned.intake_payload = {
            "files": {"CDL_FRONT": {"storage_key": own_dl, "file_id": own_dl}},
            "documents": {"mvr": {"storage_key": f"{slug}/applicant_docs/application/{attacker_id}/keep.pdf", "file_id": "keep"}},
        }
        await tenant_session.commit()
        resume_write = await client.post(
            "/api/v1/driver-onboarding/applicant/application/intake",
            params={"token": resume},
            headers=headers,
            json={
                "submit": False,
                "intake_payload": {
                    "files": {"CDL_FRONT": {"storage_key": victim_key, "file_id": victim_key}},
                    "documents": {"mvr": {"storage_key": other_tenant_key, "file_id": other_tenant_key}},
                    "agree_info_accurate": True,
                },
            },
        )
        assert resume_write.status_code == 200, resume_write.text
        resumed = resume_write.json()["intake_payload"]
        assert resumed["files"]["CDL_FRONT"]["storage_key"] == own_dl
        assert resumed["documents"]["mvr"]["storage_key"].endswith("/keep.pdf")
        assert resumed["agree_info_accurate"] is True

        # Normal document upload + applicant download. Reset to draft so the invite can upload.
        await tenant_session.refresh(poisoned)
        poisoned.status = DriverOnboardingStatus.DRAFT.value
        await tenant_session.commit()
        uploaded = await client.post(
            "/api/v1/driver-onboarding/applicant/application/document-upload",
            params={"token": invite},
            headers=headers,
            data={"doc_type": "mvr"},
            files={"file": ("mvr.pdf", PDF, "application/pdf")},
        )
        assert uploaded.status_code == 200, uploaded.text
        doc_key = uploaded.json()["intake_payload"]["documents"]["mvr"]["storage_key"]
        assert re.fullmatch(
            rf"{re.escape(slug)}/applicant_docs/application/{attacker_id}/[0-9a-f]{{32}}\.pdf",
            doc_key,
        )
        doc_dl = await fetch(invite, doc_key)
        assert doc_dl.status_code == 200, doc_dl.text
        assert doc_dl.content == PDF

        # Normal DL upload stores a tenant UUID key and the applicant can download it.
        dl_up = await client.post(
            "/api/v1/driver-onboarding/applicant/application/dl-upload",
            params={"token": invite},
            headers=headers,
            data={"doc_type": "CDL_FRONT"},
            files={"file": ("license.jpg", JPEG, "image/jpeg")},
        )
        assert dl_up.status_code == 200, dl_up.text
        front = dl_up.json()["intake_payload"]["files"]["CDL_FRONT"]
        assert re.fullmatch(
            rf"{re.escape(slug)}/applicant_dl/application/{attacker_id}/[0-9a-f]{{32}}\.jpg",
            front["storage_key"],
        )
        dl_get = await fetch(invite, front["storage_key"])
        assert dl_get.status_code == 200, dl_get.text
        assert dl_get.content

        # Admin preview is limited to this application's owned keys.
        install_host_aligned_current_user_and_tenant(fastapi_app, role="TENANT_ADMIN")
        try:
            admin_ok = await client.get(
                f"/api/v1/driver-onboarding/applications/{attacker_id}/file",
                params={"file_id": doc_key},
                headers=headers,
            )
            assert admin_ok.status_code == 200, admin_ok.text
            assert admin_ok.content == PDF
            admin_dl = await client.get(
                f"/api/v1/driver-onboarding/applications/{attacker_id}/file",
                params={"file_id": front["storage_key"]},
                headers=headers,
            )
            assert admin_dl.status_code == 200, admin_dl.text
            admin_other = await client.get(
                f"/api/v1/driver-onboarding/applications/{attacker_id}/file",
                params={"file_id": victim_key},
                headers=headers,
            )
            assert admin_other.status_code == 404
            assert VICTIM_BYTES not in admin_other.content
            admin_escape = await client.get(
                f"/api/v1/driver-onboarding/applications/{attacker_id}/file",
                params={"file_id": str(secret)},
                headers=headers,
            )
            assert admin_escape.status_code == 404
            admin_missing_app = await client.get(
                "/api/v1/driver-onboarding/applications/999999999/file",
                params={"file_id": doc_key},
                headers=headers,
            )
            assert admin_missing_app.status_code == 404
        finally:
            clear_current_user_and_tenant_overrides(fastapi_app)

        install_host_aligned_current_user_and_tenant(fastapi_app, role="TENANT_MEMBER")
        try:
            member = await client.get(
                f"/api/v1/driver-onboarding/applications/{attacker_id}/file",
                params={"file_id": doc_key},
                headers=headers,
            )
            assert member.status_code == 403
        finally:
            clear_current_user_and_tenant_overrides(fastapi_app)
    finally:
        clear_current_user_and_tenant_overrides(fastapi_app)
        await _cleanup(tenant_session, created)


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
async def test_general_applicant_routes_require_invite_or_resume_purpose(
    client: AsyncClient,
    tenant_id: int,
    tenant_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dl_capture tokens only work on /applicant/dl-capture/{token}; draft edits need the invite."""
    import app.core.storage as storage_mod

    slug = _slug()
    headers = {"host": f"{slug}.truckerp.me"}
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    monkeypatch.setattr(storage_mod.settings, "local_storage_dir", str(storage_root))
    monkeypatch.setattr(storage_mod.settings, "company_docs_dir", None)
    monkeypatch.setattr(storage_mod.settings, "storage_provider", "local")
    monkeypatch.setattr(storage_mod, "_engine", storage_mod.LocalStorageBackend())
    base = "/api/v1/driver-onboarding/applicant/application"
    invalid = "Invalid or expired invite link"

    created: list[int] = []
    other_tenant_app_id: int | None = None
    try:
        draft_id, invite = await _add_app(
            tenant_session,
            tenant_id=tenant_id,
            intake={"step": "dl_upload", "first_name": "Keep"},
        )
        created.append(draft_id)
        capture = await _add_token(
            tenant_session, tenant_id=tenant_id, application_id=draft_id, purpose=onboarding.TOKEN_PURPOSE_DL_CAPTURE
        )
        resume = await _add_token(
            tenant_session,
            tenant_id=tenant_id,
            application_id=draft_id,
            purpose=onboarding.TOKEN_PURPOSE_DOCUMENT_RESUME,
        )

        async def general_calls(token: str) -> dict[str, object]:
            p = {"token": token}
            return {
                "get": await client.get(base, params=p, headers=headers),
                "put": await client.put(base, params=p, headers=headers, json={"first_name": "Hijack"}),
                "intake": await client.post(
                    f"{base}/intake",
                    params=p,
                    headers=headers,
                    json={"submit": False, "intake_payload": {"first_name": "Hijack"}},
                ),
                "reset": await client.post(f"{base}/reset", params=p, headers=headers),
                "dl_upload": await client.post(
                    f"{base}/dl-upload",
                    params=p,
                    headers=headers,
                    data={"doc_type": "CDL_FRONT"},
                    files={"file": ("license.jpg", JPEG, "image/jpeg")},
                ),
                "dl_confirm": await client.post(
                    f"{base}/dl-confirm", params=p, headers=headers, data={"doc_type": "CDL_FRONT"}
                ),
                "capture_link": await client.post(f"{base}/dl-capture-link", params=p, headers=headers),
                "file": await client.get(f"{base}/file", params={**p, "file_id": "x"}, headers=headers),
                "document_upload": await client.post(
                    f"{base}/document-upload",
                    params=p,
                    headers=headers,
                    data={"doc_type": "mvr"},
                    files={"file": ("mvr.pdf", PDF, "application/pdf")},
                ),
            }

        for name, resp in (await general_calls(capture)).items():
            assert resp.status_code == 404, (name, resp.status_code, resp.text)
            assert resp.json()["detail"] == invalid, name
        await tenant_session.rollback()
        draft = await tenant_session.get(PersonApplication, draft_id)
        assert draft is not None
        assert (draft.intake_payload or {}).get("first_name") == "Keep"
        assert "files" not in (draft.intake_payload or {})
        assert _stored_files(storage_root) == set()

        # Capture routes still accept the capture token.
        capture_get = await client.get(
            f"/api/v1/driver-onboarding/applicant/dl-capture/{capture}", headers=headers
        )
        assert capture_get.status_code == 200, capture_get.text

        # document_resume may read and use intake, but cannot edit or wipe a draft.
        resume_get = await client.get(base, params={"token": resume}, headers=headers)
        assert resume_get.status_code == 200, resume_get.text
        for path, kwargs in (
            ("", {"method": "PUT", "json": {"first_name": "Hijack"}}),
            ("/reset", {"method": "POST"}),
            ("/dl-confirm", {"method": "POST", "data": {"doc_type": "CDL_FRONT"}}),
        ):
            method = kwargs.pop("method")
            resp = await client.request(method, f"{base}{path}", params={"token": resume}, headers=headers, **kwargs)
            assert resp.status_code == 404, (path, resp.text)
            assert resp.json()["detail"] == invalid
        resume_dl = await client.post(
            f"{base}/dl-upload",
            params={"token": resume},
            headers=headers,
            data={"doc_type": "CDL_FRONT"},
            files={"file": ("license.jpg", JPEG, "image/jpeg")},
        )
        assert resume_dl.status_code == 404
        await tenant_session.rollback()
        draft = await tenant_session.get(PersonApplication, draft_id)
        assert (draft.intake_payload or {}).get("first_name") == "Keep"

        # The invite keeps working on every general route.
        ok_get = await client.get(base, params={"token": invite}, headers=headers)
        assert ok_get.status_code == 200, ok_get.text
        ok_put = await client.put(base, params={"token": invite}, headers=headers, json={"first_name": "Pat"})
        assert ok_put.status_code == 200, ok_put.text
        ok_upload = await client.post(
            f"{base}/dl-upload",
            params={"token": invite},
            headers=headers,
            data={"doc_type": "CDL_FRONT"},
            files={"file": ("license.jpg", JPEG, "image/jpeg")},
        )
        assert ok_upload.status_code == 200, ok_upload.text
        ok_reset = await client.post(f"{base}/reset", params={"token": invite}, headers=headers)
        assert ok_reset.status_code == 200, ok_reset.text

        # Stale, revoked and other-tenant invites fail like an unknown token.
        stale_id, stale = await _add_app(tenant_session, tenant_id=tenant_id)
        revoked_id, revoked = await _add_app(tenant_session, tenant_id=tenant_id)
        created.extend([stale_id, revoked_id])
        await tenant_session.execute(
            text("UPDATE application_access_tokens SET expires_at = now() - interval '1 minute' WHERE application_id = :id"),
            {"id": stale_id},
        )
        await tenant_session.execute(
            text("UPDATE application_access_tokens SET revoked_at = now() WHERE application_id = :id"),
            {"id": revoked_id},
        )
        await tenant_session.commit()
        other_tenant_app_id, foreign = await _add_app(tenant_session, tenant_id=tenant_id + 900000)
        unknown = f"invite_{uuid.uuid4().hex}"
        for token in (stale, revoked, foreign, unknown):
            for name, resp in (await general_calls(token)).items():
                assert resp.status_code == 404, (name, resp.text)
                assert resp.json()["detail"] == invalid, name
    finally:
        await _cleanup(tenant_session, created + ([other_tenant_app_id] if other_tenant_app_id else []))


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
async def test_new_invite_stores_hash_only_and_legacy_plaintext_still_resolves(
    client: AsyncClient,
    tenant_id: int,
    tenant_session: AsyncSession,
) -> None:
    from app.core.database import AsyncSessionLocal
    from app.models.platform import OnboardingTokenLookup

    headers = {"host": f"{_slug()}.truckerp.me"}
    created: list[int] = []
    install_host_aligned_current_user_and_tenant(fastapi_app, role="TENANT_ADMIN")
    try:
        resp = await client.post(
            "/api/v1/admin/onboarding/invite-link",
            headers=headers,
            json={"phone": "+15555550100", "application_type": "DRIVER"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        raw = body["token"]
        created.append(int(body["application_id"]))
        assert raw in body["link"]
        clear_current_user_and_tenant_overrides(fastapi_app)

        row = (
            await tenant_session.execute(
                text("SELECT token, token_hash, purpose FROM application_access_tokens WHERE application_id = :id"),
                {"id": body["application_id"]},
            )
        ).one()
        assert row.token is None
        assert row.token_hash == _token_sha256_hex(raw)
        assert row.purpose == onboarding.TOKEN_PURPOSE_INVITE
        async with AsyncSessionLocal() as platform:
            lookups = (
                await platform.execute(
                    text("SELECT token FROM onboarding_token_lookup WHERE tenant_id = :t AND application_id = :a"),
                    {"t": tenant_id, "a": body["application_id"]},
                )
            ).scalars().all()
            assert lookups == [_token_sha256_hex(raw)]
            await platform.execute(
                text("DELETE FROM onboarding_token_lookup WHERE tenant_id = :t AND application_id = :a"),
                {"t": tenant_id, "a": body["application_id"]},
            )
            await platform.commit()

        ok = await client.get(
            "/api/v1/driver-onboarding/applicant/application", params={"token": raw}, headers=headers
        )
        assert ok.status_code == 200, ok.text

        legacy_id, _ = await _add_app(tenant_session, tenant_id=tenant_id)
        created.append(legacy_id)
        legacy_raw = f"legacy_{uuid.uuid4().hex}"
        tenant_session.add(
            ApplicationAccessToken(
                tenant_id=tenant_id,
                application_id=legacy_id,
                token=legacy_raw,
                token_hash=None,
                expires_at=datetime.now(timezone.utc) + timedelta(days=2),
                revoked_at=None,
                purpose=onboarding.TOKEN_PURPOSE_INVITE,
            )
        )
        await tenant_session.commit()
        legacy = await client.get(
            "/api/v1/driver-onboarding/applicant/application", params={"token": legacy_raw}, headers=headers
        )
        assert legacy.status_code == 200, legacy.text
    finally:
        clear_current_user_and_tenant_overrides(fastapi_app)
        await _cleanup(tenant_session, created)


def test_log_redaction_removes_applicant_tokens() -> None:
    import logging

    from app.middleware.tenant_context import AccessLogTokenRedactionFilter, redact_tokens_for_log

    secret = "abcDEF123_-xyz"
    cases = [
        f"/api/v1/driver-onboarding/applicant/dl-capture/{secret}",
        f"/api/v1/driver-onboarding/applicant/dl-capture/{secret}/upload",
        f"/api/v1/driver-onboarding/applicant/application?token={secret}",
        f"/api/v1/driver-onboarding/applicant/application/file?file_id=x&token={secret}&y=1",
        f"/onboarding?token={secret}",
    ]
    for url in cases:
        out = redact_tokens_for_log(url)
        assert secret not in out, out
        assert "[redacted]" in out
    assert redact_tokens_for_log("/api/v1/loads?limit=5") == "/api/v1/loads?limit=5"

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", cases[2], "1.1", 200), None,
    )
    assert AccessLogTokenRedactionFilter().filter(record) is True
    assert secret not in record.getMessage()
    assert "token=[redacted]" in record.getMessage()


class _IdRows:
    def __init__(self, ids: list[int]) -> None:
        self._ids = ids

    def all(self) -> list[tuple[int]]:
        return [(item,) for item in self._ids]


class _FakeTenantDb:
    def __init__(self, ids: list[int]) -> None:
        self.ids = ids
        self.calls = 0

    async def execute(self, _stmt, _params=None):
        self.calls += 1
        return _IdRows(self.ids)


def _s3_backend() -> S3StorageBackend:
    backend = S3StorageBackend.__new__(S3StorageBackend)
    backend._prefix = ""
    backend._bucket = "test-bucket"
    backend._client = MagicMock()
    chunks = [b"owned-bytes", b""]
    body = MagicMock()
    body.read.side_effect = lambda _size=None: chunks.pop(0) if chunks else b""
    backend._client.get_object.return_value = {"Body": body}
    backend._client.head_object.return_value = {}
    return backend


@pytest.mark.asyncio
async def test_mocked_s3_cannot_read_other_applicant_or_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Applicant A never issues GetObject/HeadObject for B or another tenant, including a legacy key."""
    import app.core.storage as storage_mod

    backend = _s3_backend()
    monkeypatch.setattr(storage_mod, "get_storage", lambda: backend)
    application_id = 4
    other_id = 9
    victim = f"pytest/applicant_dl/application/{other_id}/" + ("b" * 32) + ".jpg"
    foreign = f"acme/applicant_dl/application/{application_id}/" + ("c" * 32) + ".jpg"
    legacy = "d" * 32 + ".jpg"
    document_legacy = "e" * 32 + ".pdf"
    intake = {
        "files": {
            "VICTIM": {"storage_key": victim, "file_id": victim},
            "FOREIGN": {"storage_key": foreign, "file_id": foreign},
            "LEGACY": {"storage_key": legacy, "file_id": legacy},
            "PLAIN": {"storage_key": "old-license.jpg", "file_id": "old-license.jpg"},
        },
        "documents": {
            "mvr": {"storage_key": document_legacy, "file_id": document_legacy},
        },
    }
    shared = _FakeTenantDb([application_id, other_id])
    for file_id in (victim, foreign, legacy, "old-license.jpg"):
        denied = await onboarding._serve_application_intake_file(
            intake,
            file_id,
            db=shared,
            tenant_id=1,
            tenant_slug="pytest",
            application_id=application_id,
            include_documents=True,
        )
        assert denied is None, file_id
    backend._client.get_object.assert_not_called()
    backend._client.head_object.assert_not_called()
    assert shared.calls == 1

    sole = _FakeTenantDb([application_id])
    allowed = await onboarding._serve_application_intake_file(
        intake,
        legacy,
        db=sole,
        tenant_id=1,
        tenant_slug="pytest",
        application_id=application_id,
        include_documents=True,
    )
    assert allowed is not None
    payload = b""
    async for chunk in allowed.body_iterator:
        payload += chunk
    assert payload == b"owned-bytes"
    expected = f"pytest/applicant_dl/legacy/0/{legacy}"
    assert backend._client.head_object.call_args.kwargs["Key"] == expected
    assert backend._client.get_object.call_args.kwargs["Key"] == expected
    assert "acme/" not in expected
    assert f"application/{other_id}/" not in expected

    doc = await onboarding._serve_application_intake_file(
        intake,
        document_legacy,
        db=_FakeTenantDb([application_id]),
        tenant_id=1,
        tenant_slug="pytest",
        application_id=application_id,
        include_documents=True,
    )
    assert doc is not None
    assert backend._client.head_object.call_args.kwargs["Key"] == f"pytest/applicant_docs/legacy/0/{document_legacy}"


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
async def test_reset_removes_only_own_applicant_uploads_and_retries_after_partial_failure(
    client: AsyncClient,
    tenant_id: int,
    tenant_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.storage as storage_mod

    slug = _slug()
    headers = {"host": f"{slug}.truckerp.me"}
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    monkeypatch.setattr(storage_mod.settings, "local_storage_dir", str(storage_root))
    monkeypatch.setattr(storage_mod.settings, "company_docs_dir", None)
    monkeypatch.setattr(storage_mod.settings, "storage_provider", "local")
    monkeypatch.setattr(storage_mod, "_engine", storage_mod.LocalStorageBackend())

    created: list[int] = []
    try:
        app_id, invite = await _add_app(tenant_session, tenant_id=tenant_id)
        other_id, other_invite = await _add_app(tenant_session, tenant_id=tenant_id)
        created.extend([app_id, other_id])

        async def upload(token: str, doc_type: str) -> str:
            r = await client.post(
                "/api/v1/driver-onboarding/applicant/application/document-upload",
                params={"token": token},
                headers=headers,
                data={"doc_type": doc_type},
                files={"file": (f"{doc_type}.pdf", PDF, "application/pdf")},
            )
            assert r.status_code == 200, r.text
            return r.json()["intake_payload"]["documents"][doc_type]["storage_key"]

        own_key = await upload(invite, "mvr")
        other_key = await upload(other_invite, "mvr")
        own_dl = storage_root / f"{slug}/applicant_dl/application/{app_id}/front.jpg"
        own_dl.parent.mkdir(parents=True)
        own_dl.write_bytes(b"dl")
        other_tenant_doc = storage_root / f"other-{slug}/applicant_docs/application/{app_id}/x.pdf"
        other_tenant_doc.parent.mkdir(parents=True)
        other_tenant_doc.write_bytes(b"x")

        # Partial failure: applicant_docs purge fails after the DB reset committed.
        real_purge = storage_mod.purge_applicant_dl_application

        def flaky(tenant_slug, application_id, module="applicant_dl"):
            if module == "applicant_docs":
                raise OSError("simulated storage outage")
            return real_purge(tenant_slug, application_id, module)

        monkeypatch.setattr(storage_mod, "purge_applicant_dl_application", flaky)
        r1 = await client.post(
            "/api/v1/driver-onboarding/applicant/application/reset", params={"token": invite}, headers=headers
        )
        assert r1.status_code == 200, r1.text
        assert not (r1.json()["intake_payload"] or {}).get("documents")
        assert not own_dl.exists()
        assert (storage_root / own_key).is_file(), "unreferenced file kept until a later reset"

        monkeypatch.setattr(storage_mod, "purge_applicant_dl_application", real_purge)
        for _ in range(2):  # retry + repeated reset are both safe
            r = await client.post(
                "/api/v1/driver-onboarding/applicant/application/reset", params={"token": invite}, headers=headers
            )
            assert r.status_code == 200, r.text
        assert not (storage_root / own_key).exists()
        assert (storage_root / other_key).is_file()
        assert other_tenant_doc.is_file()
    finally:
        await _cleanup(tenant_session, created)
