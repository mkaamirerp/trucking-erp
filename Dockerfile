FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libpq-dev gcc awscli jq && rm -rf /var/lib/apt/lists/*
# Base runtime deps
RUN python -m pip install --no-cache-dir uvicorn fastapi sqlalchemy asyncpg psutil pydantic-settings

# App deps
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

# Build-time sanity gates
RUN python -m pip check
RUN python - <<'PY'
import fastapi, uvicorn, sqlalchemy, asyncpg, alembic  # noqa: F401
print("imports OK")
PY

COPY . .
RUN chmod +x scripts/start_api_with_ssm.sh
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
