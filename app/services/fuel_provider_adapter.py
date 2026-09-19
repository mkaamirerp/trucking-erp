"""Fuel provider adapter boundary (Segment 0A).

Live fetch/test/sync/parse are not implemented. Callers must surface
`connection_method_not_implemented` instead of simulating success.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.services.fuel_provider_catalog import (
    CONNECTION_METHOD_NOT_IMPLEMENTED,
    EVIDENCE_UNVERIFIED,
    connection_method_is_selectable,
    get_connection_method_schema,
    get_provider_catalog_entry,
    non_secret_field_keys,
    secret_field_keys,
)

_NOT_IMPLEMENTED_MESSAGE = (
    "Connection method not implemented. No provider connection was attempted. "
    "TruckERP will not open a network session or pretend connectivity works."
)


class FuelAdapterNotImplemented(Exception):
    def __init__(self, provider_code: str, connection_method: str):
        self.provider_code = provider_code
        self.connection_method = connection_method
        self.result = CONNECTION_METHOD_NOT_IMPLEMENTED
        super().__init__(_NOT_IMPLEMENTED_MESSAGE)

    def as_payload(self) -> dict[str, Any]:
        return {
            "success": False,
            "attempted": False,
            "result": self.result,
            "provider_code": self.provider_code,
            "connection_method": self.connection_method,
            "message": _NOT_IMPLEMENTED_MESSAGE,
        }


def validate_configuration(
    *,
    provider_code: str,
    connection_method: str,
    fields: dict[str, Any],
    existing_secret_keys: frozenset[str] | None = None,
    require_secrets: bool = True,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Split and validate catalog fields. Raises HTTPException on contract errors."""
    entry = get_provider_catalog_entry(provider_code)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "UNKNOWN_FUEL_PROVIDER", "detail": f"Unknown provider: {provider_code}"},
        )
    schema = get_connection_method_schema(provider_code, connection_method)
    if schema is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "UNSUPPORTED_CONNECTION_METHOD",
                "detail": f"{provider_code} does not support connection method {connection_method}",
            },
        )
    if schema.get("evidence_status") == EVIDENCE_UNVERIFIED or not connection_method_is_selectable(
        provider_code, connection_method
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "UNVERIFIED_CONNECTION_METHOD",
                "detail": (
                    f"{provider_code} connection method {connection_method} is unverified/"
                    "unsupported until captured provider evidence exists. It cannot be configured."
                ),
            },
        )
    allowed = {str(f["key"]) for f in schema["fields"]}
    unknown = sorted(set(fields or {}) - allowed)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "UNKNOWN_CONNECTION_FIELDS",
                "detail": "Fields are not defined by this provider/method schema.",
                "fields": unknown,
            },
        )
    if any(k.lower() in {"host", "sftp_host", "hostname", "endpoint", "base_url"} for k in (fields or {})):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "ARBITRARY_HOST_FORBIDDEN",
                "detail": "Provider hosts are backend-allowlisted; arbitrary host fields are not accepted.",
            },
        )

    secrets: dict[str, str] = {}
    config: dict[str, Any] = {}
    have_secrets = existing_secret_keys or frozenset()
    for field in schema["fields"]:
        key = str(field["key"])
        raw = (fields or {}).get(key, None)
        is_secret = bool(field.get("secret"))
        required = bool(field.get("required"))
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            if required and is_secret and require_secrets and key not in have_secrets:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "MISSING_REQUIRED_FIELD", "field": key},
                )
            if required and not is_secret:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "MISSING_REQUIRED_FIELD", "field": key},
                )
            continue
        if is_secret:
            if not isinstance(raw, str):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "INVALID_SECRET_FIELD", "field": key},
                )
            secrets[key] = raw
        else:
            if isinstance(raw, str):
                config[key] = raw.strip()
            else:
                config[key] = raw

    extra_non_secret = non_secret_field_keys(provider_code, connection_method)
    extra_secret = secret_field_keys(provider_code, connection_method)
    _ = extra_non_secret, extra_secret
    return config, secrets


def attempt_test_connection(*, provider_code: str, connection_method: str) -> dict[str, str]:
    raise FuelAdapterNotImplemented(provider_code, connection_method)


def fetch_or_receive_source(*, provider_code: str, connection_method: str) -> dict[str, str]:
    raise FuelAdapterNotImplemented(provider_code, connection_method)


def parse_structured_source(*, provider_code: str, connection_method: str) -> dict[str, str]:
    raise FuelAdapterNotImplemented(provider_code, connection_method)
