# ---------- Builder (has compilers) ----------
FROM python:3.13-slim-bookworm AS builder
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip wheel setuptools
RUN python -m pip wheel --wheel-dir /wheels -r requirements.txt

# ---------- Runtime (no compilers) ----------
FROM python:3.13-slim-bookworm
WORKDIR /app

# Only runtime libs (no gcc, no libpq-dev)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    jq \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir awscli
# Base runtime deps
RUN python -m pip install --no-cache-dir uvicorn fastapi sqlalchemy asyncpg psutil pydantic-settings alembic

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN python -m pip install --no-cache-dir /wheels/*

RUN python -m pip check
RUN python - <<'PY'
import fastapi, uvicorn, sqlalchemy, asyncpg, alembic  # noqa: F401
print("imports OK")
PY

COPY . .
RUN chmod +x scripts/start_api_with_ssm.sh

CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
