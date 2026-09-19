"""Tenant Fuel provider connection persistence (Segment 0A)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelProviderConnection
from app.models.platform_integration import TenantIntegrationSecret
from app.schemas.fuel import (
    FuelProviderConnectionOut,
    FuelProviderConnectionUpdate,
    FuelProviderConnectionWrite,
    FuelSecretStateOut,
)
from app.services.fuel_provider_adapter import (
    FuelAdapterNotImplemented,
    fetch_or_receive_source,
    attempt_test_connection,
    validate_configuration,
)
from app.services.fuel_provider_catalog import secret_field_keys
from app.services.audit_events import write_audit_event
from app.utils.encryption import encrypt_secret, generate_credential_ref

logger = logging.getLogger(__name__)

_INTEGRATION_TYPE = "fuel_provider"
_MASK = "********"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _actor_label(actor: Any) -> str | None:
    email = getattr(actor, "email", None)
    if email:
        return str(email)[:128]
    user = getattr(actor, "user", None)
    if user is not None and getattr(user, "email", None):
        return str(user.email)[:128]
    return None


def _actor_user_id(actor: Any) -> int | None:
    for attr in ("tenant_local_member_id", "member_id", "user_id"):
        raw = getattr(actor, attr, None)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _actor_ref(actor: Any) -> str | None:
    uid = getattr(actor, "user_id", None)
    if uid is None:
        return None
    return str(uid)[:36]


def connection_to_out(row: FuelProviderConnection) -> FuelProviderConnectionOut:
    secret_keys = set(secret_field_keys(row.provider_code, row.connection_method))
    configured = bool(row.credential_ref)
    secrets = {
        key: FuelSecretStateOut(
            configured=configured,
            masked_display=_MASK if configured else None,
        )
        for key in sorted(secret_keys)
    }
    config = dict(row.config_json or {})
    for key in list(config):
        lowered = key.lower()
        if (
            key in secret_keys
            or "password" in lowered
            or lowered in {"api_key", "secret", "token", "credential_ref"}
        ):
            config.pop(key, None)
            if key not in secrets:
                secrets[key] = FuelSecretStateOut(
                    configured=configured,
                    masked_display=_MASK if configured else None,
                )
    return FuelProviderConnectionOut(
        id=row.id,
        tenant_id=row.tenant_id,
        provider_code=row.provider_code,
        connection_method=row.connection_method,
        display_name=row.display_name,
        account_reference=row.account_reference,
        enabled=row.enabled,
        auto_sync_enabled=row.auto_sync_enabled,
        sync_frequency=row.sync_frequency,
        config=config,
        secrets=secrets,
        last_sync_at=row.last_sync_at,
        last_sync_status=row.last_sync_status,
        last_sync_result=row.last_sync_result,
        last_tested_at=row.last_tested_at,
        last_test_status=row.last_test_status,
        last_test_result=row.last_test_result,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _apply_config_fields(row: FuelProviderConnection, config: dict[str, Any]) -> None:
    secret_keys = secret_field_keys(row.provider_code, row.connection_method)
    merged = dict(row.config_json or {})
    merged.update(config)
    for key in secret_keys:
        merged.pop(key, None)
    if "display_name" in config:
        raw = config.get("display_name")
        row.display_name = str(raw).strip()[:255] if raw else None
    if "account_reference" in config:
        raw = config.get("account_reference")
        row.account_reference = str(raw).strip()[:128] if raw else None
    row.config_json = merged


async def _store_secrets(
    platform_db: AsyncSession,
    *,
    tenant_id: int,
    provider_code: str,
    existing_ref: str | None,
    secrets: dict[str, str],
) -> str | None:
    if not secrets and not existing_ref:
        return None
    if not secrets:
        return existing_ref

    payload = json.dumps(secrets, separators=(",", ":"))
    blob = encrypt_secret(payload)
    if existing_ref:
        result = await platform_db.execute(
            select(TenantIntegrationSecret).where(
                TenantIntegrationSecret.credential_ref == existing_ref,
                TenantIntegrationSecret.tenant_id == tenant_id,
            )
        )
        secret_row = result.scalar_one_or_none()
        if secret_row is None:
            ref = generate_credential_ref()
            platform_db.add(
                TenantIntegrationSecret(
                    tenant_id=tenant_id,
                    integration_type=_INTEGRATION_TYPE,
                    provider=provider_code[:50],
                    credential_ref=ref,
                    encrypted_payload=blob,
                )
            )
            return ref
        secret_row.encrypted_payload = blob
        secret_row.provider = provider_code[:50]
        secret_row.integration_type = _INTEGRATION_TYPE
        return existing_ref

    ref = generate_credential_ref()
    platform_db.add(
        TenantIntegrationSecret(
            tenant_id=tenant_id,
            integration_type=_INTEGRATION_TYPE,
            provider=provider_code[:50],
            credential_ref=ref,
            encrypted_payload=blob,
        )
    )
    return ref


async def _audit(
    tenant_db: AsyncSession,
    *,
    tenant_id: int,
    row: FuelProviderConnection,
    action: str,
    actor: Any,
    snapshot_after: dict[str, Any],
) -> None:
    await write_audit_event(
        tenant_db,
        tenant_id=tenant_id,
        module="fuel",
        entity_type="fuel_provider_connection",
        entity_id=str(row.id),
        entity_label=(row.display_name or row.provider_code)[:256],
        action=action,
        source="api",
        actor_type="user",
        actor_user_id=_actor_user_id(actor),
        actor_label=_actor_label(actor),
        snapshot_after=snapshot_after,
        visibility="admin_sensitive",
        best_effort=True,
    )


def _public_snapshot(row: FuelProviderConnection) -> dict[str, Any]:
    return {
        "id": row.id,
        "provider_code": row.provider_code,
        "connection_method": row.connection_method,
        "display_name": row.display_name,
        "account_reference": row.account_reference,
        "enabled": row.enabled,
        "auto_sync_enabled": row.auto_sync_enabled,
        "secrets_configured": bool(row.credential_ref),
    }


async def list_connections(
    tenant_db: AsyncSession, *, tenant_id: int
) -> list[FuelProviderConnection]:
    result = await tenant_db.execute(
        select(FuelProviderConnection)
        .where(FuelProviderConnection.tenant_id == tenant_id)
        .order_by(FuelProviderConnection.provider_code, FuelProviderConnection.id)
    )
    return list(result.scalars().all())


async def get_connection(
    tenant_db: AsyncSession, *, tenant_id: int, connection_id: int
) -> FuelProviderConnection | None:
    result = await tenant_db.execute(
        select(FuelProviderConnection).where(
            FuelProviderConnection.tenant_id == tenant_id,
            FuelProviderConnection.id == connection_id,
        )
    )
    return result.scalar_one_or_none()


async def create_connection(
    tenant_db: AsyncSession,
    platform_db: AsyncSession,
    *,
    tenant_id: int,
    payload: FuelProviderConnectionWrite,
    actor: Any,
) -> FuelProviderConnection:
    config, secrets = validate_configuration(
        provider_code=payload.provider_code,
        connection_method=payload.connection_method,
        fields=payload.fields,
        require_secrets=True,
    )
    row = FuelProviderConnection(
        tenant_id=tenant_id,
        provider_code=payload.provider_code,
        connection_method=payload.connection_method,
        enabled=payload.enabled,
        auto_sync_enabled=payload.auto_sync_enabled,
        sync_frequency=payload.sync_frequency,
        config_json={},
        created_by=_actor_ref(actor),
        updated_by=_actor_ref(actor),
    )
    _apply_config_fields(row, config)
    tenant_db.add(row)
    await tenant_db.flush()

    row.credential_ref = await _store_secrets(
        platform_db,
        tenant_id=tenant_id,
        provider_code=payload.provider_code,
        existing_ref=None,
        secrets=secrets,
    )
    logger.info(
        "fuel_provider_connection created tenant_id=%s id=%s provider=%s method=%s secrets_configured=%s",
        tenant_id,
        row.id,
        row.provider_code,
        row.connection_method,
        bool(row.credential_ref),
    )
    await _audit(
        tenant_db,
        tenant_id=tenant_id,
        row=row,
        action="create",
        actor=actor,
        snapshot_after=_public_snapshot(row),
    )
    await platform_db.commit()
    await tenant_db.commit()
    await tenant_db.refresh(row)
    return row


async def update_connection(
    tenant_db: AsyncSession,
    platform_db: AsyncSession,
    *,
    tenant_id: int,
    row: FuelProviderConnection,
    payload: FuelProviderConnectionUpdate,
    actor: Any,
) -> FuelProviderConnection:
    method = payload.connection_method or row.connection_method
    merged_fields = dict(row.config_json or {})
    if payload.fields:
        merged_fields.update(payload.fields)
    existing_secret_keys = (
        secret_field_keys(row.provider_code, method) if row.credential_ref else frozenset()
    )
    config, secrets = validate_configuration(
        provider_code=row.provider_code,
        connection_method=method,
        fields=merged_fields,
        existing_secret_keys=existing_secret_keys,
        require_secrets=not bool(row.credential_ref),
    )
    row.connection_method = method
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.auto_sync_enabled is not None:
        row.auto_sync_enabled = payload.auto_sync_enabled
    if payload.sync_frequency is not None:
        row.sync_frequency = payload.sync_frequency
    _apply_config_fields(row, config)
    if secrets:
        row.credential_ref = await _store_secrets(
            platform_db,
            tenant_id=tenant_id,
            provider_code=row.provider_code,
            existing_ref=row.credential_ref,
            secrets=secrets,
        )
    row.updated_by = _actor_ref(actor)
    logger.info(
        "fuel_provider_connection updated tenant_id=%s id=%s provider=%s method=%s secrets_updated=%s",
        tenant_id,
        row.id,
        row.provider_code,
        row.connection_method,
        bool(secrets),
    )
    await _audit(
        tenant_db,
        tenant_id=tenant_id,
        row=row,
        action="update",
        actor=actor,
        snapshot_after=_public_snapshot(row),
    )
    await platform_db.commit()
    await tenant_db.commit()
    await tenant_db.refresh(row)
    return row


async def run_test_connection(
    tenant_db: AsyncSession,
    *,
    tenant_id: int,
    row: FuelProviderConnection,
    actor: Any,
) -> dict[str, Any]:
    now = _utcnow()
    try:
        attempt_test_connection(provider_code=row.provider_code, connection_method=row.connection_method)
    except FuelAdapterNotImplemented as exc:
        payload = exc.as_payload()
        row.last_tested_at = now
        row.last_test_status = exc.result
        row.last_test_result = exc.result
        row.updated_by = _actor_ref(actor)
        logger.info(
            "fuel_provider_connection test tenant_id=%s id=%s result=%s",
            tenant_id,
            row.id,
            exc.result,
        )
        await _audit(
            tenant_db,
            tenant_id=tenant_id,
            row=row,
            action="test_connection",
            actor=actor,
            snapshot_after={**_public_snapshot(row), "result": exc.result, "success": False, "attempted": False},
        )
        await tenant_db.commit()
        return payload
    raise RuntimeError("Fuel attempt_test_connection must not succeed in Segment 0A")


async def run_sync(
    tenant_db: AsyncSession,
    *,
    tenant_id: int,
    row: FuelProviderConnection,
    actor: Any,
) -> dict[str, Any]:
    now = _utcnow()
    try:
        fetch_or_receive_source(provider_code=row.provider_code, connection_method=row.connection_method)
    except FuelAdapterNotImplemented as exc:
        payload = exc.as_payload()
        row.last_sync_at = now
        row.last_sync_status = exc.result
        row.last_sync_result = exc.result
        row.updated_by = _actor_ref(actor)
        logger.info(
            "fuel_provider_connection sync tenant_id=%s id=%s result=%s",
            tenant_id,
            row.id,
            exc.result,
        )
        await _audit(
            tenant_db,
            tenant_id=tenant_id,
            row=row,
            action="sync",
            actor=actor,
            snapshot_after={**_public_snapshot(row), "result": exc.result, "success": False, "attempted": False},
        )
        await tenant_db.commit()
        return payload
    raise RuntimeError("Fuel sync must not succeed in Segment 0A")
