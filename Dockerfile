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
FROM python:3.13-slim-bookworm AS prod
# Baked images omit .git (.dockerignore). Pass at build for tenant preflight / upgrade logs:
#   docker build --build-arg TRUCKERP_APP_GIT_SHA=$(git rev-parse --short HEAD) ...
ARG TRUCKERP_APP_GIT_SHA=
ENV TRUCKERP_APP_GIT_SHA=${TRUCKERP_APP_GIT_SHA}
WORKDIR /app

# Runtime libs and migration wrapper tooling: libpq5, curl, jq, ca-certificates,
# postgresql-client for psql preflight checks, and git for repo drift proof.
# Workaround for CI/sandbox: allow insecure repos if apt GPG verification fails.
RUN apt-get update -o Acquire::Retries=3 -o Acquire::http::Timeout=30 \
        -o Acquire::AllowInsecureRepositories=true \
        -o Acquire::AllowDowngradeFromInsecureRepositories=true \
    && apt-get install -y --no-install-recommends -o APT::Get::AllowUnauthenticated=true \
        libpq5 \
        curl \
        jq \
        git \
        postgresql-client \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir "awscli==1.44.59"
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

# --- DEV TOOLBELT STAGE (debug utilities, non-prod) ---
FROM prod AS dev
COPY requirements-dev.txt /app/requirements-dev.txt
RUN python -m pip install --no-cache-dir -r /app/requirements-dev.txt \
    && python -m pytest --version
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    bash \
    ca-certificates \
    procps \
    iproute2 \
    netcat-openbsd \
    postgresql-client \
    openssl \
    less \
    vim-tiny \
 && rm -rf /var/lib/apt/lists/*
