"""Signup reset refuses protected tenants and keeps the registry row when drop fails."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "tools" / "reset_signup.sh"
GUARD = ROOT / "tools" / "reset_signup_guard.sh"


def _run_guard(function: str, *args: str) -> subprocess.CompletedProcess[str]:
    quoted = " ".join("'" + arg.replace("'", "'\\''") + "'" for arg in args)
    script = f". '{GUARD}'\n{function} {quoted}\n"
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=False)


def test_protected_slug_and_database_are_refused() -> None:
    for args in (
        ("reset_signup_assert_not_protected", "demo", "tenant_other"),
        ("reset_signup_assert_not_protected", "ikl", "tenant_other"),
        ("reset_signup_assert_not_protected", "flowtest-abc", "tenant_demo"),
        ("reset_signup_assert_not_protected", "flowtest-abc", "tenant_ikl"),
    ):
        result = _run_guard(*args)
        assert result.returncode == 1
        assert "protected production tenant" in result.stderr


def test_active_tenant_requires_explicit_slug_and_protected_names_win() -> None:
    refused = _run_guard("reset_signup_assert_active_allowed", "flowtest-abc", "ACTIVE", "")
    assert refused.returncode == 1
    assert "active tenant" in refused.stderr

    allowed = _run_guard(
        "reset_signup_assert_active_allowed", "flowtest-abc", "ACTIVE", "flowtest-abc"
    )
    assert allowed.returncode == 0

    protected = _run_guard("reset_signup_assert_not_protected", "demo", "tenant_demo")
    assert protected.returncode == 1


def test_script_refuses_protected_slug_without_calling_docker(tmp_path: Path) -> None:
    called = tmp_path / "docker-called"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\nprintf called >> '" + str(called) + "'\nexit 99\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    env.pop("RESET_SIGNUP_COMPOSE", None)
    result = subprocess.run(
        ["sh", str(RESET), "demo", "owner@example.com", "tenant_demo"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "protected production tenant" in result.stderr
    assert not called.exists()


def _compose_stub(
    tmp_path: Path,
    *,
    drop_ok: bool,
    still_present: bool,
    delete_ok: bool = True,
    restore_ok: bool = True,
    original_allow: str = "true",
) -> Path:
    log = tmp_path / "sql.log"
    stub = tmp_path / "compose"
    still = "1" if still_present else ""
    drop_status = "0" if drop_ok else "1"
    delete_status = "0" if delete_ok else "1"
    restore_status = "0" if restore_ok else "1"
    stub.write_text(
        f"""#!/bin/sh
printf '%s\\n' "$*" >> '{log}'
case "$*" in
  *'DELETE FROM platform_tenants'*)
    exit {delete_status}
    ;;
  *'FROM platform_tenants WHERE slug'*)
    printf '%s\\n' '9|ACTIVE|tenant_flowtest_abc'
    ;;
  *datallowconn*)
    printf '%s\\n' '{original_allow}'
    ;;
  *'ALLOW_CONNECTIONS true'*|*'ALLOW_CONNECTIONS false'*)
    case "$*" in
      *'ALLOW_CONNECTIONS {original_allow}'*)
        if grep -q 'ALLOW_CONNECTIONS false' '{log}'; then
          exit {restore_status}
        fi
        ;;
    esac
    ;;
  *'DROP DATABASE'*)
    exit {drop_status}
    ;;
  *'SELECT 1 FROM pg_database'*)
    if grep -q 'DROP DATABASE' '{log}'; then
      printf '%s\\n' '{still}'
    else
      printf '%s\\n' '1'
    fi
    ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def _run_reset(tmp_path: Path, stub: Path, *, allow_active: str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RESET_SIGNUP_COMPOSE"] = str(stub)
    if allow_active is None:
        env.pop("RESET_SIGNUP_ALLOW_ACTIVE", None)
    else:
        env["RESET_SIGNUP_ALLOW_ACTIVE"] = allow_active
    return subprocess.run(
        ["sh", str(RESET), "flowtest-abc", "owner@example.com", "tenant_flowtest_abc"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_active_tenant_is_not_dropped_without_explicit_identification(tmp_path: Path) -> None:
    stub = _compose_stub(tmp_path, drop_ok=True, still_present=False)
    result = _run_reset(tmp_path, stub, allow_active=None)
    log = (tmp_path / "sql.log").read_text(encoding="utf-8")
    assert result.returncode == 1
    assert "active tenant" in result.stderr
    assert "DROP DATABASE" not in log
    assert "DELETE FROM platform_tenants" not in log


def test_registry_row_is_kept_when_drop_fails(tmp_path: Path) -> None:
    stub = _compose_stub(tmp_path, drop_ok=False, still_present=True)
    result = _run_reset(tmp_path, stub, allow_active="flowtest-abc")
    log = (tmp_path / "sql.log").read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "DELETE FROM platform_tenants" not in log
    assert "DROP DATABASE" in log


def test_registry_row_is_kept_when_database_remains(tmp_path: Path) -> None:
    stub = _compose_stub(tmp_path, drop_ok=True, still_present=True)
    result = _run_reset(tmp_path, stub, allow_active="flowtest-abc")
    log = (tmp_path / "sql.log").read_text(encoding="utf-8")
    assert result.returncode == 1
    assert "Database drop failed" in result.stderr
    assert "DELETE FROM platform_tenants" not in log


def test_registry_delete_runs_only_after_verified_drop(tmp_path: Path) -> None:
    stub = _compose_stub(tmp_path, drop_ok=True, still_present=False)
    result = _run_reset(tmp_path, stub, allow_active="flowtest-abc")
    log = (tmp_path / "sql.log").read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    drop_at = log.index("DROP DATABASE")
    delete_at = log.index("DELETE FROM platform_tenants")
    assert drop_at < delete_at
    assert "ALLOW_CONNECTIONS false" in log
    assert "WITH (FORCE)" in log


def test_failed_drop_restores_original_allow_connections(tmp_path: Path) -> None:
    stub = _compose_stub(tmp_path, drop_ok=False, still_present=True, original_allow="true")
    result = _run_reset(tmp_path, stub, allow_active="flowtest-abc")
    log = (tmp_path / "sql.log").read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "Restored ALLOW_CONNECTIONS true" in result.stderr
    assert "Registry row" in result.stderr
    assert "DELETE FROM platform_tenants" not in log
    assert "CREATE DATABASE" not in log
    false_at = log.index("ALLOW_CONNECTIONS false")
    drop_at = log.index("DROP DATABASE")
    restore_at = log.index("ALLOW_CONNECTIONS true")
    assert false_at < drop_at < restore_at


def test_allow_connections_restore_failure_is_reported(tmp_path: Path) -> None:
    stub = _compose_stub(
        tmp_path, drop_ok=False, still_present=True, restore_ok=False, original_allow="true"
    )
    result = _run_reset(tmp_path, stub, allow_active="flowtest-abc")
    log = (tmp_path / "sql.log").read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "Recovery failure" in result.stderr
    assert "ALLOW_CONNECTIONS true" in result.stderr
    assert "removed registry" not in result.stdout
    assert "DELETE FROM platform_tenants" not in log
    assert "CREATE DATABASE" not in log


def test_registry_delete_failure_after_drop_is_partial(tmp_path: Path) -> None:
    stub = _compose_stub(tmp_path, drop_ok=True, still_present=False, delete_ok=False)
    result = _run_reset(tmp_path, stub, allow_active="flowtest-abc")
    assert result.returncode != 0
    assert "Partial failure" in result.stderr
    assert "was dropped" in result.stderr
    assert "removed registry" not in result.stdout
    assert "removed registry" not in result.stderr
