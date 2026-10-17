"""Mocked tests for the disposable tenant_demo clone runner. No database is created."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "demo_clone_runner",
    Path(__file__).resolve().parents[1] / "scripts" / "demo_clone_runner.py",
)
runner = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["demo_clone_runner"] = runner
_SPEC.loader.exec_module(runner)

SOURCE_DATABASE = runner.SOURCE_DATABASE
CloneError = runner.CloneError
CloneRequest = runner.CloneRequest
DbTarget = runner.DbTarget
_redact = runner._redact
assert_revision = runner.assert_revision
classify_column = runner.classify_column
main = runner.main
make_clone_name = runner.make_clone_name
run_clone = runner.run_clone

SOURCE = DbTarget("truckerp-postgres", SOURCE_DATABASE)
HOST = "172.24.0.2"
WHEN = datetime(2026, 10, 17, 15, 4, 5, tzinfo=timezone.utc)
NAME = make_clone_name(WHEN, "ab12cd")
COLUMNS = (
    ("people", "email"),
    ("people", "phone"),
    ("load_files", "storage_key"),
    ("mail_accounts", "webhook_url"),
    ("loads", "id"),
)


class FakeSql:
    def __init__(self, revisions: list[str], *, drop_error: str = "", missing_schema: str = ""):
        self.revisions = list(revisions)
        self.drop_error = drop_error
        self.missing_schema = missing_schema
        self.calls: list[tuple] = []

    def query(self, host: str, database: str, sql: str) -> list[tuple]:
        self.calls.append(("query", host, database, sql))
        if sql.startswith("SELECT version_num"):
            return [(self.revisions.pop(0),)]
        if "table_name, column_name" in sql:
            return list(COLUMNS)
        if "information_schema.columns" in sql and "count(*)" in sql:
            if self.missing_schema and self.missing_schema in sql:
                return [(0,)]
            return [(1,)]
        if sql.startswith("SELECT count(*)"):
            return [(0,)]
        raise AssertionError(sql)

    def execute(self, host: str, database: str, sql: str) -> None:
        self.calls.append(("execute", host, database, sql))
        if database == SOURCE_DATABASE:
            raise AssertionError("write attempted on tenant_demo")
        if sql.startswith("DROP") and self.drop_error:
            raise RuntimeError(self.drop_error)


class FakeCommands:
    def __init__(self, codes: dict[str, int] | None = None):
        self.codes = codes or {}
        self.argv: list[list[str]] = []
        self.envs: list[dict | None] = []

    def run(self, argv: list[str], env: dict[str, str] | None = None) -> int:
        self.argv.append(argv)
        self.envs.append(env)
        return self.codes.get(argv[0], 0)


def _request(**overrides) -> CloneRequest:
    payload = dict(
        source=SOURCE,
        clone_host=HOST,
        clone_name=NAME,
        dump_path="/tmp/demo-clone-test-not-created.dump",
    )
    payload.update(overrides)
    return CloneRequest(**payload)


def test_clone_name_and_revision_guards() -> None:
    assert NAME.startswith("tenant_clone_20261017t150405z_")
    with pytest.raises(CloneError):
        make_clone_name(WHEN, "no")
    with pytest.raises(CloneError):
        assert_revision("head")
    with pytest.raises(CloneError):
        assert_revision("heads")
    assert classify_column("people", "email") == "email"
    assert classify_column("load_files", "storage_key") == "storage"
    assert classify_column("mail_accounts", "webhook_url") == "secret"
    with pytest.raises(CloneError):
        classify_column("people", "email;drop")


def test_refuses_protected_targets_before_any_sql() -> None:
    sql = FakeSql(["x5"])
    commands = FakeCommands()
    with pytest.raises(CloneError):
        run_clone(sql, commands, _request(clone_name="tenant_demo"))
    with pytest.raises(CloneError):
        run_clone(sql, commands, _request(clone_host="truckerp-postgres"))
    with pytest.raises(CloneError):
        run_clone(sql, commands, _request(clone_host="172.29.0.4"))
    with pytest.raises(CloneError):
        run_clone(sql, commands, _request(revision="head"))
    assert sql.calls == []
    assert commands.argv == []


def test_successful_clone_sanitizes_upgrades_and_drops() -> None:
    sql = FakeSql(["x5y6z7a8b9c0", "x5y6z7a8b9c0", "x5y6z7a8b9c0", "i14_load_pod_evidence_x5", "x5y6z7a8b9c0"])
    commands = FakeCommands()
    report = run_clone(sql, commands, _request(revision="i14_load_pod_evidence_x5", run_tests=True))
    assert report.sanitize_ok is True
    assert report.schema_ok is True
    assert report.tests_ran is True
    assert report.cleanup == "dropped"
    assert report.error == ""
    assert report.text().count("example.com") == 0
    dump = commands.argv[0]
    assert dump[:2] == ["pg_dump", "-h"]
    assert SOURCE_DATABASE in dump
    assert "-Fc" in dump
    assert "--no-owner" in dump
    assert commands.envs[0]["PGOPTIONS"] == "-c default_transaction_read_only=on"
    upgrade = commands.argv[2]
    assert upgrade[-2:] == ["upgrade", "i14_load_pod_evidence_x5"]
    assert "head" not in upgrade
    assert commands.envs[2]["ALEMBIC_TENANT_DATABASE_URL"].endswith("/" + NAME)
    assert "tenant_demo" not in commands.envs[2]["ALEMBIC_TENANT_DATABASE_URL"]
    test_env = commands.envs[3]
    assert test_env["STORAGE_PROVIDER"] == "local"
    assert test_env["DEMO_CLONE_EXTERNAL_EFFECTS"] == "disabled"
    assert test_env["TRUCKERP_INTEGRATION_ALLOWED_DB_NAMES"] == NAME
    writes = [sql_text for kind, _host, database, sql_text in sql.calls if kind == "execute"]
    assert any(item.startswith('CREATE DATABASE "tenant_clone_') for item in writes)
    assert any(item.startswith('DROP DATABASE "tenant_clone_') and "WITH (FORCE)" in item for item in writes)
    assert any("SET" in item and "@example.invalid" in item for item in writes)
    assert any("storage_key" in item and "NULL" in item for item in writes)
    assert any("webhook_url" in item and "NULL" in item for item in writes)
    assert all("trucking_erp" not in item for item in writes)


def test_sanitization_failure_skips_tests_and_still_drops() -> None:
    sql = FakeSql(["x5", "x5", "x5"])
    sql.query = _query_without_people_email(sql)  # type: ignore[method-assign]
    commands = FakeCommands()
    report = run_clone(sql, commands, _request(run_tests=True))
    assert report.sanitize_ok is False
    assert report.tests_ran is False
    assert report.cleanup == "dropped"
    assert "people.email" in report.error
    assert all(argv[0] != "pytest" for argv in commands.argv)


def test_cleanup_failure_reports_remaining_database_without_secrets() -> None:
    sql = FakeSql(["x5", "x5", "x5"], drop_error="postgresql://cloneuser:s3cret@172.24.0.2/db denied")
    commands = FakeCommands()
    report = run_clone(sql, commands, _request())
    assert report.cleanup == "failed"
    assert report.remaining_database == NAME
    assert "Do not drop tenant_demo" in report.recovery
    rendered = report.text()
    assert "s3cret" not in rendered
    assert "://***@" in rendered
    assert _redact("postgresql://cloneuser:s3cret@host/db") == "postgresql://***@host/db"


def test_source_revision_change_stops_before_tests() -> None:
    sql = FakeSql(["x5", "x5", "changed"])
    commands = FakeCommands()
    report = run_clone(sql, commands, _request(revision="i14_load_pod_evidence_x5", run_tests=True))
    assert "revision changed" in report.error
    assert report.tests_ran is False
    assert all(argv[0] != "alembic" for argv in commands.argv)
    assert report.cleanup == "dropped"


def test_missing_schema_contract_blocks_tests() -> None:
    sql = FakeSql(["x5", "x5", "x5"], missing_schema="trips")
    commands = FakeCommands()
    report = run_clone(
        sql,
        commands,
        _request(schema_contract=(("trips", "id"),), run_tests=True),
    )
    assert "Missing required column trips.id" in report.error
    assert report.tests_ran is False
    assert report.cleanup == "dropped"


def test_main_does_not_create_a_clone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_CLONE_EXECUTE", raising=False)
    assert main([]) == 2
    monkeypatch.setenv("DEMO_CLONE_EXECUTE", "1")
    assert main([]) == 2


def _query_without_people_email(sql: FakeSql):
    original = FakeSql.query

    def query(host: str, database: str, statement: str) -> list[tuple]:
        if "table_name, column_name" in statement:
            sql.calls.append(("query", host, database, statement))
            return [("loads", "id")]
        return original(sql, host, database, statement)

    return query
