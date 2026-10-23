#!/usr/bin/env python3
"""Create a disposable tenant database from Alembic (no live production pg_dump).

Optional: restore a previously sanitized offline artifact via TRUCKERP_VERIFICATION_TENANT_ARTIFACT.
"""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.verification_host_guard import (  # noqa: E402
    VerificationHostDenied,
    assert_disposable_verification_host,
    assert_verification_database_url,
)
from app.core.verification_subprocess_env import build_verification_subprocess_env  # noqa: E402
import importlib.util

_clone_spec = importlib.util.spec_from_file_location(
    "demo_clone_runner", _REPO_ROOT / "scripts" / "demo_clone_runner.py"
)
assert _clone_spec and _clone_spec.loader
clone_runner = importlib.util.module_from_spec(_clone_spec)
_clone_spec.loader.exec_module(clone_runner)

ENV_ADMIN_URL = "TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL"
ENV_ARTIFACT = "TRUCKERP_VERIFICATION_TENANT_ARTIFACT"
ENV_TENANT_REVISION = "TRUCKERP_VERIFICATION_TENANT_REVISION"


def _redact(url: str) -> str:
    p = urlparse(url)
    netloc = p.hostname or ""
    if p.port:
        netloc = f"{netloc}:{p.port}"
    if p.username:
        netloc = f"{p.username}:***@{netloc}"
    return urlunparse((p.scheme, netloc, p.path, "", "", ""))


def make_database_name() -> str:
    return clone_runner.make_clone_name(datetime.now(timezone.utc), secrets.token_hex(3))


def _swap_db(url: str, database: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, f"/{database}", "", "", ""))


def _run_psql(admin_url: str, sql: str) -> None:
    env = build_verification_subprocess_env(
        {"TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL": admin_url},
    )
    proc = subprocess.run(
        ["psql", admin_url, "-v", "ON_ERROR_STOP=1", "-c", sql],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "psql failed")


def _run_alembic_tenant_upgrade(async_url: str, revision: str) -> None:
    env = build_verification_subprocess_env({"ALEMBIC_TENANT_DATABASE_URL": async_url})
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic_tenant.ini",
            "upgrade",
            revision,
        ],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "alembic upgrade failed")


def _restore_artifact(admin_url: str, database: str, artifact: Path) -> None:
    tenant_url = _swap_db(admin_url, database)
    env = build_verification_subprocess_env(
        {
            "TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL": admin_url,
            "TENANT_DATABASE_URL": tenant_url,
        }
    )
    if artifact.suffix == ".sql":
        proc = subprocess.run(
            ["psql", tenant_url, "-v", "ON_ERROR_STOP=1", "-f", str(artifact)],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
    else:
        proc = subprocess.run(
            [
                "pg_restore",
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
                "-d",
                tenant_url,
                str(artifact),
            ],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "artifact restore failed")


def bootstrap_tenant_database(
    *,
    admin_url: str,
    revision: str,
    artifact: Path | None,
    database: str | None = None,
) -> dict[str, str]:
    assert_disposable_verification_host()
    assert_verification_database_url(admin_url, context="postgres admin")

    db_name = database or make_database_name()
    clone_runner.assert_clone_name(db_name)

    _run_psql(admin_url, f'CREATE DATABASE "{db_name}"')
    sync_url = _swap_db(admin_url, db_name)
    async_base = admin_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    async_url = _swap_db(async_base.replace("postgresql://", "postgresql+asyncpg://", 1), db_name)

    assert_verification_database_url(async_url, context="tenant target")

    if artifact is not None:
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
        _restore_artifact(admin_url, db_name, artifact)
    else:
        _run_alembic_tenant_upgrade(async_url, revision)

    return {
        "database": db_name,
        "TENANT_DATABASE_URL": sync_url,
        "ALEMBIC_TENANT_DATABASE_URL": async_url,
        "admin_url_redacted": _redact(admin_url),
        "revision": revision,
        "artifact": str(artifact) if artifact else "",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap disposable tenant DB for verification.")
    parser.add_argument("--database", default="")
    parser.add_argument("--revision", default="")
    parser.add_argument("--artifact", default="")
    parser.add_argument("--drop", metavar="DATABASE", default="")
    args = parser.parse_args(argv)

    try:
        assert_disposable_verification_host()
    except VerificationHostDenied as exc:
        print(f"VERIFICATION_BOOTSTRAP_DENIED: {exc}", file=sys.stderr)
        return 78

    admin = (os.environ.get(ENV_ADMIN_URL) or "").strip()
    if not admin:
        print(f"{ENV_ADMIN_URL} is required", file=sys.stderr)
        return 2

    if args.drop:
        try:
            clone_runner.assert_clone_name(args.drop)
            _run_psql(admin, f'DROP DATABASE IF EXISTS "{args.drop}" WITH (FORCE)')
            print(f"dropped={args.drop}")
            return 0
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1

    revision = (args.revision or os.environ.get(ENV_TENANT_REVISION) or "").strip()
    if not revision:
        revision = clone_runner.DEFAULT_DEMO_CLONE_TENANT_REVISION
    revision = clone_runner.assert_revision(revision) or revision

    artifact = Path(args.artifact or os.environ.get(ENV_ARTIFACT) or "")
    art = artifact if str(artifact) else None

    try:
        result = bootstrap_tenant_database(admin_url=admin, revision=revision, artifact=art, database=args.database or None)
    except Exception as exc:
        print(f"VERIFICATION_BOOTSTRAP_FAILED: {exc}", file=sys.stderr)
        return 1

    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
