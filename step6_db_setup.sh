#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/admin/trucking_erp"
VENV="$PROJECT_DIR/venv"
ENV_FILE="$PROJECT_DIR/.env"
CONFIG_FILE="$PROJECT_DIR/app/core/config.py"
MAIN_FILE="$PROJECT_DIR/app/main.py"
DB_FILE="$PROJECT_DIR/app/db.py"
DB_ROUTER_FILE="$PROJECT_DIR/app/routers/db_test.py"
SERVICE_NAME="trucking_erp"

echo "== Trucking ERP Step 6: DB setup =="

# --- Preflight ---
if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "❌ Project dir not found: $PROJECT_DIR"
  exit 1
fi
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "❌ venv not found at: $VENV"
  exit 1
fi

cd "$PROJECT_DIR"
source "$VENV/bin/activate"

# --- Install deps ---
echo "== Installing dependencies =="
pip install -q "sqlalchemy>=2.0" asyncpg alembic pydantic-settings

# --- Collect DB info ---
echo
echo "Docker Postgres host port check (optional):"
echo "Run manually if unsure: docker ps --format \"table {{.Names}}\t{{.Ports}}\t{{.Image}}\""
echo

read -r -p "Enter DB host port (default 5432): " DB_PORT
DB_PORT="${DB_PORT:-5432}"

read -r -s -p "Enter DB password for erp_user (hidden): " DB_PASSWORD
echo

# --- Ensure .env exists & update keys (use field names that match Settings) ---
echo "== Writing .env =="
# Preserve existing non-db keys if file exists; rewrite db keys deterministically
touch "$ENV_FILE"

# Remove existing db_* keys (if any)
grep -vE '^(db_host|db_port|db_name|db_user|db_password)=' "$ENV_FILE" > "$ENV_FILE.tmp" || true

cat >> "$ENV_FILE.tmp" <<EOF
db_host="127.0.0.1"
db_port=$DB_PORT
db_name="trucking_erp"
db_user="erp_user"
db_password="$DB_PASSWORD"
EOF

mv "$ENV_FILE.tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"

# --- Patch config.py to include DB fields if missing ---
echo "== Updating app/core/config.py =="
python - <<'PY'
from pathlib import Path

p = Path("/home/admin/trucking_erp/app/core/config.py")
text = p.read_text()

# Ensure pydantic_settings import exists (you already had it, but safe)
if "from pydantic_settings import BaseSettings, SettingsConfigDict" not in text:
    text = "from pydantic_settings import BaseSettings, SettingsConfigDict\n\n" + text

# Ensure db fields exist in Settings
if "db_host:" not in text:
    insert_after = 'environment: str = "dev"\n'
    if insert_after in text:
        text = text.replace(
            insert_after,
            insert_after + "\n"
            '    db_host: str = "127.0.0.1"\n'
            "    db_port: int = 5432\n"
            '    db_name: str = "trucking_erp"\n'
            '    db_user: str = "erp_user"\n'
            '    db_password: str = ""\n'
        )
    else:
        # fallback: append inside class Settings (best-effort)
        marker = "class Settings(BaseSettings):"
        if marker in text:
            parts = text.split(marker, 1)
            text = parts[0] + marker + "\n" + \
                   '    db_host: str = "127.0.0.1"\n' + \
                   "    db_port: int = 5432\n" + \
                   '    db_name: str = "trucking_erp"\n' + \
                   '    db_user: str = "erp_user"\n' + \
                   '    db_password: str = ""\n' + parts[1]

p.write_text(text)
print("config.py patched")
PY

# --- Create app/db.py ---
echo "== Creating app/db.py =="
cat > "$DB_FILE" <<'EOF'
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

DATABASE_URL = (
    f"postgresql+asyncpg://{settings.db_user}:{settings.db_password}"
    f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
EOF

# --- Create db test router ---
echo "== Creating app/routers/db_test.py =="
cat > "$DB_ROUTER_FILE" <<'EOF'
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db import get_db

router = APIRouter(tags=["db"])

@router.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    return {"db": "ok", "value": result.scalar_one()}
EOF

# --- Patch app/main.py to include db router ---
echo "== Updating app/main.py =="
python - <<'PY'
from pathlib import Path

p = Path("/home/admin/trucking_erp/app/main.py")
t = p.read_text()

# Ensure db router import
if "from app.routers.db_test import router as db_router" not in t:
    # Insert after health import (most stable for your file)
    if "from app.routers.health import router as health_router\n" in t:
        t = t.replace(
            "from app.routers.health import router as health_router\n",
            "from app.routers.health import router as health_router\nfrom app.routers.db_test import router as db_router\n"
        )
    else:
        # Fallback: add near top
        t = "from app.routers.db_test import router as db_router\n" + t

# Ensure include_router for db
needle = 'app.include_router(health_router, prefix="/api/v1")'
if needle in t and 'app.include_router(db_router, prefix="/api/v1")' not in t:
    t = t.replace(needle, needle + '\napp.include_router(db_router, prefix="/api/v1")')

p.write_text(t)
print("main.py patched")
PY

# --- Restart service and test ---
echo "== Restarting systemd service =="
sudo systemctl restart "$SERVICE_NAME"

echo "== Waiting briefly for service to bind =="
sleep 1

echo "== Testing /api/v1/db-check =="
set +e
OUT=$(curl -sS http://127.0.0.1:8000/api/v1/db-check)
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  echo "❌ curl failed. Checking service status/logs..."
  sudo systemctl status "$SERVICE_NAME" --no-pager || true
  sudo journalctl -u "$SERVICE_NAME" -n 60 --no-pager || true
  exit 1
fi

echo "✅ Response: $OUT"
echo "✅ Step 6 done if response shows db ok + value 1"
