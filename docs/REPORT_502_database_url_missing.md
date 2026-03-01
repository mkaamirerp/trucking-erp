# REPORT: truckerp-api restart loop / nginx 502 — DATABASE_URL missing

## 1) Root cause

With the **dev compose override** (`docker-compose.yml` + `docker-compose.dev.yml`), the API container does **not** run `scripts/start_api_with_ssm.sh`. It runs an inline command that sources `/app/.env` and then starts uvicorn. The repo has **no `.env` file** (it is gitignored and was never created). So (1) the shell never exports `DATABASE_URL`, and (2) `app/core/config.py` sets `env_file` only when `.env` exists, so Pydantic loads from no file and gets no `DATABASE_URL` from the process environment. Settings therefore raises `ValidationError: database_url Field required (missing)`, the app exits, and the container restarts in a loop. Production (SSM-first) is unchanged: base compose runs `start_api_with_ssm.sh`, which writes `/run/secrets/truckerp.env` and starts uvicorn with that env—so the 502 is specific to the dev override when `.env` is missing.

## 2) Evidence

- **Container env / secrets**
  - `docker exec truckerp-api ...` (when container was up): `/run/secrets/` exists but **NO `/run/secrets/truckerp.env`** — dev override does not run the SSM script, so secrets are never written.
- **Repo**
  - `ls /home/admin/trucking_erp/.env` → **No such file or directory**; `.env` is in `.gitignore`.
- **Compose**
  - **Base** (`docker-compose.yml`): `command: ["/bin/sh", "-lc", "/app/scripts/start_api_with_ssm.sh"]`; `tmpfs: /run/secrets`; no `env_file`. So prod relies on the script to populate env.
  - **Dev override** (`docker-compose.dev.yml`): `command: ["/bin/sh", "-c", "set -a; [ -f /app/.env ] && . /app/.env; set +a; exec python3 -m uvicorn ..."]`; no `env_file`. So the only source of `DATABASE_URL` in dev is `/app/.env`, which is missing.
- **Settings**
  - `app/core/config.py`: `database_url: str` (required, no default). `model_config.env_file = str(_env_path) if _env_path.exists() else None` with `_env_path = .../ ".env"`. So when `.env` does not exist, `env_file` is `None` and Pydantic only reads from `os.environ`, where `DATABASE_URL` was never set.

## 3) Minimal fix (without breaking SSM-first)

- **Step 1 — Dev compose:** In `docker-compose.dev.yml`, under `truckerp-api`, add `env_file: [.env]` so that when `.env` exists, Compose injects its variables into the container. No DB URL in the `environment:` block; still no SSM required in dev.
- **Step 2 — Provide `.env` for dev:** Create a `.env` in the repo root with at least `DATABASE_URL=postgresql+asyncpg://postgres@truckerp-postgres:5432/trucking_erp` (and optionally `JWT_SECRET=dev-change-me`, etc.). Keep `.env` gitignored. Optionally add `.env.example` with the same keys and placeholder values so others can `cp .env.example .env`.

**Files to change**

1. **`docker-compose.dev.yml`** — add `env_file: [.env]` under `services.truckerp-api`.
2. **Create `.env`** (and optionally `.env.example`) in repo root with `DATABASE_URL` and any other vars needed for local runs.

No change to `app/core/config.py` or to the base compose/SSM design; production continues to use the start script and `/run/secrets/truckerp.env`.
