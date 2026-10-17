#!/usr/bin/env python3
"""Clone tenant_demo onto the isolated Postgres server and test that clone.

The testing workflow is a real PostgreSQL copy of tenant_demo: schema,
relationships, tenant ids, and representative rows. Mocks are only for the
runner's safety checks. Live dump, restore, migration, and pytest run only
when DEMO_CLONE_EXECUTE=1 is set for an approved execution.

tenant_demo is never written. The clone is never registered in the production
platform database.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Protocol

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.core.integration_db_guard import (  # noqa: E402
    ALLOWED_TEST_PLATFORM_CONNECTIONS,
    FORBIDDEN_INTEGRATION_TENANT_DB_NAMES,
    PRODUCTION_PLATFORM_DB_NAMES,
    PRODUCTION_PLATFORM_HOSTS,
)

SOURCE_DATABASE = "tenant_demo"
CLONE_NAME_RE = re.compile(r"^tenant_clone_[0-9]{8}t[0-9]{6}z_[a-z0-9]{6}$")
IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
REFUSED_REVISIONS = frozenset({"", "head", "heads"})
FORBIDDEN_TARGET_NAMES = frozenset(
    FORBIDDEN_INTEGRATION_TENANT_DB_NAMES
    | PRODUCTION_PLATFORM_DB_NAMES
    | {"tenant_pytest", "tenant_ikl", "postgres", "template0", "template1"}
)
ALLOWED_CLONE_HOSTS = frozenset(
    host
    for host, database in ALLOWED_TEST_PLATFORM_CONNECTIONS
    if database == "postgres" and host not in PRODUCTION_PLATFORM_HOSTS
)
SECRET_MARKERS = ("password", "secret", "token", "webhook", "api_key", "access_key", "refresh")
STORAGE_MARKERS = ("storage_key", "storage_ref", "s3_key", "object_key")
PHONE_NAMES = frozenset({"phone", "mobile", "fax"})
DEFAULT_SCHEMA = (
    ("alembic_version", "version_num"),
    ("loads", "id"),
    ("people", "id"),
    ("people", "tenant_id"),
    ("people", "email"),
)
RECOVERY = (
    "Recovery: on truckerp-phase4c-postgres only, confirm datname equals the "
    "remaining name, then DROP DATABASE that name WITH (FORCE). Do not drop tenant_demo."
)
CONTAINER_FOR_HOST = {
    "truckerp-postgres": ("truckerp-postgres", "postgres"),
    "172.29.0.4": ("truckerp-postgres", "postgres"),
    "172.24.0.2": ("truckerp-phase4c-postgres", "phase4c"),
    "truckerp-phase4c-postgres": ("truckerp-phase4c-postgres", "phase4c"),
}
DISABLED_SIDE_EFFECTS = {
    "SMTP_HOST": "",
    "SMTP_PORT": "",
    "SMTP_USERNAME": "",
    "SMTP_PASSWORD": "",
    "SMTP_FROM_ADDRESS": "",
    "SMTP_USE_TLS": "",
    "SMTP_USE_SSL": "",
    "AWS_ACCESS_KEY_ID": "",
    "AWS_SECRET_ACCESS_KEY": "",
    "AWS_SESSION_TOKEN": "",
    "AWS_REGION": "",
    "STRIPE_SECRET_KEY": "",
    "STRIPE_WEBHOOK_SECRET": "",
    "S3_BUCKET": "",
    "S3_PREFIX": "",
    "OPENAI_API_KEY": "",
    "GOOGLE_CLIENT_ID": "",
    "GOOGLE_CLIENT_SECRET": "",
    "GMAIL_OAUTH_CALLBACK_URL": "",
    "GMAIL_PUBSUB_PUSH_AUDIENCE": "",
    "GMAIL_PUBSUB_PUSH_TOKEN": "",
    "GMAIL_PUBSUB_TOPIC_NAME": "",
    "MICROSOFT_CLIENT_ID": "",
    "MICROSOFT_CLIENT_SECRET": "",
    "MICROSOFT_OAUTH_CALLBACK_URL": "",
    "MICROSOFT_WEBHOOK_NOTIFICATION_URL": "",
    "MICROSOFT_WEBHOOK_CLIENT_STATE_SECRET": "",
    "INTEGRATION_SECRET_ENCRYPTION_KEY": "",
    "TWILIO_AUTH_TOKEN": "",
    "SENDGRID_API_KEY": "",
    "DATABASE_URL": "postgresql://test:test@db.example.invalid:5432/test",
    "POSTGRES_ADMIN_URL": "postgresql://test:test@db.example.invalid:5432/test",
}
CREDENTIAL_MARKERS = (
    "SMTP",
    "AWS_",
    "STRIPE",
    "S3_",
    "OPENAI",
    "OAUTH",
    "WEBHOOK",
    "GOOGLE_CLIENT",
    "MICROSOFT_",
    "GMAIL_PUBSUB",
    "TWILIO",
    "SENDGRID",
    "INTEGRATION_SECRET",
)


class CloneError(RuntimeError):
    """The clone runner refused to continue."""


class SqlPort(Protocol):
    def query(self, host: str, database: str, sql: str) -> list[tuple]: ...

    def execute(self, host: str, database: str, sql: str) -> None: ...


class CommandPort(Protocol):
    def run(self, argv: list[str], env: dict[str, str] | None = None) -> int: ...


@dataclass(frozen=True)
class DbTarget:
    host: str
    database: str


@dataclass
class CloneReport:
    clone_name: str
    clone_host: str
    source_revision: str = ""
    clone_revision: str = ""
    applied_revision: str = ""
    sanitize_ok: bool = False
    schema_ok: bool = False
    tests_ran: bool = False
    cleanup: str = "not-attempted"
    dump_cleanup: str = "not-created"
    remaining_database: str = ""
    recovery: str = ""
    error: str = ""

    def text(self) -> str:
        lines = [
            f"clone_name={self.clone_name}",
            f"clone_host={self.clone_host}",
            f"source_revision={self.source_revision}",
            f"clone_revision={self.clone_revision}",
            f"applied_revision={self.applied_revision or '(baseline only)'}",
            f"sanitize_ok={self.sanitize_ok}",
            f"schema_ok={self.schema_ok}",
            "database_mode=postgresql_clone",
            "external_effects=disabled",
            f"platform_mutations=none",
            f"tests_ran={self.tests_ran}",
            f"cleanup={self.cleanup}",
            f"dump_cleanup={self.dump_cleanup}",
        ]
        if self.remaining_database:
            lines.append(f"remaining_database={self.remaining_database}")
            lines.append(self.recovery or RECOVERY)
        if self.error:
            lines.append(f"error={_redact(self.error)}")
        return "\n".join(lines) + "\n"


@dataclass
class _SensitiveColumn:
    table: str
    column: str
    kind: str
    nullable: bool
    data_type: str
    max_length: int
    unique: bool
    foreign_key: bool


@dataclass
class CloneRequest:
    source: DbTarget
    clone_host: str
    clone_name: str
    revision: str | None = None
    schema_contract: tuple[tuple[str, str], ...] = DEFAULT_SCHEMA
    run_tests: bool = False
    test_paths: tuple[str, ...] = ()
    dump_path: str = ""
    commands: list[list[str]] = field(default_factory=list)


def make_clone_name(moment: datetime, suffix: str) -> str:
    if moment.tzinfo is None:
        raise CloneError("Clone timestamp must be timezone-aware.")
    if not re.fullmatch(r"[a-z0-9]{6}", suffix or ""):
        raise CloneError("Clone suffix must be 6 lowercase letters or digits.")
    name = f"tenant_clone_{moment.astimezone(timezone.utc).strftime('%Y%m%d')}t{moment.astimezone(timezone.utc).strftime('%H%M%S')}z_{suffix}"
    assert_clone_name(name)
    return name


def assert_clone_name(name: str) -> None:
    if name in FORBIDDEN_TARGET_NAMES or not CLONE_NAME_RE.fullmatch(name or ""):
        raise CloneError(f"Refusing database name {name!r}.")


def assert_clone_host(host: str) -> None:
    lowered = (host or "").strip().lower()
    if lowered in PRODUCTION_PLATFORM_HOSTS or lowered not in ALLOWED_CLONE_HOSTS:
        raise CloneError(f"Refusing clone host {host!r}.")


def assert_revision(revision: str | None) -> str | None:
    if revision is None:
        return None
    cleaned = revision.strip()
    if cleaned.lower() in REFUSED_REVISIONS or " " in cleaned or ";" in cleaned:
        raise CloneError("Refusing Alembic target. Pass one explicit revision, never head.")
    return cleaned


def _quote_ident(name: str) -> str:
    if not IDENT_RE.fullmatch(name or ""):
        raise CloneError(f"Refusing SQL identifier {name!r}.")
    return '"' + name + '"'


def _redact(text: str) -> str:
    cleaned = re.sub(r"://[^/\s:@]+:[^/\s@]+@", "://***@", text)
    cleaned = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", cleaned)
    cleaned = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[redacted-phone]", cleaned)
    return cleaned


def _safe_process_detail(text: str) -> str:
    compact = _redact(text).replace("\n", " ")
    return compact[:180]


def classify_column(table: str, column: str) -> str | None:
    if not IDENT_RE.fullmatch(table) or not IDENT_RE.fullmatch(column):
        raise CloneError(f"Refusing sensitive column {table}.{column}.")
    lowered = column.lower()
    if any(marker in lowered for marker in SECRET_MARKERS):
        return "secret"
    if any(marker in lowered for marker in STORAGE_MARKERS):
        return "storage"
    if lowered == "email" or lowered.endswith("_email"):
        return "email"
    if lowered in PHONE_NAMES or lowered.endswith("_phone"):
        return "phone"
    return None


def _read_revision(sql: SqlPort, target: DbTarget) -> str:
    rows = sql.query(target.host, target.database, "SELECT version_num FROM alembic_version")
    if len(rows) != 1 or not rows[0] or not str(rows[0][0]).strip():
        raise CloneError(f"Expected one Alembic revision on {target.database}.")
    return str(rows[0][0]).strip()


def _require_module_contract(contract: tuple[tuple[str, str], ...]) -> None:
    if not contract:
        raise CloneError("Schema contract is empty.")
    module_columns = [item for item in contract if item not in DEFAULT_SCHEMA]
    if not module_columns:
        raise CloneError("A module-specific schema contract is required.")
    for table, column in module_columns:
        _quote_ident(table)
        _quote_ident(column)


def _column_profile(row: tuple) -> _SensitiveColumn | None:
    if len(row) != 7:
        raise CloneError("Column profile is incomplete.")
    table, column = str(row[0]), str(row[1])
    kind = classify_column(table, column)
    if kind is None:
        return None
    nullable = str(row[2]).upper() == "YES"
    data_type = str(row[3]).lower()
    max_length = int(row[4] or 0)
    unique = str(row[5]) == "1"
    foreign_key = str(row[6]) == "1"
    profile = _SensitiveColumn(table, column, kind, nullable, data_type, max_length, unique, foreign_key)
    if profile.foreign_key:
        raise CloneError(f"Refusing to rewrite foreign key {table}.{column}.")
    return profile


def _discover(sql: SqlPort, clone: DbTarget) -> list[_SensitiveColumn]:
    rows = sql.query(
        clone.host,
        clone.database,
        "SELECT c.table_name, c.column_name, c.is_nullable, c.data_type, "
        "COALESCE(c.character_maximum_length, 0), "
        "CASE WHEN unique_col.column_name IS NULL THEN 0 ELSE 1 END, "
        "CASE WHEN fk_col.column_name IS NULL THEN 0 ELSE 1 END "
        "FROM information_schema.columns c "
        "LEFT JOIN ("
        "SELECT kcu.table_name, kcu.column_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
        "WHERE tc.table_schema = 'public' AND tc.constraint_type = 'UNIQUE'"
        ") unique_col ON unique_col.table_name = c.table_name AND unique_col.column_name = c.column_name "
        "LEFT JOIN ("
        "SELECT kcu.table_name, kcu.column_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
        "WHERE tc.table_schema = 'public' AND tc.constraint_type = 'FOREIGN KEY'"
        ") fk_col ON fk_col.table_name = c.table_name AND fk_col.column_name = c.column_name "
        "WHERE c.table_schema = 'public'",
    )
    found: list[_SensitiveColumn] = []
    seen = set()
    for row in rows:
        profile = _column_profile(row)
        if profile is None:
            continue
        key = (profile.table, profile.column)
        if key in seen:
            continue
        seen.add(key)
        found.append(profile)
    if ("people", "email") not in {(item.table, item.column) for item in found}:
        raise CloneError("Sanitization incomplete: people.email was not found.")
    return found


def _replacement_expr(item: _SensitiveColumn, table: str) -> str:
    digest = f"substr(md5({table}.ctid::text), 1, 16)"
    if item.data_type == "bytea":
        return f"decode(md5({table}.ctid::text), 'hex')"
    if item.data_type in {"character varying", "text"}:
        if item.kind == "email":
            literal = f"'redacted-' || {digest} || '@example.invalid'"
            needed = 9 + 16 + 16
        elif item.kind == "phone":
            literal = f"'200555' || substr(md5({table}.ctid::text), 1, 7)"
            needed = 13
        elif item.kind == "storage":
            literal = f"'redacted-object-' || {digest}"
            needed = 16 + 16
        else:
            literal = f"'redacted-secret-' || {digest}"
            needed = 16 + 16
        if item.max_length and item.max_length < needed:
            raise CloneError(f"Cannot fit a collision-safe value into {item.table}.{item.column}.")
        return literal
    if item.nullable and not item.unique:
        return "NULL"
    raise CloneError(
        f"Cannot sanitize {item.table}.{item.column}: {item.data_type} is required or unique."
    )


def _sanitize(sql: SqlPort, clone: DbTarget, columns: Iterable[_SensitiveColumn]) -> None:
    for item in columns:
        table = _quote_ident(item.table)
        column = _quote_ident(item.column)
        expr = _replacement_expr(item, table)
        if expr == "NULL" and not item.nullable:
            raise CloneError(f"Refusing to null required column {item.table}.{item.column}.")
        sql.execute(
            clone.host,
            clone.database,
            f"UPDATE {table} SET {column} = {expr} WHERE {column} IS NOT NULL",
        )


def _verify_sanitized(sql: SqlPort, clone: DbTarget, columns: Iterable[_SensitiveColumn]) -> None:
    for item in columns:
        table = _quote_ident(item.table)
        column = _quote_ident(item.column)
        if item.data_type in {"character varying", "text"} and item.kind == "email":
            predicate = f"{column} IS NOT NULL AND {column} !~ '^redacted-[0-9a-f]{{16}}@example.invalid$'"
        elif item.data_type in {"character varying", "text"} and item.kind == "phone":
            predicate = f"{column} IS NOT NULL AND {column} !~ '^200555[0-9a-f]{{7}}$'"
        elif item.data_type in {"character varying", "text"} and item.kind == "storage":
            predicate = f"{column} IS NOT NULL AND {column} !~ '^redacted-object-[0-9a-f]{{16}}$'"
        elif item.data_type in {"character varying", "text"}:
            predicate = f"{column} IS NOT NULL AND {column} !~ '^redacted-secret-[0-9a-f]{{16}}$'"
        elif item.data_type == "bytea":
            predicate = f"{column} IS NOT NULL AND octet_length({column}) <> 16"
        else:
            predicate = f"{column} IS NOT NULL"
        rows = sql.query(clone.host, clone.database, f"SELECT count(*) FROM {table} WHERE {predicate}")
        if not rows or int(rows[0][0]) != 0:
            raise CloneError(f"Sanitization incomplete on {item.table}.{item.column}.")
        if not item.nullable:
            nulls = sql.query(
                clone.host, clone.database, f"SELECT count(*) FROM {table} WHERE {column} IS NULL"
            )
            if not nulls or int(nulls[0][0]) != 0:
                raise CloneError(f"Required column {item.table}.{item.column} was nulled.")
        if item.unique:
            dupes = sql.query(
                clone.host,
                clone.database,
                f"SELECT count(*) FROM (SELECT {column} FROM {table} WHERE {column} IS NOT NULL "
                f"GROUP BY {column} HAVING count(*) > 1) duplicates",
            )
            if not dupes or int(dupes[0][0]) != 0:
                raise CloneError(f"Replacement values collided on {item.table}.{item.column}.")
    invalid = sql.query(
        clone.host,
        clone.database,
        "SELECT count(*) FROM pg_constraint WHERE contype = 'f' AND NOT convalidated",
    )
    if not invalid or int(invalid[0][0]) != 0:
        raise CloneError("Referential integrity check failed on the clone.")


def _require_schema(sql: SqlPort, clone: DbTarget, contract: tuple[tuple[str, str], ...]) -> None:
    if not contract:
        raise CloneError("Schema contract is empty.")
    for table, column in contract:
        table_sql = _quote_ident(table)
        column_sql = _quote_ident(column)
        rows = sql.query(
            clone.host,
            clone.database,
            "SELECT count(*) FROM information_schema.columns "
            f"WHERE table_schema = 'public' AND table_name = '{table_sql[1:-1]}' "
            f"AND column_name = '{column_sql[1:-1]}'",
        )
        if not rows or int(rows[0][0]) != 1:
            raise CloneError(f"Missing required column {table}.{column}.")


def _dump_env() -> dict[str, str]:
    return {"PGOPTIONS": "-c default_transaction_read_only=on"}


def _secure_dump(path: str) -> None:
    directory = os.path.dirname(path) or "."
    resolved = os.path.abspath(directory)
    if resolved != "/tmp" and not resolved.startswith("/tmp/"):
        raise CloneError("Dump path must be under /tmp.")
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise CloneError("Refusing to overwrite an existing dump file.") from exc
    os.close(descriptor)
    if os.stat(path).st_mode & 0o777 != 0o600:
        raise CloneError("Dump file permissions are not restrictive.")


def _clone_present(sql: SqlPort, host: str, name: str) -> bool:
    assert_clone_name(name)
    rows = sql.query(
        host,
        "postgres",
        f"SELECT count(*) FROM pg_database WHERE datname = '{name}'",
    )
    return bool(rows) and int(rows[0][0]) == 1


def _clone_owned(sql: SqlPort, host: str, name: str, nonce: str) -> bool:
    assert_clone_name(name)
    if not re.fullmatch(r"[0-9a-f]{16}", nonce or ""):
        raise CloneError("Clone marker is invalid.")
    rows = sql.query(
        host,
        "postgres",
        "SELECT count(*) FROM pg_database d "
        "JOIN pg_shdescription s ON s.objoid = d.oid "
        "AND s.classoid = 'pg_database'::regclass "
        f"WHERE d.datname = '{name}' AND s.description = 'truckerp-demo-clone:{nonce}'",
    )
    return bool(rows) and int(rows[0][0]) == 1


def _assert_current_database(sql: SqlPort, clone: DbTarget) -> None:
    rows = sql.query(clone.host, clone.database, "SELECT current_database()")
    if not rows or str(rows[0][0]) != clone.database or clone.database == SOURCE_DATABASE:
        raise CloneError("Connected database does not match the clone name.")


def assert_source(source: DbTarget) -> None:
    if source.database != SOURCE_DATABASE:
        raise CloneError("Source database must be tenant_demo.")
    if source.host.strip().lower() not in PRODUCTION_PLATFORM_HOSTS:
        raise CloneError("Source host must be the production Postgres service that holds tenant_demo.")


def run_clone(
    sql: SqlPort,
    commands: CommandPort,
    request: CloneRequest,
) -> CloneReport:
    assert_clone_host(request.clone_host)
    assert_clone_name(request.clone_name)
    assert_source(request.source)
    if request.source.host.strip().lower() == request.clone_host.strip().lower():
        raise CloneError("Source and clone hosts must be different.")
    revision = assert_revision(request.revision)
    if request.run_tests and not request.test_paths:
        raise CloneError("Clone tests require explicit pytest paths.")
    _require_module_contract(request.schema_contract)
    report = CloneReport(clone_name=request.clone_name, clone_host=request.clone_host)
    created = False
    dump_path = ""
    dump_created = False
    clone_nonce = secrets.token_hex(8)
    try:
        report.source_revision = _read_revision(sql, request.source)
        dump_path = request.dump_path or os.path.join("/tmp", f"{request.clone_name}.dump")
        _secure_dump(dump_path)
        dump_created = True
        dump_code = commands.run(
            [
                "pg_dump",
                "-h",
                request.source.host,
                "-d",
                SOURCE_DATABASE,
                "-Fc",
                "--no-owner",
                "--no-acl",
                "-f",
                dump_path,
            ],
            env=_dump_env(),
        )
        if dump_code != 0:
            raise CloneError("pg_dump of tenant_demo failed.")
        if _clone_present(sql, request.clone_host, request.clone_name):
            raise CloneError("Refusing to touch a pre-existing database.")
        try:
            sql.execute(
                request.clone_host,
                "postgres",
                f'CREATE DATABASE "{request.clone_name}"',
            )
        except Exception as exc:
            present = False
            try:
                present = _clone_present(sql, request.clone_host, request.clone_name)
            except Exception:
                present = False
            if present:
                report.cleanup = "not-attempted"
                report.remaining_database = request.clone_name
                report.recovery = (
                    "CREATE DATABASE result was ambiguous. Do not drop this database. "
                    + RECOVERY
                )
                report.error = "CREATE DATABASE result was ambiguous."
                return report
            if isinstance(exc, CloneError):
                raise
            raise CloneError("CREATE DATABASE failed.") from exc
        if not _clone_present(sql, request.clone_host, request.clone_name):
            raise CloneError("CREATE DATABASE did not create the clone.")
        sql.execute(
            request.clone_host,
            "postgres",
            f'COMMENT ON DATABASE "{request.clone_name}" IS '
            f"'truckerp-demo-clone:{clone_nonce}'",
        )
        created = True
        clone = DbTarget(request.clone_host, request.clone_name)
        restore_code = commands.run(
            [
                "pg_restore",
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
                "-h",
                request.clone_host,
                "-d",
                request.clone_name,
                dump_path,
            ]
        )
        if restore_code != 0:
            raise CloneError("pg_restore into the clone failed.")
        report.clone_revision = _read_revision(sql, clone)
        source_after = _read_revision(sql, request.source)
        if source_after != report.source_revision:
            raise CloneError("tenant_demo revision changed during the clone.")
        if report.clone_revision != report.source_revision:
            raise CloneError("Clone did not preserve the tenant_demo Alembic revision.")
        _assert_current_database(sql, clone)
        columns = _discover(sql, clone)
        _sanitize(sql, clone, columns)
        _verify_sanitized(sql, clone, columns)
        report.sanitize_ok = True
        if revision is not None:
            upgrade_code = commands.run(
                ["alembic", "-c", "alembic_tenant.ini", "upgrade", revision],
                env={
                    "ALEMBIC_TENANT_DATABASE_URL": (
                        f"postgresql://{request.clone_host}/{request.clone_name}"
                    )
                },
            )
            if upgrade_code != 0:
                raise CloneError("Alembic upgrade of the clone failed.")
            report.applied_revision = revision
            report.clone_revision = _read_revision(sql, clone)
            if report.clone_revision != revision:
                raise CloneError("Clone revision does not match the requested target.")
            if _read_revision(sql, request.source) != report.source_revision:
                raise CloneError("tenant_demo revision changed during clone migration.")
        _assert_current_database(sql, clone)
        _require_schema(sql, clone, request.schema_contract)
        report.schema_ok = True
        if request.run_tests:
            if not report.sanitize_ok or not report.schema_ok:
                raise CloneError("Refusing tests before sanitization and schema checks.")
            test_code = commands.run(
                ["pytest", *request.test_paths],
                env={
                    "TENANT_DATABASE_URL": (
                        f"postgresql://{request.clone_host}/{request.clone_name}"
                    ),
                    "TRUCKERP_INTEGRATION_ALLOWED_DB_NAMES": request.clone_name,
                    "STORAGE_PROVIDER": "local",
                    "DEMO_CLONE_EXTERNAL_EFFECTS": "disabled",
                },
            )
            report.tests_ran = True
            if test_code != 0:
                raise CloneError("Clone tests failed.")
        return report
    except CloneError as exc:
        report.error = str(exc)
        return report
    finally:
        if dump_created:
            try:
                os.remove(dump_path)
                report.dump_cleanup = "removed"
            except OSError:
                report.dump_cleanup = "failed"
                report.error = (report.error + " " if report.error else "") + "Dump cleanup failed."
        if created:
            try:
                assert_clone_host(request.clone_host)
                assert_clone_name(request.clone_name)
                if not _clone_owned(sql, request.clone_host, request.clone_name, clone_nonce):
                    raise CloneError("Refusing to drop a database this run did not mark.")
                sql.execute(
                    request.clone_host,
                    "postgres",
                    f'DROP DATABASE "{request.clone_name}" WITH (FORCE)',
                )
                report.cleanup = "dropped"
            except Exception as exc:  # noqa: BLE001 — cleanup must be reported, not hidden
                report.cleanup = "failed"
                report.remaining_database = request.clone_name
                report.recovery = RECOVERY
                report.error = (report.error + " " if report.error else "") + (
                    f"Cleanup failed: {_redact(str(exc))}"
                )


def assert_live_sql(host: str, database: str, sql: str, *, write: bool) -> None:
    """Reject any live statement that could change tenant_demo or another database."""
    statement = " ".join(sql.split())
    upper = statement.upper()
    lowered = host.strip().lower()
    protected = lowered in PRODUCTION_PLATFORM_HOSTS or database == SOURCE_DATABASE
    if protected:
        if write or upper != "SELECT VERSION_NUM FROM ALEMBIC_VERSION":
            raise CloneError("Refusing SQL against tenant_demo.")
        return
    assert_clone_host(lowered)
    if SOURCE_DATABASE in statement or "trucking_erp" in statement:
        raise CloneError("Refusing a statement that names a protected database.")
    if database == "postgres":
        if upper.startswith("SELECT COUNT(*) FROM PG_DATABASE WHERE DATNAME = 'TENANT_CLONE_"):
            return
        if (
            upper.startswith("SELECT COUNT(*) FROM PG_DATABASE D JOIN PG_SHDESCRIPTION")
            and "TRUCKERP-DEMO-CLONE:" in upper
        ):
            return
        if upper.startswith('COMMENT ON DATABASE "TENANT_CLONE_') and "TRUCKERP-DEMO-CLONE:" in upper:
            return
        allowed = upper.startswith('CREATE DATABASE "TENANT_CLONE_') or upper.startswith(
            'DROP DATABASE "TENANT_CLONE_'
        )
        if not allowed or ("WITH (FORCE)" not in upper and upper.startswith("DROP")):
            raise CloneError("Refusing SQL against the isolated maintenance database.")
        return
    assert_clone_name(database)
    if write and not upper.startswith("UPDATE "):
        raise CloneError("Refusing a non-sanitizing write on the clone.")
    if not write and not upper.startswith("SELECT "):
        raise CloneError("Refusing a non-select on the clone.")


def _container(host: str) -> tuple[str, str]:
    found = CONTAINER_FOR_HOST.get(host.strip().lower())
    if found is None:
        raise CloneError(f"No container is mapped for host {host!r}.")
    return found


def docker_psql_argv(host: str, database: str, sql: str) -> list[str]:
    container, user = _container(host)
    argv = ["docker", "exec", "-i"]
    if host.strip().lower() in PRODUCTION_PLATFORM_HOSTS:
        argv.extend(["-e", "PGOPTIONS=-c default_transaction_read_only=on"])
    argv.extend(
        [
            container,
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            "-F",
            "\t",
            "-c",
            sql,
        ]
    )
    return argv


def translate_dump(argv: list[str], env: dict[str, str]) -> tuple[list[str], str]:
    if env.get("PGOPTIONS") != "-c default_transaction_read_only=on":
        raise CloneError("pg_dump of tenant_demo must be read-only.")
    if argv[0] != "pg_dump" or "-d" not in argv or "-h" not in argv or "-f" not in argv:
        raise CloneError("Refusing unexpected pg_dump arguments.")
    host = argv[argv.index("-h") + 1]
    database = argv[argv.index("-d") + 1]
    dest = argv[argv.index("-f") + 1]
    if database != SOURCE_DATABASE or host.strip().lower() not in PRODUCTION_PLATFORM_HOSTS:
        raise CloneError("pg_dump source must be tenant_demo on production Postgres.")
    container, user = _container(host)
    docker_argv = [
        "docker", "exec", "-e", "PGOPTIONS=-c default_transaction_read_only=on",
        container, "pg_dump", "-U", user, "-d", SOURCE_DATABASE,
        "-Fc", "--no-owner", "--no-acl",
    ]
    return docker_argv, dest


def translate_restore(argv: list[str]) -> tuple[list[str], str]:
    if argv[0] != "pg_restore" or "-d" not in argv or "-h" not in argv:
        raise CloneError("Refusing unexpected pg_restore arguments.")
    host = argv[argv.index("-h") + 1]
    database = argv[argv.index("-d") + 1]
    dump_path = argv[-1]
    assert_clone_host(host)
    assert_clone_name(database)
    container, user = _container(host)
    docker_argv = [
        "docker", "exec", "-i", container, "pg_restore", "-U", user,
        "--no-owner", "--no-acl", "--exit-on-error", "-d", database,
    ]
    return docker_argv, dump_path


def isolated_child_env(updates: dict[str, str]) -> dict[str, str]:
    """Build a child environment that cannot inherit production credentials."""
    child = {
        "PATH": os.environ.get("PATH", "/usr/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "PYTHONPATH": _REPO_ROOT,
        "ENVIRONMENT": "test",
        "JWT_SECRET": "phase4c-test-secret",
        "ALLOW_TENANT_RESOLUTION_SHORTCUTS": "true",
        "STORAGE_PROVIDER": "local",
        "DEMO_CLONE_EXTERNAL_EFFECTS": "disabled",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "ALL_PROXY": "",
    }
    child.update(DISABLED_SIDE_EFFECTS)
    for key, value in updates.items():
        if key in DISABLED_SIDE_EFFECTS:
            raise CloneError("Refusing to pass a live credential into the clone child.")
        child[key] = value
    for key, value in child.items():
        upper = key.upper()
        if any(marker in upper for marker in CREDENTIAL_MARKERS) and value not in ("",):
            raise CloneError(f"Child environment still has {key}.")
        if key in {"DATABASE_URL", "POSTGRES_ADMIN_URL", "TENANT_DATABASE_URL", "ALEMBIC_TENANT_DATABASE_URL"}:
            if any(token in value for token in ("truckerp-postgres", "trucking_erp", "172.29.0.4", "tenant_demo")):
                raise CloneError("Refusing a production platform URL in the clone child process.")
    for url_key in ("TENANT_DATABASE_URL", "ALEMBIC_TENANT_DATABASE_URL"):
        if child.get(url_key):
            assert_isolated_target(child[url_key])
    return child


def assert_isolated_target(url: str) -> tuple[str, str]:
    host, database = _host_and_database(url)
    assert_clone_host(host)
    assert_clone_name(database)
    if any(token in url for token in ("tenant_demo", "trucking_erp", "truckerp-postgres", "172.29.0.4")):
        raise CloneError("Refusing a production connection target.")
    return host, database


def clone_database_url(host: str, database: str, *, async_driver: bool) -> str:
    assert_clone_host(host)
    assert_clone_name(database)
    password = os.environ.get("DEMO_CLONE_DB_PASSWORD", "")
    if not password:
        raise CloneError("DEMO_CLONE_DB_PASSWORD is required for the isolated clone connection.")
    scheme = "postgresql+asyncpg" if async_driver else "postgresql"
    return f"{scheme}://phase4c:{password}@{host}:5432/{database}"


class _Completed:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


Spawn = Callable[..., _Completed]


def _parse_psql(text: str) -> list[tuple]:
    rows = []
    for line in text.splitlines():
        if line.strip():
            rows.append(tuple(line.split("\t")))
    return rows


class LiveSql:
    """SQL through docker exec. Production accepts only the revision select."""

    def __init__(self, spawn: Spawn | None = None) -> None:
        self.spawn = spawn or subprocess.run

    def query(self, host: str, database: str, sql: str) -> list[tuple]:
        assert_live_sql(host, database, sql, write=False)
        completed = self.spawn(
            docker_psql_argv(host, database, sql),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            raise CloneError(f"psql query failed: {_redact(completed.stderr.decode(errors='replace'))}")
        return _parse_psql(completed.stdout.decode(errors="replace"))

    def execute(self, host: str, database: str, sql: str) -> None:
        assert_live_sql(host, database, sql, write=True)
        completed = self.spawn(
            docker_psql_argv(host, database, sql),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            raise CloneError(f"psql execute failed: {_redact(completed.stderr.decode(errors='replace'))}")


class LiveCommands:
    """Translate logical dump, restore, Alembic, and pytest calls to real processes."""

    def __init__(self, spawn: Spawn | None = None) -> None:
        self.spawn = spawn or subprocess.run

    def run(self, argv: list[str], env: dict[str, str] | None = None) -> int:
        if not argv:
            raise CloneError("Refusing an empty command.")
        if argv[0] == "pg_dump":
            docker_argv, dest = translate_dump(argv, env or {})
            with open(dest, "wb") as handle:
                completed = self.spawn(
                    docker_argv, stdout=handle, stderr=subprocess.PIPE, check=False
                )
            return completed.returncode
        if argv[0] == "pg_restore":
            docker_argv, dump_path = translate_restore(argv)
            with open(dump_path, "rb") as handle:
                completed = self.spawn(
                    docker_argv, stdin=handle, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, check=False,
                )
            return completed.returncode
        if argv[0] == "alembic":
            if "head" in argv or "heads" in argv:
                raise CloneError("Refusing Alembic head.")
            logical_url = (env or {}).get("ALEMBIC_TENANT_DATABASE_URL", "")
            host, database = _host_and_database(logical_url)
            child = isolated_child_env(
                {
                    "ALEMBIC_TENANT_DATABASE_URL": clone_database_url(
                        host, database, async_driver=True
                    )
                }
            )
            assert_isolated_target(child["ALEMBIC_TENANT_DATABASE_URL"])
            completed = self.spawn(
                [sys.executable, "-m", *argv],
                cwd=_REPO_ROOT,
                env=child,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            return completed.returncode
        if argv[0] == "pytest":
            logical_url = (env or {}).get("TENANT_DATABASE_URL", "")
            host, database = _host_and_database(logical_url)
            child = isolated_child_env(
                {
                    "TENANT_DATABASE_URL": clone_database_url(host, database, async_driver=False),
                    "TRUCKERP_INTEGRATION_ALLOWED_DB_NAMES": (env or {}).get(
                        "TRUCKERP_INTEGRATION_ALLOWED_DB_NAMES", database
                    ),
                }
            )
            assert_isolated_target(child["TENANT_DATABASE_URL"])
            completed = self.spawn(
                [sys.executable, "-m", *argv],
                cwd=_REPO_ROOT,
                env=child,
                check=False,
            )
            return completed.returncode
        raise CloneError(f"Refusing unexpected command {argv[0]!r}.")


def _host_and_database(url: str) -> tuple[str, str]:
    match = re.fullmatch(r"postgresql(?:\+asyncpg)?://([^/]+)/([a-z0-9_]+)", url or "")
    if match is None:
        raise CloneError("Clone URL is missing a host or database name.")
    host = match.group(1).split("@")[-1].split(":")[0]
    return host, match.group(2)


def run_approved_clone(request: CloneRequest) -> CloneReport:
    if os.environ.get("DEMO_CLONE_EXECUTE") != "1":
        raise CloneError("Live clone execution is not approved.")
    return run_clone(LiveSql(), LiveCommands(), request)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clone tenant_demo onto isolated Postgres.")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--source-host", default="truckerp-postgres")
    parser.add_argument("--clone-host", default="172.24.0.2")
    parser.add_argument("--name", default="")
    parser.add_argument("--revision", default="")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--test", action="append", default=[])
    parser.add_argument("--schema", action="append", default=[])
    return parser.parse_args(argv)


def _request_from_args(args: argparse.Namespace) -> CloneRequest:
    if bool(args.revision) == bool(args.baseline_only):
        raise CloneError("Pass exactly one of --revision or --baseline-only.")
    if not args.test:
        raise CloneError("Pass at least one --test path. The clone runs those tests against real rows.")
    if not args.schema:
        raise CloneError("A module-specific schema contract is required. Pass --schema table.column.")
    extra: list[tuple[str, str]] = []
    for item in args.schema:
        if item.count(".") != 1:
            raise CloneError(f"Schema contract entry must be table.column, got {item!r}.")
        table, column = item.split(".", 1)
        extra.append((table, column))
    name = args.name or make_clone_name(datetime.now(timezone.utc), secrets.token_hex(3))
    return CloneRequest(
        source=DbTarget(args.source_host, SOURCE_DATABASE),
        clone_host=args.clone_host,
        clone_name=name,
        revision=None if args.baseline_only else args.revision,
        schema_contract=DEFAULT_SCHEMA + tuple(extra),
        run_tests=True,
        test_paths=tuple(args.test),
    )


def _plan_text(request: CloneRequest) -> str:
    revision = request.revision or "(baseline only)"
    tests = ",".join(request.test_paths)
    return (
        "plan=postgresql_clone\n"
        f"source_database={SOURCE_DATABASE}\n"
        f"source_host={request.source.host}\n"
        f"clone_host={request.clone_host}\n"
        f"clone_name={request.clone_name}\n"
        f"revision={revision}\n"
        f"tests={tests}\n"
        f"schema={','.join(table + '.' + column for table, column in request.schema_contract)}\n"
        "platform_mutations=none\n"
        "live_execution=not_started\n"
    )


def main(
    argv: list[str] | None = None,
    live_runner: Callable[[CloneRequest], CloneReport] | None = None,
) -> int:
    args = _parse_args(list(argv or []))
    try:
        request = _request_from_args(args)
    except CloneError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.plan_only or os.environ.get("DEMO_CLONE_EXECUTE") != "1":
        if not args.plan_only:
            print(
                "Refusing to create a clone. Set DEMO_CLONE_EXECUTE=1 only after a separate execution approval.",
                file=sys.stderr,
            )
            return 2
        sys.stdout.write(_plan_text(request))
        return 0
    report = (live_runner or run_approved_clone)(request)
    sys.stdout.write(report.text())
    if report.error or report.cleanup != "dropped":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
