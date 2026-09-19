"""Fuel Segment 0A: provider catalog, RBAC, secrets, adapter, API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps.fuel_rbac import (
    FUEL_PROVIDERS_MANAGE,
    FUEL_PROVIDERS_SYNC,
    FUEL_PROVIDERS_TEST_CONNECTION,
    FUEL_PROVIDERS_VIEW,
    fuel_capability_allowed,
)
from app.schemas.fuel import FuelProviderConnectionWrite
from app.services.fuel_provider_adapter import (
    FuelAdapterNotImplemented,
    fetch_or_receive_source,
    parse_structured_source,
    attempt_test_connection,
    validate_configuration,
)
from app.services.fuel_provider_catalog import (
    CONNECTION_METHOD_NOT_IMPLEMENTED,
    get_connection_method_schema,
    get_provider_catalog_entry,
    list_provider_catalog,
    secret_field_keys,
)
from app.services.fuel_provider_connections import connection_to_out, create_connection, _store_secrets
from app.utils import encryption as encryption_mod


def test_catalog_contains_locked_providers_and_no_live_adapters() -> None:
    catalog = list_provider_catalog()
    codes = [p["provider_code"] for p in catalog]
    assert codes == [
        "BVD",
        "NATIONWIDE",
        "PILOT_FLYING_J",
        "LOVES",
        "WEX",
        "EFS_TCHEK",
        "COMDATA",
    ]
    assert all(p["live_adapter_implemented"] is False for p in catalog)
    for provider in catalog:
        for method in provider["connection_methods"]:
            assert method["live_adapter_implemented"] is False
            assert method["test_connection_capability"] is False
            assert method["sync_capability"] is False
            keys = {f["key"] for f in method["fields"]}
            assert "host" not in keys
            assert "sftp_host" not in keys
            assert "endpoint" not in keys
            assert "base_url" not in keys
        for code in provider["supported_connection_methods"]:
            schema = get_connection_method_schema(provider["provider_code"], code)
            assert schema is not None
            assert schema["selectable"] is True
            assert schema["evidence_status"] == "evidenced"
        for code in provider["unverified_connection_methods"]:
            schema = get_connection_method_schema(provider["provider_code"], code)
            assert schema is not None
            assert schema["selectable"] is False
            assert schema["evidence_status"] == "unverified"
            assert schema["fields"] == []


def test_catalog_only_evidenced_methods_are_selectable() -> None:
    bvd = get_provider_catalog_entry("bvd")
    assert bvd is not None
    assert bvd["supported_connection_methods"] == ["PDF_UPLOAD", "STRUCTURED_FILE_UPLOAD"]
    assert bvd["unverified_connection_methods"] == []
    nationwide = get_provider_catalog_entry("NATIONWIDE")
    assert nationwide is not None
    assert nationwide["supported_connection_methods"] == ["PDF_UPLOAD"]
    assert "STRUCTURED_FILE_UPLOAD" not in nationwide["supported_connection_methods"]
    for code in ("PILOT_FLYING_J", "LOVES", "WEX", "EFS_TCHEK", "COMDATA"):
        entry = get_provider_catalog_entry(code)
        assert entry is not None
        assert entry["supported_connection_methods"] == []
        assert entry["default_connection_method"] is None
        assert entry["unverified_connection_methods"]
    wex = get_provider_catalog_entry("WEX")
    assert wex is not None
    assert "REST_API" in wex["unverified_connection_methods"]
    assert "REST_API" not in wex["supported_connection_methods"]


def test_catalog_drives_method_fields_not_a_universal_form() -> None:
    bvd = get_provider_catalog_entry("bvd")
    assert bvd is not None
    pdf = get_connection_method_schema("BVD", "PDF_UPLOAD")
    assert pdf is not None
    pdf_keys = {f["key"] for f in pdf["fields"]}
    assert "display_name" in pdf_keys
    assert "account_reference" in pdf_keys
    assert "sftp_password" not in pdf_keys
    assert "api_key" not in pdf_keys
    nationwide = get_connection_method_schema("NATIONWIDE", "PDF_UPLOAD")
    assert nationwide is not None
    assert nationwide["selectable"] is True
    sftp = get_connection_method_schema("PILOT_FLYING_J", "SFTP")
    assert sftp is not None
    assert sftp["selectable"] is False
    assert sftp["fields"] == []


def test_validate_configuration_rejects_unknown_provider_and_arbitrary_host() -> None:
    with pytest.raises(HTTPException) as unknown:
        validate_configuration(provider_code="NOT_A_VENDOR", connection_method="PDF_UPLOAD", fields={})
    assert unknown.value.status_code == 422
    with pytest.raises(HTTPException) as host:
        validate_configuration(
            provider_code="BVD",
            connection_method="PDF_UPLOAD",
            fields={"display_name": "acct", "sftp_host": "evil.example"},
        )
    assert host.value.status_code == 422
    assert host.value.detail["code"] in {"UNKNOWN_CONNECTION_FIELDS", "ARBITRARY_HOST_FORBIDDEN"}


def test_validate_configuration_rejects_unverified_methods() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_configuration(
            provider_code="PILOT_FLYING_J",
            connection_method="SFTP",
            fields={"sftp_username": "u", "sftp_password": "p"},
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "UNVERIFIED_CONNECTION_METHOD"
    with pytest.raises(HTTPException) as wex:
        validate_configuration(
            provider_code="WEX",
            connection_method="REST_API",
            fields={"api_key": "k"},
        )
    assert wex.value.detail["code"] == "UNVERIFIED_CONNECTION_METHOD"


def test_validate_configuration_accepts_evidenced_bvd_pdf() -> None:
    config, secrets = validate_configuration(
        provider_code="BVD",
        connection_method="PDF_UPLOAD",
        fields={"display_name": "BVD main", "account_reference": "acct-1"},
    )
    assert config["display_name"] == "BVD main"
    assert config["account_reference"] == "acct-1"
    assert secrets == {}


def test_adapters_never_simulate_connectivity() -> None:
    for fn in (attempt_test_connection, fetch_or_receive_source, parse_structured_source):
        with pytest.raises(FuelAdapterNotImplemented) as exc:
            fn(provider_code="BVD", connection_method="PDF_UPLOAD")
        assert exc.value.result == CONNECTION_METHOD_NOT_IMPLEMENTED
        payload = exc.value.as_payload()
        assert payload["result"] == "connection_method_not_implemented"
        assert payload["success"] is False
        assert payload["attempted"] is False
        assert "no provider connection was attempted" in payload["message"].lower()


@pytest.mark.parametrize(
    "role,capability,allowed",
    [
        ("TENANT_ADMIN", FUEL_PROVIDERS_VIEW, True),
        ("OWNER", FUEL_PROVIDERS_MANAGE, True),
        ("ADMIN", FUEL_PROVIDERS_TEST_CONNECTION, True),
        ("TENANT_OWNER", FUEL_PROVIDERS_SYNC, True),
        ("TENANT_MEMBER", FUEL_PROVIDERS_VIEW, False),
        ("TENANT_MEMBER", FUEL_PROVIDERS_MANAGE, False),
        ("TENANT_MEMBER", FUEL_PROVIDERS_TEST_CONNECTION, False),
        ("TENANT_MEMBER", FUEL_PROVIDERS_SYNC, False),
        (None, FUEL_PROVIDERS_MANAGE, False),
    ],
)
def test_fuel_rbac_maps_admin_roles_only(role: str | None, capability: str, allowed: bool) -> None:
    assert fuel_capability_allowed(role, capability) is allowed


def test_connection_to_out_never_returns_secret_or_credential_ref() -> None:
    row = SimpleNamespace(
        id=9,
        tenant_id=53,
        provider_code="PILOT_FLYING_J",
        connection_method="SFTP",
        display_name="Pilot acct",
        account_reference="A-1",
        enabled=True,
        auto_sync_enabled=False,
        sync_frequency=None,
        credential_ref="should-never-appear",
        config_json={"sftp_username": "pilot-user", "sftp_password": "leaked"},
        last_sync_at=None,
        last_sync_status=None,
        last_sync_result=None,
        last_tested_at=None,
        last_test_status=None,
        last_test_result=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    out = connection_to_out(row)  # type: ignore[arg-type]
    dumped = out.model_dump(mode="json")
    blob = json.dumps(dumped)
    assert "should-never-appear" not in blob
    assert "leaked" not in blob
    assert dumped["config"].get("sftp_password") is None
    assert dumped["secrets"]["sftp_password"]["configured"] is True
    assert dumped["secrets"]["sftp_password"]["masked_display"] == "********"
    assert dumped["config"]["sftp_username"] == "pilot-user"


@pytest.mark.asyncio
async def test_create_connection_keeps_two_bvd_accounts_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.fuel_provider_connections.write_audit_event",
        AsyncMock(return_value=None),
    )

    tenant_rows: list[object] = []
    tenant_db = AsyncMock()
    platform_db = AsyncMock()
    platform_db.commit = AsyncMock()

    async def flush() -> None:
        row = tenant_rows[-1]
        row.id = len(tenant_rows)
        now = datetime.now(timezone.utc)
        row.created_at = now
        row.updated_at = now

    async def refresh(row) -> None:
        return None

    tenant_db.add = tenant_rows.append
    tenant_db.flush = flush
    tenant_db.commit = AsyncMock()
    tenant_db.refresh = refresh

    actor = SimpleNamespace(user_id="1", member_id=1, email="admin@example.com", user=None)
    first = await create_connection(
        tenant_db,
        platform_db,
        tenant_id=53,
        payload=FuelProviderConnectionWrite(
            provider_code="BVD",
            connection_method="PDF_UPLOAD",
            fields={"display_name": "BVD one", "account_reference": "acct-1"},
        ),
        actor=actor,
    )
    second = await create_connection(
        tenant_db,
        platform_db,
        tenant_id=53,
        payload=FuelProviderConnectionWrite(
            provider_code="BVD",
            connection_method="PDF_UPLOAD",
            fields={"display_name": "BVD two", "account_reference": "acct-2"},
        ),
        actor=actor,
    )
    assert first.id != second.id
    assert first.account_reference == "acct-1"
    assert second.account_reference == "acct-2"
    assert first.provider_code == second.provider_code == "BVD"
    assert first.credential_ref is None
    assert second.credential_ref is None


@pytest.mark.asyncio
async def test_store_secrets_encrypts_payload_and_never_returns_plaintext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(
        "app.core.config.settings.integration_secret_encryption_key",
        key,
    )
    encryption_mod._fernet = None
    added_platform: list[object] = []
    platform_db = AsyncMock()
    platform_db.add = added_platform.append
    ref = await _store_secrets(
        platform_db,
        tenant_id=53,
        provider_code="BVD",
        existing_ref=None,
        secrets={"sftp_password": "secret-one"},
    )
    assert ref
    assert len(added_platform) == 1
    raw = encryption_mod.decrypt_secret(added_platform[0].encrypted_payload)
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["sftp_password"] == "secret-one"
    assert added_platform[0].integration_type == "fuel_provider"
    blob = json.dumps(connection_to_out(
        SimpleNamespace(
            id=1,
            tenant_id=53,
            provider_code="BVD",
            connection_method="PDF_UPLOAD",
            display_name="BVD",
            account_reference=None,
            enabled=True,
            auto_sync_enabled=False,
            sync_frequency=None,
            credential_ref=ref,
            config_json={"sftp_password": "secret-one"},
            last_sync_at=None,
            last_sync_status=None,
            last_sync_result=None,
            last_tested_at=None,
            last_test_status=None,
            last_test_result=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )  # type: ignore[arg-type]
    ).model_dump(mode="json"))
    assert "secret-one" not in blob


def _fuel_app():
    from app.routers.fuel import router as fuel_router

    mini = FastAPI()
    mini.include_router(fuel_router, prefix="/api/v1")
    return mini


def _install_auth(app, *, role: str, tenant_id: int = 53):
    from app.core.database import get_db
    from app.deps.auth import get_current_user
    from app.deps.entitlements import require_admin_sensitive_entitlement
    from app.deps.tenant import require_tenant
    from app.deps.tenant_db import get_tenant_db

    async def _user():
        return SimpleNamespace(
            user_id=1,
            tenant_id=tenant_id,
            role=role,
            email="admin@example.com",
            member_id=1,
            user=SimpleNamespace(email="admin@example.com"),
        )

    async def _skip_entitlement():
        return None

    async def _fake_tenant_db():
        yield AsyncMock()

    async def _fake_platform_db():
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[require_tenant] = lambda: tenant_id
    app.dependency_overrides[require_admin_sensitive_entitlement] = _skip_entitlement
    app.dependency_overrides[get_tenant_db] = _fake_tenant_db
    app.dependency_overrides[get_db] = _fake_platform_db


@pytest.fixture
def api_client():
    app = _fuel_app()
    app.dependency_overrides.clear()
    yield app
    app.dependency_overrides.clear()


def test_catalog_api_driven_by_backend(api_client) -> None:
    _install_auth(api_client, role="TENANT_ADMIN")
    client = TestClient(api_client)
    resp = client.get("/api/v1/fuel/providers", headers={"host": "pytest.truckerp.me"})
    assert resp.status_code == 200
    data = resp.json()
    assert [p["provider_code"] for p in data][0] == "BVD"
    bvd = client.get("/api/v1/fuel/providers/BVD", headers={"host": "pytest.truckerp.me"})
    assert bvd.status_code == 200
    methods = {m["connection_method"] for m in bvd.json()["connection_methods"] if m["selectable"]}
    assert "PDF_UPLOAD" in methods
    assert "REST_API" not in methods
    assert bvd.json()["unverified_connection_methods"] == []
    wex = client.get("/api/v1/fuel/providers/WEX", headers={"host": "pytest.truckerp.me"})
    assert wex.status_code == 200
    assert wex.json()["supported_connection_methods"] == []
    assert "REST_API" in wex.json()["unverified_connection_methods"]


def test_member_cannot_manage_test_or_sync(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_auth(api_client, role="TENANT_MEMBER")
    client = TestClient(api_client)
    headers = {"host": "pytest.truckerp.me"}
    assert client.get("/api/v1/fuel/providers", headers=headers).status_code == 403
    create = client.post(
        "/api/v1/fuel/provider-connections",
        headers=headers,
        json={"provider_code": "BVD", "connection_method": "PDF_UPLOAD", "fields": {}},
    )
    assert create.status_code == 403
    assert create.json()["detail"]["capability"] == FUEL_PROVIDERS_MANAGE
    assert client.post("/api/v1/fuel/provider-connections/1/test", headers=headers).status_code == 403
    assert client.post("/api/v1/fuel/provider-connections/1/sync", headers=headers).status_code == 403


def test_unauthenticated_fuel_routes_rejected(api_client) -> None:
    client = TestClient(api_client)
    resp = client.get("/api/v1/fuel/providers", headers={"host": "pytest.truckerp.me"})
    assert resp.status_code in (401, 400, 403)


def test_get_connection_404_for_other_tenant(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_auth(api_client, role="TENANT_ADMIN", tenant_id=53)
    monkeypatch.setattr(
        "app.services.fuel_provider_connections.get_connection",
        AsyncMock(return_value=None),
    )
    client = TestClient(api_client)
    resp = client.get("/api/v1/fuel/provider-connections/99", headers={"host": "pytest.truckerp.me"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_test_and_sync_persist_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.fuel_provider_connections.write_audit_event",
        AsyncMock(return_value=None),
    )
    from app.services.fuel_provider_connections import run_sync, run_test_connection

    row = SimpleNamespace(
        id=3,
        tenant_id=53,
        provider_code="BVD",
        connection_method="PDF_UPLOAD",
        display_name="BVD",
        account_reference=None,
        enabled=True,
        auto_sync_enabled=False,
        credential_ref=None,
        last_tested_at=None,
        last_test_status=None,
        last_test_result=None,
        last_sync_at=None,
        last_sync_status=None,
        last_sync_result=None,
        updated_by=None,
    )
    db = AsyncMock()
    actor = SimpleNamespace(user_id="1", member_id=1, email="a@b.c", user=None)
    test_out = await run_test_connection(db, tenant_id=53, row=row, actor=actor)
    assert test_out["result"] == "connection_method_not_implemented"
    assert test_out["success"] is False
    assert test_out["attempted"] is False
    assert row.last_test_status == "connection_method_not_implemented"
    sync_out = await run_sync(db, tenant_id=53, row=row, actor=actor)
    assert sync_out["result"] == "connection_method_not_implemented"
    assert sync_out["success"] is False
    assert sync_out["attempted"] is False
    assert row.last_sync_status == "connection_method_not_implemented"
    db.commit.assert_awaited()


def test_secret_field_keys_for_pdf_empty() -> None:
    assert secret_field_keys("BVD", "PDF_UPLOAD") == frozenset()
    assert secret_field_keys("LOVES", "SFTP") == frozenset()
    assert secret_field_keys("WEX", "REST_API") == frozenset()


def test_unverified_method_create_rejected_by_api(api_client) -> None:
    _install_auth(api_client, role="TENANT_ADMIN")
    client = TestClient(api_client)
    resp = client.post(
        "/api/v1/fuel/provider-connections",
        headers={"host": "pytest.truckerp.me"},
        json={"provider_code": "WEX", "connection_method": "REST_API", "fields": {"api_key": "k"}},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "UNVERIFIED_CONNECTION_METHOD"
