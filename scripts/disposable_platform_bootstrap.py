#!/usr/bin/env python3
"""Bootstrap disposable platform database for authorization certification waves.

Runs only after verification_host_preflight passes. Does not use production SSM or prod Postgres.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
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

ENV_ADMIN_URL = "TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL"
DEFAULT_PLATFORM_DB = "platform_verification"
DEFAULT_PLATFORM_REVISION = "0045_platform_tenant_user_map_identity_link_type"


def _swap_db(url: str, database: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, f"/{database}", "", "", ""))


def _run_psql(admin_url: str, sql: str) -> None:
    env = build_verification_subprocess_env(
        {"TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL": admin_url},
    )
    proc = subprocess.run(
        ["psql", admin_url, "-v", "ON_ERROR_STOP=1", "-c", sql],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "psql failed")


def _platform_upgrade(sync_url: str, revision: str) -> None:
    env = build_verification_subprocess_env({"DATABASE_URL": sync_url})
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic_platform.ini", "upgrade", revision],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "platform alembic failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default=DEFAULT_PLATFORM_DB)
    parser.add_argument("--revision", default=DEFAULT_PLATFORM_REVISION)
    args = parser.parse_args()

    try:
        assert_disposable_verification_host()
    except VerificationHostDenied as exc:
        print(f"VERIFICATION_PLATFORM_DENIED: {exc}", file=sys.stderr)
        return 78

    admin = (os.environ.get(ENV_ADMIN_URL) or "").strip()
    if not admin:
        print(f"{ENV_ADMIN_URL} is required", file=sys.stderr)
        return 2

    assert_verification_database_url(admin, context="platform admin")
    db = args.database
    _run_psql(admin, f'CREATE DATABASE "{db}"')
    sync = _swap_db(admin, db)
    async_url = sync.replace("postgresql://", "postgresql+asyncpg://", 1)
    _platform_upgrade(sync, args.revision)
    print(f"DATABASE_URL={sync}")
    print(f"platform_database={db}")
    print(
        "NEXT: seed platform_tenants/users and Casbin — see tests/support/disposable_verification_auth.py"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
