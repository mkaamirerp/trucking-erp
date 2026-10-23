#!/usr/bin/env python3
"""Fail-closed F1/§14 verification orchestrator (disposable DB only, JUnit per wave)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.verification_host_guard import (  # noqa: E402
    VerificationHostDenied,
    assert_disposable_verification_host,
    assert_verification_auth_not_bypassed,
)
from app.core.verification_subprocess_env import build_verification_subprocess_env  # noqa: E402

import importlib.util

_bootstrap_spec = importlib.util.spec_from_file_location(
    "disposable_tenant_bootstrap", _REPO_ROOT / "scripts" / "disposable_tenant_bootstrap.py"
)
assert _bootstrap_spec and _bootstrap_spec.loader
_bootstrap_mod = importlib.util.module_from_spec(_bootstrap_spec)
_bootstrap_spec.loader.exec_module(_bootstrap_mod)
bootstrap_tenant_database = _bootstrap_mod.bootstrap_tenant_database

_clone_spec = importlib.util.spec_from_file_location(
    "demo_clone_runner", _REPO_ROOT / "scripts" / "demo_clone_runner.py"
)
assert _clone_spec and _clone_spec.loader
clone_runner = importlib.util.module_from_spec(_clone_spec)
_clone_spec.loader.exec_module(clone_runner)

PREFLIGHT = _REPO_ROOT / "scripts" / "verification_host_preflight.py"
PLATFORM_BOOT = _REPO_ROOT / "scripts" / "disposable_platform_bootstrap.py"
PLATFORM_SEED = _REPO_ROOT / "scripts" / "disposable_platform_seed.py"
EXIT_PREFLIGHT = 78
DEFAULT_PLATFORM_DB = "platform_verification"


@dataclass(frozen=True)
class VerificationWave:
    wave_id: str
    test_paths: tuple[str, ...]
    certification_auth: bool = False


DEFAULT_WAVES: tuple[VerificationWave, ...] = (
    VerificationWave(
        "wave1-f1-core",
        (
            "tests/test_load_writer_freeze_issue0a.py::TestSharedCommercialInsertionUnit",
            "tests/test_load_workspace_draft_api.py",
        ),
    ),
    VerificationWave(
        "wave3-auth-certification",
        (
            "tests/test_disposable_verification_auth_unit.py",
            "tests/test_load_cancel_issue5.py",
        ),
        certification_auth=True,
    ),
)


def _git_revision() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "").strip() if proc.returncode == 0 else "unknown"


def _run_preflight() -> int:
    env = build_verification_subprocess_env({})
    proc = subprocess.run([sys.executable, str(PREFLIGHT)], cwd=_REPO_ROOT, env=env)
    return proc.returncode


def _run_script(script: Path, extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    env = build_verification_subprocess_env(extra_env)
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _parse_kv_output(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def _ensure_certification_platform(admin_url: str, tenant_env: dict[str, str]) -> dict[str, str]:
    proc = _run_script(
        PLATFORM_BOOT,
        {
            "TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL": admin_url,
            "DATABASE_URL": "",
        },
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "platform bootstrap failed")
    platform = _parse_kv_output(proc.stdout)
    database_url = platform.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("platform bootstrap did not emit DATABASE_URL")

    seed_proc = _run_script(
        PLATFORM_SEED,
        {
            "TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL": admin_url,
            "DATABASE_URL": database_url,
            "TENANT_DATABASE_URL": tenant_env["TENANT_DATABASE_URL"],
            "TRUCKERP_VERIFICATION_TENANT_SLUG": "pytest",
        },
    )
    if seed_proc.returncode != 0:
        raise RuntimeError(seed_proc.stderr or seed_proc.stdout or "platform seed failed")
    seed = _parse_kv_output(seed_proc.stdout)
    return {"DATABASE_URL": database_url, **seed}


def _environment_manifest() -> dict[str, str]:
    allowed = (
        "ENVIRONMENT",
        "TRUCKERP_VERIFICATION_RUN_ID",
        "TRUCKERP_VERIFICATION_TENANT_REVISION",
        "TRUCKERP_VERIFICATION_AUTH_MODE",
        "TRUCKERP_VERIFICATION_DISPOSABLE_CI",
    )
    return {key: os.environ[key] for key in allowed if os.environ.get(key)}


def _run_pytest_wave(
    wave: VerificationWave,
    artifact_dir: Path,
    tenant_env: dict[str, str],
    platform_env: dict[str, str],
) -> tuple[int, Path]:
    junit = artifact_dir / f"junit-{wave.wave_id}.xml"
    log = artifact_dir / f"pytest-{wave.wave_id}.log"
    updates = {
        **tenant_env,
        "TRUCKERP_VERIFICATION_RUN_ID": artifact_dir.name,
        "DEMO_CLONE_EXTERNAL_EFFECTS": "disabled",
        "ENVIRONMENT": "test",
        "STORAGE_PROVIDER": "local",
        "ALLOW_TENANT_RESOLUTION_SHORTCUTS": "true",
    }
    if wave.certification_auth:
        assert_verification_auth_not_bypassed()
        updates["TRUCKERP_VERIFICATION_AUTH_MODE"] = "certification"
        updates.update(platform_env)
        updates["CASBIN_LOAD_PILOT_ENFORCEMENT"] = "true"
        env = build_verification_subprocess_env(updates, allow_test_bypass_auth=False)
    else:
        updates["TRUCKERP_VERIFICATION_AUTH_MODE"] = "service"
        env = build_verification_subprocess_env(
            {**updates, "TEST_BYPASS_AUTH": "1"},
            allow_test_bypass_auth=True,
        )

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *wave.test_paths,
        "--verbose",
        f"--junitxml={junit}",
    ]
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, cwd=_REPO_ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT)
    return proc.returncode, junit


def _drop_tenant_database(admin_url: str, database: str) -> None:
    env = build_verification_subprocess_env({"TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL": admin_url})
    subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "disposable_tenant_bootstrap.py"), "--drop", database],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def run_verification(
    *,
    artifact_dir: Path,
    waves: tuple[VerificationWave, ...],
    admin_url: str,
    tenant_revision: str,
    artifact_path: Path | None,
) -> dict:
    assert_disposable_verification_host()
    if _run_preflight() != 0:
        raise VerificationHostDenied("preflight subprocess failed")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "run_id": artifact_dir.name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": _git_revision(),
        "tenant_revision": tenant_revision,
        "waves": [],
        "environment": _environment_manifest(),
        "preflight": "passed",
    }

    tenant_db_name = ""
    try:
        bootstrap = bootstrap_tenant_database(
            admin_url=admin_url,
            revision=tenant_revision,
            artifact=artifact_path,
        )
        tenant_db_name = bootstrap["database"]
        tenant_env = {
            "TENANT_DATABASE_URL": bootstrap["TENANT_DATABASE_URL"],
            "ALEMBIC_TENANT_DATABASE_URL": bootstrap["ALEMBIC_TENANT_DATABASE_URL"],
            "TRUCKERP_INTEGRATION_ALLOWED_DB_NAMES": bootstrap["database"],
            "TRUCKERP_INTEGRATION_TENANT_DB": bootstrap["database"],
        }
        manifest["tenant_database"] = tenant_db_name
        (artifact_dir / "bootstrap.json").write_text(json.dumps(bootstrap, indent=2), encoding="utf-8")

        platform_env: dict[str, str] = {}
        if any(wave.certification_auth for wave in waves):
            platform_env = _ensure_certification_platform(admin_url, tenant_env)
            (artifact_dir / "platform_seed.json").write_text(json.dumps(platform_env, indent=2), encoding="utf-8")

        for wave in waves:
            code, junit_path = _run_pytest_wave(wave, artifact_dir, tenant_env, platform_env)
            wave_record = {
                "wave_id": wave.wave_id,
                "test_paths": list(wave.test_paths),
                "exit_code": code,
                "junit_xml": str(junit_path),
                "certification_auth": wave.certification_auth,
            }
            manifest["waves"].append(wave_record)
            manifest_path = artifact_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            if code != 0:
                manifest["status"] = "failed"
                manifest["failed_wave"] = wave.wave_id
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                return manifest

        manifest["status"] = "passed"
        (artifact_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    finally:
        if tenant_db_name:
            _drop_tenant_database(admin_url, tenant_db_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run disposable verification waves (fail-closed).")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--revision", default="")
    parser.add_argument("--tenant-artifact", default="")
    parser.add_argument("--wave", action="append", default=[], help="Limit to wave id (repeatable)")
    args = parser.parse_args(argv)

    admin = (os.environ.get("TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL") or "").strip()
    if not admin:
        print("TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL is required", file=sys.stderr)
        return 2

    revision = (args.revision or os.environ.get("TRUCKERP_VERIFICATION_TENANT_REVISION") or "").strip()
    if not revision:
        revision = clone_runner.DEFAULT_DEMO_CLONE_TENANT_REVISION

    waves = DEFAULT_WAVES
    if args.wave:
        allowed = {w.wave_id: w for w in DEFAULT_WAVES}
        waves = tuple(allowed[w] for w in args.wave if w in allowed)
        if not waves:
            print("no matching waves", file=sys.stderr)
            return 2

    art_path = Path(args.tenant_artifact) if args.tenant_artifact else None

    try:
        manifest = run_verification(
            artifact_dir=Path(args.artifact_dir),
            waves=waves,
            admin_url=admin,
            tenant_revision=revision,
            artifact_path=art_path,
        )
    except VerificationHostDenied as exc:
        print(f"VERIFICATION_RUN_DENIED: {exc}", file=sys.stderr)
        return EXIT_PREFLIGHT
    except Exception as exc:
        print(f"VERIFICATION_RUN_FAILED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"status": manifest.get("status"), "artifact_dir": args.artifact_dir}))
    return 0 if manifest.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
