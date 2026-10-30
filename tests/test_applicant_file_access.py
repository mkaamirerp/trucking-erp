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
