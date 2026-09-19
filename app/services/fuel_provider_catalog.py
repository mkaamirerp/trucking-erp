"""Backend-owned Fuel/Card provider catalog (Segment 0A).

Tenants select from this catalog. They do not redefine what a vendor means.

A connection method is selectable only when Fuel design/research already
captured evidence for that intake path. Unverified methods stay listed as
unverified/unsupported and cannot be configured. Live machine adapters are
not implemented; catalog metadata must not imply Test Connection / Sync
will succeed.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Final

CONNECTION_METHOD_PDF_UPLOAD = "PDF_UPLOAD"
CONNECTION_METHOD_STRUCTURED_FILE_UPLOAD = "STRUCTURED_FILE_UPLOAD"
CONNECTION_METHOD_FILE_EXPORT = "FILE_EXPORT"
CONNECTION_METHOD_SFTP = "SFTP"
CONNECTION_METHOD_DATA_SHARING = "DATA_SHARING"
CONNECTION_METHOD_REST_API = "REST_API"
CONNECTION_METHOD_MANUAL_DRIVER = "MANUAL_DRIVER"

KNOWN_CONNECTION_METHODS: Final[frozenset[str]] = frozenset(
    {
        CONNECTION_METHOD_PDF_UPLOAD,
        CONNECTION_METHOD_STRUCTURED_FILE_UPLOAD,
        CONNECTION_METHOD_FILE_EXPORT,
        CONNECTION_METHOD_SFTP,
        CONNECTION_METHOD_DATA_SHARING,
        CONNECTION_METHOD_REST_API,
        CONNECTION_METHOD_MANUAL_DRIVER,
    }
)

CONNECTION_METHOD_NOT_IMPLEMENTED = "connection_method_not_implemented"

EVIDENCE_EVIDENCED = "evidenced"
EVIDENCE_UNVERIFIED = "unverified"

FIELD_TYPE_TEXT = "text"
FIELD_TYPE_SECRET = "secret"
FIELD_TYPE_BOOLEAN = "boolean"

_ACCOUNT_REFERENCE_FIELD: dict[str, Any] = {
    "key": "account_reference",
    "label": "Account / Customer Reference",
    "type": FIELD_TYPE_TEXT,
    "required": False,
    "secret": False,
}

_DISPLAY_NAME_FIELD: dict[str, Any] = {
    "key": "display_name",
    "label": "Connection name",
    "type": FIELD_TYPE_TEXT,
    "required": False,
    "secret": False,
}

_SFTP_USERNAME_FIELD: dict[str, Any] = {
    "key": "sftp_username",
    "label": "SFTP Username",
    "type": FIELD_TYPE_TEXT,
    "required": True,
    "secret": False,
}

_SFTP_PASSWORD_FIELD: dict[str, Any] = {
    "key": "sftp_password",
    "label": "SFTP Password",
    "type": FIELD_TYPE_SECRET,
    "required": True,
    "secret": True,
}

_API_KEY_FIELD: dict[str, Any] = {
    "key": "api_key",
    "label": "API key",
    "type": FIELD_TYPE_SECRET,
    "required": True,
    "secret": True,
}

# Host/endpoint are backend-allowlisted later. Do not accept arbitrary hosts (SSRF).
_FIELDS_FILE: list[dict[str, Any]] = [_DISPLAY_NAME_FIELD, _ACCOUNT_REFERENCE_FIELD]
_FIELDS_SFTP: list[dict[str, Any]] = [
    _DISPLAY_NAME_FIELD,
    _ACCOUNT_REFERENCE_FIELD,
    _SFTP_USERNAME_FIELD,
    _SFTP_PASSWORD_FIELD,
]
_FIELDS_API: list[dict[str, Any]] = [_DISPLAY_NAME_FIELD, _ACCOUNT_REFERENCE_FIELD, _API_KEY_FIELD]
_FIELDS_MANUAL: list[dict[str, Any]] = [_DISPLAY_NAME_FIELD]

_METHOD_LABELS = {
    CONNECTION_METHOD_PDF_UPLOAD: "PDF upload",
    CONNECTION_METHOD_STRUCTURED_FILE_UPLOAD: "Structured file upload",
    CONNECTION_METHOD_FILE_EXPORT: "File export",
    CONNECTION_METHOD_SFTP: "SFTP",
    CONNECTION_METHOD_DATA_SHARING: "Partner data sharing",
    CONNECTION_METHOD_REST_API: "REST API",
    CONNECTION_METHOD_MANUAL_DRIVER: "Manual driver entry",
}
_FIELD_MAP = {
    CONNECTION_METHOD_PDF_UPLOAD: _FIELDS_FILE,
    CONNECTION_METHOD_STRUCTURED_FILE_UPLOAD: _FIELDS_FILE,
    CONNECTION_METHOD_FILE_EXPORT: _FIELDS_FILE,
    CONNECTION_METHOD_SFTP: _FIELDS_SFTP,
    CONNECTION_METHOD_DATA_SHARING: _FIELDS_FILE,
    CONNECTION_METHOD_REST_API: _FIELDS_API,
    CONNECTION_METHOD_MANUAL_DRIVER: _FIELDS_MANUAL,
}


def _method_entry(method: str, *, evidence_status: str) -> dict[str, Any]:
    selectable = evidence_status == EVIDENCE_EVIDENCED
    return {
        "connection_method": method,
        "label": _METHOD_LABELS[method],
        "evidence_status": evidence_status,
        "selectable": selectable,
        "live_adapter_implemented": False,
        "test_connection_capability": False,
        "sync_capability": False,
        "scheduling_capability": False,
        "fields": deepcopy(_FIELD_MAP[method]) if selectable else [],
    }


def _provider(
    *,
    code: str,
    display_name: str,
    evidenced_methods: list[str],
    unverified_methods: list[str],
    parser_profile_code: str | None,
    expected_file_formats: list[str],
    filename_pattern: str | None,
    instructions: str,
) -> dict[str, Any]:
    connection_methods = [_method_entry(m, evidence_status=EVIDENCE_EVIDENCED) for m in evidenced_methods]
    connection_methods.extend(
        _method_entry(m, evidence_status=EVIDENCE_UNVERIFIED) for m in unverified_methods
    )
    return {
        "provider_code": code,
        "display_name": display_name,
        "enabled": True,
        "supported_connection_methods": list(evidenced_methods),
        "unverified_connection_methods": list(unverified_methods),
        "default_connection_method": evidenced_methods[0] if evidenced_methods else None,
        "parser_profile_code": parser_profile_code,
        "expected_file_formats": list(expected_file_formats),
        "filename_pattern": filename_pattern,
        "instructions": instructions,
        "live_adapter_implemented": False,
        "connection_methods": connection_methods,
    }


_CATALOG: Final[tuple[dict[str, Any], ...]] = (
    _provider(
        code="BVD",
        display_name="BVD",
        evidenced_methods=[CONNECTION_METHOD_PDF_UPLOAD, CONNECTION_METHOD_STRUCTURED_FILE_UPLOAD],
        unverified_methods=[],
        parser_profile_code="fuel_card_statement",
        expected_file_formats=["pdf", "dat"],
        filename_pattern=None,
        instructions=(
            "BVD is the first evidence-backed section in the master Fuel provider "
            "profiles JSON (app/contracts/fuel_provider_profiles.json → BVD, "
            "profile_version stamped) for the generic Fuel parser — not a separate BVD parser "
            "engine. Captured evidence: digital statement PDF invoice 972201. Industry "
            "documentation mentions T-Chek-compatible export (e.g. TcheckDATTransplus) but "
            "no sample file is present; structured adapter remains BLOCKED_BY_SOURCE_EVIDENCE "
            "until a real export exists. Direct BVD API/SFTP is unconfirmed and is not "
            "advertised. Live adapters are not implemented."
        ),
    ),
    _provider(
        code="NATIONWIDE",
        display_name="Nationwide",
        evidenced_methods=[CONNECTION_METHOD_PDF_UPLOAD],
        unverified_methods=[],
        parser_profile_code="fuel_card_statement",
        expected_file_formats=["pdf"],
        filename_pattern=None,
        instructions=(
            "Nationwide is the second evidence-backed section in the master Fuel provider "
            "profiles JSON (app/contracts/fuel_provider_profiles.json → NATIONWIDE, "
            "profile_version stamped) for the generic Fuel parser — not a separate "
            "Nationwide parser. PDF-first. PDF text references an attached CSV for further "
            "detail, but no CSV sample is in-repo; structured CSV remains "
            "BLOCKED_BY_SOURCE_EVIDENCE. Automated Nationwide machine feed is not evidenced "
            "and is not advertised. Live adapters are not implemented."
        ),
    ),
    _provider(
        code="PILOT_FLYING_J",
        display_name="Pilot Flying J",
        evidenced_methods=[],
        unverified_methods=[CONNECTION_METHOD_SFTP, CONNECTION_METHOD_STRUCTURED_FILE_UPLOAD],
        parser_profile_code=None,
        expected_file_formats=["csv", "dat"],
        filename_pattern=None,
        instructions=(
            "Pilot Flying J has no captured tenant contract, credentials, or file sample. "
            "SFTP and structured-file intake remain unverified/unsupported and cannot be "
            "configured. Do not invent a public fuel-transaction REST API. Live adapters "
            "are not implemented."
        ),
    ),
    _provider(
        code="LOVES",
        display_name="Love's",
        evidenced_methods=[],
        unverified_methods=[CONNECTION_METHOD_SFTP, CONNECTION_METHOD_STRUCTURED_FILE_UPLOAD],
        parser_profile_code=None,
        expected_file_formats=["csv", "dat"],
        filename_pattern=None,
        instructions=(
            "Love's has no captured tenant contract, credentials, or file sample. Public "
            "Love's APIs are not assumed to be a fleet transaction feed. SFTP and structured "
            "file intake remain unverified/unsupported and cannot be configured. Live "
            "adapters are not implemented."
        ),
    ),
    _provider(
        code="WEX",
        display_name="WEX",
        evidenced_methods=[],
        unverified_methods=[
            CONNECTION_METHOD_REST_API,
            CONNECTION_METHOD_DATA_SHARING,
            CONNECTION_METHOD_FILE_EXPORT,
        ],
        parser_profile_code=None,
        expected_file_formats=["csv"],
        filename_pattern=None,
        instructions=(
            "WEX REST/data-sharing/file-export remain unverified until the exact account "
            "contract is confirmed. Those methods are listed for direction only and cannot "
            "be configured. Live adapters are not implemented."
        ),
    ),
    _provider(
        code="EFS_TCHEK",
        display_name="EFS/T-Chek",
        evidenced_methods=[],
        unverified_methods=[
            CONNECTION_METHOD_REST_API,
            CONNECTION_METHOD_DATA_SHARING,
            CONNECTION_METHOD_STRUCTURED_FILE_UPLOAD,
        ],
        parser_profile_code=None,
        expected_file_formats=["dat", "csv"],
        filename_pattern=None,
        instructions=(
            "EFS/T-Chek REST/data-sharing/structured-file remain unverified until the exact "
            "account contract is confirmed. Those methods are listed for direction only and "
            "cannot be configured. Live adapters are not implemented."
        ),
    ),
    _provider(
        code="COMDATA",
        display_name="Comdata",
        evidenced_methods=[],
        unverified_methods=[CONNECTION_METHOD_REST_API, CONNECTION_METHOD_FILE_EXPORT],
        parser_profile_code=None,
        expected_file_formats=["csv"],
        filename_pattern=None,
        instructions=(
            "Comdata web-service/feed fields are not guessed before onboarding documentation. "
            "REST and file-export remain unverified/unsupported and cannot be configured. "
            "Live adapters are not implemented."
        ),
    ),
)


def list_provider_catalog() -> list[dict[str, Any]]:
    return deepcopy(list(_CATALOG))


def get_provider_catalog_entry(provider_code: str) -> dict[str, Any] | None:
    code = (provider_code or "").strip().upper()
    for entry in _CATALOG:
        if entry["provider_code"] == code:
            return deepcopy(entry)
    return None


def get_connection_method_schema(provider_code: str, connection_method: str) -> dict[str, Any] | None:
    entry = get_provider_catalog_entry(provider_code)
    if entry is None:
        return None
    method = (connection_method or "").strip().upper()
    for item in entry["connection_methods"]:
        if item["connection_method"] == method:
            return deepcopy(item)
    return None


def connection_method_is_selectable(provider_code: str, connection_method: str) -> bool:
    schema = get_connection_method_schema(provider_code, connection_method)
    return bool(schema and schema.get("selectable") and schema.get("evidence_status") == EVIDENCE_EVIDENCED)


def secret_field_keys(provider_code: str, connection_method: str) -> frozenset[str]:
    schema = get_connection_method_schema(provider_code, connection_method)
    if schema is None:
        return frozenset()
    return frozenset(str(f["key"]) for f in schema["fields"] if f.get("secret"))


def non_secret_field_keys(provider_code: str, connection_method: str) -> frozenset[str]:
    schema = get_connection_method_schema(provider_code, connection_method)
    if schema is None:
        return frozenset()
    return frozenset(str(f["key"]) for f in schema["fields"] if not f.get("secret"))
