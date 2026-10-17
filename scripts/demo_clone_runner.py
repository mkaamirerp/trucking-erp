#!/usr/bin/env python3
"""Create a disposable clone of tenant_demo on the isolated Postgres server.

tenant_demo is read-only. The clone is never registered in the production
platform database. This module does not open a connection unless a caller
invokes main() with DEMO_CLONE_EXECUTE=1.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Protocol

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
            f"external_effects=disabled",
            f"platform_mutations=none",
            f"tests_ran={self.tests_ran}",
            f"cleanup={self.cleanup}",
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


@dataclass
class CloneRequest:
    source: DbTarget
    clone_host: str
    clone_name: str
    revision: str | None = None
    schema_contract: tuple[tuple[str, str], ...] = DEFAULT_SCHEMA
    run_tests: bool = False
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
    return re.sub(r"://[^/\s:@]+:[^/\s@]+@", "://***@", text)


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


def _discover(sql: SqlPort, clone: DbTarget) -> list[_SensitiveColumn]:
    rows = sql.query(
        clone.host,
        clone.database,
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public'",
    )
    found: list[_SensitiveColumn] = []
    seen = set()
    for row in rows:
        table, column = str(row[0]), str(row[1])
        kind = classify_column(table, column)
        if kind is None:
            continue
        key = (table, column)
        if key in seen:
            continue
        seen.add(key)
        found.append(_SensitiveColumn(table, column, kind))
    if ("people", "email") not in {(item.table, item.column) for item in found}:
        raise CloneError("Sanitization incomplete: people.email was not found.")
    return found


def _sanitize(sql: SqlPort, clone: DbTarget, columns: Iterable[_SensitiveColumn]) -> None:
    for item in columns:
        table = _quote_ident(item.table)
        column = _quote_ident(item.column)
        if item.kind == "email":
            sql.execute(
                clone.host,
                clone.database,
                f"UPDATE {table} SET {column} = "
                f"'redacted-' || substr(md5({table}.ctid::text), 1, 16) || '@example.invalid' "
                f"WHERE {column} IS NOT NULL AND {column} NOT LIKE '%@example.invalid'",
            )
        else:
            sql.execute(
                clone.host,
                clone.database,
                f"UPDATE {table} SET {column} = NULL WHERE {column} IS NOT NULL",
            )


def _verify_sanitized(sql: SqlPort, clone: DbTarget, columns: Iterable[_SensitiveColumn]) -> None:
    for item in columns:
        table = _quote_ident(item.table)
        column = _quote_ident(item.column)
        if item.kind == "email":
            sql_text = (
                f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL "
                f"AND {column} NOT LIKE '%@example.invalid'"
            )
        else:
            sql_text = f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL"
        rows = sql.query(clone.host, clone.database, sql_text)
        if not rows or int(rows[0][0]) != 0:
            raise CloneError(f"Sanitization incomplete on {item.table}.{item.column}.")


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
    report = CloneReport(clone_name=request.clone_name, clone_host=request.clone_host)
    created = False
    try:
        report.source_revision = _read_revision(sql, request.source)
        dump_path = request.dump_path or os.path.join(
            "/tmp", f"{request.clone_name}.dump"
        )
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
        sql.execute(
            request.clone_host,
            "postgres",
            f'CREATE DATABASE "{request.clone_name}"',
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
        _require_schema(sql, clone, request.schema_contract)
        report.schema_ok = True
        if request.run_tests:
            if not report.sanitize_ok or not report.schema_ok:
                raise CloneError("Refusing tests before sanitization and schema checks.")
            test_code = commands.run(
                ["pytest"],
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
        if request.dump_path == "" and report.clone_name:
            try:
                os.remove(os.path.join("/tmp", f"{request.clone_name}.dump"))
            except OSError:
                pass
        if created:
            try:
                assert_clone_host(request.clone_host)
                assert_clone_name(request.clone_name)
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


def main(argv: list[str] | None = None) -> int:
    """Refuse a live clone until a separate execution approval.

    DEMO_CLONE_EXECUTE=1 is recorded and still does not open a database.
    The first controlled run has to be started deliberately after review.
    """
    del argv
    if os.environ.get("DEMO_CLONE_EXECUTE") != "1":
        print(
            "Refusing to create a clone. Set DEMO_CLONE_EXECUTE=1 only after a separate execution approval.",
            file=sys.stderr,
        )
        return 2
    print(
        "Live clone execution is not enabled in this process. run_clone() is covered by mocks until the approved run.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
