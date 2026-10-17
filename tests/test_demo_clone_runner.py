"""Mocked tests for the disposable tenant_demo clone runner. No database is created."""

from __future__ import annotations

import importlib.util
import os
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
    ("people", "email", "YES", "character varying", 255, "0", "0"),
    ("people", "phone", "YES", "character varying", 50, "0", "0"),
    ("driver_document_files", "storage_key", "NO", "character varying", 1024, "0", "0"),
    ("tenant_email_accounts", "refresh_token_encrypted", "NO", "bytea", 0, "0", "0"),
    ("tenant_users", "email_norm", "NO", "character varying", 255, "1", "0"),
    ("tenant_email_accounts", "last_gmail_webhook_at", "YES", "timestamp with time zone", 0, "0", "0"),
    ("loads", "id", "NO", "uuid", 0, "0", "0"),
)


class FakeSql:
    def __init__(
        self,
        revisions: list[str],
        *,
        drop_error: str = "",
        missing_schema: str = "",
        exists_answers: list[int] | None = None,
        owned: int = 1,
        create_error: str = "",
        current_name: str = "",
    ):
        self.revisions = list(revisions)
        self.drop_error = drop_error
        self.missing_schema = missing_schema
        self.exists_answers = list(exists_answers if exists_answers is not None else [0, 1])
        self.owned = owned
        self.create_error = create_error
        self.current_name = current_name
        self.calls: list[tuple] = []

    def query(self, host: str, database: str, sql: str) -> list[tuple]:
        self.calls.append(("query", host, database, sql))
        if sql.startswith("SELECT version_num"):
            return [(self.revisions.pop(0),)]
        if sql.startswith("SELECT current_database()"):
            return [(self.current_name or database,)]
        if "FROM pg_database WHERE datname" in sql:
            return [(self.exists_answers.pop(0),)]
        if "pg_shdescription" in sql:
            return [(self.owned,)]
        if "pg_constraint" in sql:
            return [(0,)]
        if "information_schema.columns c" in sql:
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
        if sql.startswith("CREATE") and self.create_error:
            raise CloneError(self.create_error)
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
        dump_path=f"/tmp/{NAME}.dump",
        schema_contract=runner.DEFAULT_SCHEMA + (("load_pod_evidence", "id"),),
    )
    stale = payload["dump_path"]
    if os.path.exists(stale):
        os.remove(stale)
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
    report = run_clone(
        sql,
        commands,
        _request(
            revision="i14_load_pod_evidence_x5",
            run_tests=True,
            test_paths=("tests/test_module.py",),
        ),
    )
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
    assert commands.argv[3] == ["pytest", "tests/test_module.py"]
    assert test_env["STORAGE_PROVIDER"] == "local"
    assert test_env["DEMO_CLONE_EXTERNAL_EFFECTS"] == "disabled"
    assert test_env["TRUCKERP_INTEGRATION_ALLOWED_DB_NAMES"] == NAME
    writes = [sql_text for kind, _host, database, sql_text in sql.calls if kind == "execute"]
    assert any(item.startswith('CREATE DATABASE "tenant_clone_') for item in writes)
    assert any(item.startswith('DROP DATABASE "tenant_clone_') and "WITH (FORCE)" in item for item in writes)
    assert any("SET" in item and "@example.invalid" in item for item in writes)
    assert any("storage_key" in item and "redacted-object-" in item for item in writes)
    assert any("refresh_token_encrypted" in item and "decode(md5" in item for item in writes)
    assert any("last_gmail_webhook_at" in item and "= NULL" in item for item in writes)
    assert not any("storage_key" in item and "= NULL" in item for item in writes)
    assert report.dump_cleanup == "removed"
    assert all("trucking_erp" not in item for item in writes)


def test_sanitization_failure_skips_tests_and_still_drops() -> None:
    sql = FakeSql(["x5", "x5", "x5"])
    sql.query = _query_without_people_email(sql)  # type: ignore[method-assign]
    commands = FakeCommands()
    report = run_clone(sql, commands, _request(run_tests=True, test_paths=("tests/test_module.py",)))
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
    report = run_clone(
        sql,
        commands,
        _request(
            revision="i14_load_pod_evidence_x5",
            run_tests=True,
            test_paths=("tests/test_module.py",),
        ),
    )
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
        _request(schema_contract=(("trips", "id"),), run_tests=True, test_paths=("tests/test_module.py",)),
    )
    assert "Missing required column trips.id" in report.error
    assert report.tests_ran is False
    assert report.cleanup == "dropped"


def test_main_plan_does_not_connect(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "--plan-only",
            "--revision",
            "i14_load_pod_evidence_x5",
            "--test",
            "tests/test_module.py",
            "--schema",
            "load_pod_evidence.id",
            "--name",
            NAME,
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "live_execution=not_started" in output
    assert "source_database=tenant_demo" in output
    assert NAME in output
    assert "i14_load_pod_evidence_x5" in output
    assert "s3cret" not in output


def test_main_refuses_live_execution_without_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_CLONE_EXECUTE", raising=False)
    calls: list = []
    code = main(
        ["--revision", "i14_load_pod_evidence_x5", "--test", "tests/test_module.py", "--name", NAME],
        live_runner=lambda request: calls.append(request),
    )
    assert code == 2
    assert calls == []


def test_approved_entry_refuses_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_CLONE_EXECUTE", raising=False)
    with pytest.raises(CloneError, match="not approved"):
        runner.run_approved_clone(_request())


def test_live_sql_refuses_writes_to_tenant_demo() -> None:
    spawned: list = []

    def spawn(*_args, **_kwargs):
        spawned.append(True)
        raise AssertionError("spawned")

    sql = runner.LiveSql(spawn=spawn)
    with pytest.raises(CloneError, match="tenant_demo"):
        sql.execute("truckerp-postgres", "tenant_demo", "UPDATE people SET email = 'a@example.com'")
    with pytest.raises(CloneError, match="protected database"):
        sql.execute("172.24.0.2", "postgres", 'DROP DATABASE "tenant_demo" WITH (FORCE)')
    assert spawned == []
    completed = type("C", (), {"returncode": 0, "stdout": b"x5\n", "stderr": b""})()
    sql.spawn = lambda *_args, **_kwargs: completed
    assert sql.query("truckerp-postgres", "tenant_demo", "SELECT version_num FROM alembic_version") == [("x5",)]


def test_live_commands_keep_secrets_out_of_argv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SMTP_PASSWORD", "super-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@truckerp-postgres:5432/trucking_erp")
    monkeypatch.setenv("DEMO_CLONE_DB_PASSWORD", "clone-pass")
    recorded: list = []

    def spawn(argv, **kwargs):
        recorded.append((argv, kwargs.get("env")))
        class Completed:
            returncode = 0
            stdout = b""
            stderr = b""
        return Completed()

    commands = runner.LiveCommands(spawn=spawn)
    dump_path = tmp_path / "clone.dump"
    code = commands.run(
        ["pg_dump", "-h", "truckerp-postgres", "-d", "tenant_demo", "-Fc", "--no-owner", "--no-acl", "-f", str(dump_path)],
        env={"PGOPTIONS": "-c default_transaction_read_only=on"},
    )
    assert code == 0
    assert recorded[0][0][:3] == ["docker", "exec", "-e"]
    assert "default_transaction_read_only=on" in " ".join(recorded[0][0])
    assert "tenant_demo" in recorded[0][0]
    assert "clone-pass" not in recorded[0][0]
    assert "super-secret" not in recorded[0][0]
    commands.run(
        ["pytest", "tests/test_module.py"],
        env={
            "TENANT_DATABASE_URL": f"postgresql://172.24.0.2/{NAME}",
            "TRUCKERP_INTEGRATION_ALLOWED_DB_NAMES": NAME,
        },
    )
    child = recorded[1][1]
    assert child["SMTP_PASSWORD"] == ""
    assert "super-secret" not in child.values()
    assert "trucking_erp" not in child["DATABASE_URL"]
    assert child["TENANT_DATABASE_URL"].endswith("/" + NAME)
    assert "clone-pass" not in recorded[1][0]
    assert child["DEMO_CLONE_EXTERNAL_EFFECTS"] == "disabled"
    assert child["GOOGLE_CLIENT_SECRET"] == ""
    assert child["MICROSOFT_WEBHOOK_CLIENT_STATE_SECRET"] == ""
    assert child["STRIPE_SECRET_KEY"] == ""
    assert child["SMTP_HOST"] == ""
    assert "172.29.0.4" not in child["DATABASE_URL"]


def test_preexisting_database_is_not_dropped() -> None:
    sql = FakeSql(["x5"], exists_answers=[1])
    commands = FakeCommands()
    report = run_clone(sql, commands, _request())
    assert "pre-existing" in report.error
    assert report.cleanup == "not-attempted"
    assert not any(item.startswith("DROP") for _kind, _host, _db, item in sql.calls if _kind == "execute")


def test_ambiguous_create_is_not_dropped() -> None:
    sql = FakeSql(["x5"], exists_answers=[0, 1], create_error="connection reset")
    commands = FakeCommands()
    report = run_clone(sql, commands, _request())
    assert "ambiguous" in report.error
    assert report.cleanup == "not-attempted"
    assert report.remaining_database == NAME
    assert "Do not drop" in report.recovery
    assert not any(item.startswith("DROP") for _kind, _host, _db, item in sql.calls if _kind == "execute")


def test_unmarked_database_is_not_dropped() -> None:
    sql = FakeSql(["x5", "x5", "x5"], owned=0)
    commands = FakeCommands()
    report = run_clone(sql, commands, _request())
    assert report.cleanup == "failed"
    assert "did not mark" in report.error
    assert not any(item.startswith("DROP") for _kind, _host, _db, item in sql.calls if _kind == "execute")


def test_wrong_connection_target_blocks_migration() -> None:
    sql = FakeSql(["x5", "x5", "x5"], current_name="tenant_demo")
    commands = FakeCommands()
    report = run_clone(sql, commands, _request(revision="i14_load_pod_evidence_x5", run_tests=True, test_paths=("tests/test_module.py",)))
    assert "does not match" in report.error
    assert all(argv[0] != "alembic" for argv in commands.argv)
    assert report.tests_ran is False


def test_default_schema_contract_is_rejected() -> None:
    sql = FakeSql(["x5"])
    commands = FakeCommands()
    with pytest.raises(CloneError, match="module-specific"):
        run_clone(sql, commands, _request(schema_contract=runner.DEFAULT_SCHEMA))
    assert sql.calls == []


def test_dump_permissions_are_restrictive() -> None:
    path = f"/tmp/{NAME}-perms.dump"
    if os.path.exists(path):
        os.remove(path)
    runner._secure_dump(path)
    assert os.stat(path).st_mode & 0o777 == 0o600
    with pytest.raises(CloneError, match="existing dump"):
        runner._secure_dump(path)
    os.remove(path)


def test_sensitive_replacements_respect_constraints() -> None:
    with pytest.raises(CloneError, match="foreign key"):
        runner._column_profile(("brokers", "email", "YES", "character varying", 255, "0", "1"))
    short = runner._SensitiveColumn("driver_phones", "phone", "phone", False, "character varying", 8, False, False)
    with pytest.raises(CloneError, match="collision-safe"):
        runner._replacement_expr(short, '"driver_phones"')
    required = runner._SensitiveColumn("driver_phones", "phone", "phone", False, "character varying", 30, False, False)
    assert "NULL" not in runner._replacement_expr(required, '"driver_phones"')


def test_cli_requires_module_schema() -> None:
    assert main(["--plan-only", "--revision", "i14_load_pod_evidence_x5", "--test", "tests/test_module.py", "--name", NAME]) == 2


def _query_without_people_email(sql: FakeSql):
    original = FakeSql.query

    def query(host: str, database: str, statement: str) -> list[tuple]:
        if "information_schema.columns c" in statement:
            sql.calls.append(("query", host, database, statement))
            return [("loads", "id", "NO", "uuid", 0, "0", "0")]
        return original(sql, host, database, statement)

    return query
