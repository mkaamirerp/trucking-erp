from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Load env in order: SSM-rendered secrets file (container / host with script), then .env
def _load_env_file(path: str) -> None:
    try:
        fp = Path(path)
        if not fp.exists():
            return
        for line in fp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass

_load_env_file("/run/secrets/truckerp.env")
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")




import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Alembic Config object
config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---- Import your metadata ----
# This MUST point to your declarative Base
from app.models.base import Base  # noqa: E402
import app.models  # noqa: F401

target_metadata = Base.metadata


def _fetch_ssm_param(name: str) -> str | None:
    """Fetch a single SSM parameter via AWS CLI. Returns None if missing or CLI unavailable."""
    ssm_path = os.getenv("SSM_PATH_PLATFORM", "/truckerp/prod/platform/").rstrip("/") + "/"
    param_name = name if name.startswith("/") else ssm_path + name
    region = os.getenv("AWS_REGION", "us-east-1")
    try:
        out = subprocess.run(
            ["aws", "ssm", "get-parameter", "--name", param_name, "--region", region, "--with-decryption", "--query", "Parameter.Value", "--output", "text"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_database_url() -> str:
    # Platform DB: prefer env (from .env or /run/secrets/truckerp.env), then SSM
    url = os.getenv("PLATFORM_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        url = _fetch_ssm_param("PLATFORM_DATABASE_URL") or _fetch_ssm_param("DATABASE_URL")
    if not url:
        env_path = Path(__file__).resolve().parents[1] / ".env"
        raise RuntimeError(
            "PLATFORM_DATABASE_URL or DATABASE_URL must be set. "
            "Use one of: (1) .env in project root, (2) /run/secrets/truckerp.env (SSM-rendered), "
            "(3) AWS CLI + SSM (SSM_PATH_PLATFORM, AWS_REGION). "
            f"Example: add to {env_path} or run with env from SSM."
        )
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
