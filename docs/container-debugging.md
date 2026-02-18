# Container Debugging

## 502 Bad Gateway (API not responding)

If **all** API calls (e.g. `/api/v1/me`, `/api/v1/tools/ping`) return **502 Bad Gateway**, nginx is not reaching the API. Common causes:

1. **API container not running or crashed**  
   Check: `docker ps` (is `truckerp-api` up?) and `docker logs truckerp-api`.

2. **API never started** (default command uses AWS SSM)  
   The default `start_api_with_ssm.sh` needs AWS SSM. If SSM is unavailable, the script exits and uvicorn never starts.

   **Fix for local/dev:** Use the dev override so the API runs without SSM and loads env from `.env`:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
   ```
   Ensure a **`.env`** file exists in the repo root with at least `DATABASE_URL` (and `JWT_SECRET`, etc.). The dev override runs uvicorn directly and sources `/app/.env` (your repo’s `.env` when the repo is mounted).

3. **Nginx can’t reach API**  
   Check that `truckerp-api` and `truckerp-nginx` are on the same Docker network and that the API listens on port 8000.

---

## Why `docker exec` Python commands fail

The `truckerp-api` container gets its environment from `/run/secrets/truckerp.env`, which is written at startup by `scripts/start_api_with_ssm.sh`. Uvicorn is launched with `--env-file /run/secrets/truckerp.env`, so the running process has `DATABASE_URL` and other vars.

When you run `docker exec truckerp-api sh -lc 'python -c "..."'`, you get a **new shell** with the container’s default environment. That shell does **not** inherit the env file. As a result, `Settings()` fails with `database_url: Field required`.

## Fix: Source the env file before running Python

Use this pattern for any Python or debugging command:

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && <your command>'
```

- `set -a` — export all variables set in the next step
- `. /run/secrets/truckerp.env` — source the secrets file
- `set +a` — stop auto-exporting
- Then run your command with `DATABASE_URL` and other vars in the environment

## Examples

**Import the app:**
```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -c "from app.main import app; print(\"OK\")"'
```

**List signup/verify/company-setup routes:**
```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -c "
from app.main import app
paths = sorted({getattr(r, \"path\", \"\") for r in app.router.routes})
print(\"\\n\".join([p for p in paths if \"company-setup\" in p or \"verify\" in p or \"signup\" in p]))
"'
```

**Check that env is loaded:**
```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && echo "DATABASE_URL=${DATABASE_URL:0:30}..."'
```

## How this helps you

| Task | How it helps |
|------|--------------|
| **Debug import errors** | Run `python -c "from app.main import app"` inside the container with the same env as the real process. |
| **Inspect routes** | List or filter registered routes to verify signup, verify-otp, company-setup, etc. |
| **Run one-off scripts** | Run small Python scripts (Alembic, DB checks) without writing a separate entrypoint. |
| **Confirm env** | Check that `DATABASE_URL`, `JWT_SECRET`, etc. are present without exposing full values. |
| **Troubleshoot config** | See if config loading fails for the same reasons as in production. |

Without sourcing the env file, any command that touches `app.core.config` will fail. With it, you get the same environment as the running API.
