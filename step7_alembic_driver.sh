#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/admin/trucking_erp"
VENV="$PROJECT_DIR/venv"
SERVICE="trucking_erp"

cd "$PROJECT_DIR"
source "$VENV/bin/activate"

echo "== Step 7: Alembic + Driver model =="

echo "== Installing Alembic (if needed) =="
pip -q install alembic

# -----------------------------
# 1) Create models structure
# -----------------------------
echo "== Creating model files =="

mkdir -p app/models

cat > app/models/base.py <<'EOF'
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
EOF

cat > app/models/driver.py <<'EOF'
from sqlalchemy import String, Date, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(primary_key=True)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Optional (but common + useful)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    hire_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[Date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
EOF

cat > app/models/__init__.py <<'EOF'
from app.models.base import Base
from app.models.driver import Driver

__all__ = ["Base", "Driver"]
EOF

# -----------------------------
# 2) Initialize Alembic (idempotent)
# -----------------------------
if [[ ! -d "alembic" ]]; then
  echo "== Initializing Alembic =="
  alembic init alembic
else
  echo "== Alembic already initialized, skipping init =="
fi

# -----------------------------
# 3) Configure Alembic to use our settings + async engine
# -----------------------------
echo "== Configuring alembic/env.py for async migrations =="

cat > alembic/env.py <<'EOF'
import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Ensure project root is on sys.path so "app.*" imports work
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.core.config import settings
from app.models import Base  # imports Driver too

config = context.config

# Logging config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def get_database_url() -> str:
    # Alembic expects a URL; we use async driver for async migrations
    return (
        f"postgresql+asyncpg://{settings.db_user}:{settings.db_password}"
        f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )

def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
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
    # Set the sqlalchemy.url dynamically
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
EOF

# Make alembic.ini present and readable; env.py sets url dynamically anyway.
if [[ ! -f "alembic.ini" ]]; then
  echo "❌ alembic.ini not found. Alembic init may have failed."
  exit 1
fi

# -----------------------------
# 4) Create migration (autogenerate)
# -----------------------------
echo "== Creating migration for drivers table =="

# If there are no versions yet, create one; otherwise create a new one safely.
mkdir -p alembic/versions

# Generate a migration
alembic revision --autogenerate -m "create drivers table"

# -----------------------------
# 5) Apply migration
# -----------------------------
echo "== Applying migration =="
alembic upgrade head

# -----------------------------
# 6) Verify table exists
# -----------------------------
echo "== Verifying drivers table exists =="

python - <<'PY'
import asyncio
from sqlalchemy import text
from app.db import engine

async def main():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT to_regclass('public.drivers')"))
        print("drivers table:", res.scalar())

asyncio.run(main())
PY

echo "== Restarting API service =="
sudo systemctl restart "$SERVICE"

echo "✅ Step 7 complete: Alembic + drivers model + migration applied"
