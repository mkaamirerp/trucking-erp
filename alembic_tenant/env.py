from __future__ import annotations

# --- TruckERP guardrail: load env file for alembic runs ---
import os
from pathlib import Path as _Path

def _load_env_file(path: str) -> None:
    try:
        fp = _Path(path)
        if not fp.exists():
            return
        for line in fp.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip()
            # do not override already-set env vars
            os.environ.setdefault(k, v)
    except Exception:
        # never fail alembic just because env file parsing failed
        return

# Prefer production secrets file if present; fallback to local .env
_load_env_file('/run/secrets/truckerp.env')
_load_env_file('.env')
# --- end guardrail ---

from pathlib import Path
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


def get_database_url() -> str:
    url = os.getenv("ALEMBIC_TENANT_DATABASE_URL")
    if not url:
        raise RuntimeError("ALEMBIC_TENANT_DATABASE_URL is not set. Provide it explicitly for tenant migrations (or set it in .env for local dev)")
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
