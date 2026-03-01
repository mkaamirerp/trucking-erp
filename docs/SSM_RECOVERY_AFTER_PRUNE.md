# SSM recovery after Docker prune

If you ran `docker system prune` (or similar) and the API won’t start because “SSM is not working,” use this to get back to a running state.

## 1. See why the API is failing

```bash
docker logs truckerp-api --tail 80
```

Look for:

- **"FATAL: … missing in /run/secrets/truckerp.env"** → SSM ran but didn’t return required vars (wrong path or missing params).
- **"ERROR: No secrets. Configure AWS SSM or create …"** → SSM fetch failed (no credentials, wrong region, or no params) and there is no valid `.env` fallback.
- **"FATAL: .env must define non-empty …"** → You’re using `.env` but a required variable is missing or empty.

## 2. Option A — Fix SSM (preferred for prod/dev with AWS)

1. **Credentials in the API container**  
   The container needs AWS credentials (instance profile, or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in the environment). With dev compose, the host’s env is not automatically passed; add them in `docker-compose.dev.yml` only if you accept the security tradeoff, or run the stack on an EC2 instance with an IAM role that has `ssm:GetParametersByPath` on `/truckerp/*`.

2. **Path and region**  
   With `SSM_ENV=dev` (in docker-compose.dev.yml), the script reads:
   - `/truckerp/dev/platform/`
   - `/truckerp/dev/shared/`  
   Ensure these parameters exist in the same region the container uses (`AWS_REGION`, default `us-east-1`).

3. **Required parameters**  
   At minimum, SSM must provide (under the paths above):
   - `DATABASE_URL` (platform DB, e.g. `postgresql+asyncpg://...`)
   - `POSTGRES_ADMIN_URL` (e.g. `postgresql://...`)
   - `POSTGRES_PASSWORD`  
   Optional but recommended: `TENANT_DATABASE_URL`, `JWT_SECRET`.

4. **One-time (re)create dev SSM params**  
   See **docs/SSM_ENV_DEV_PROD_SPLIT.md** (“One-time AWS CLI: create dev SSM params”) to create or repopulate `/truckerp/dev/platform/` and `/truckerp/dev/shared/` (e.g. from prod or from your chosen values).

5. **Restart API**  
   After fixing credentials/path/params:
   ```bash
   cd /home/admin/trucking_erp
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d truckerp-api
   docker logs truckerp-api --tail 30
   ```

## 3. Option B — Run without SSM using `.env` (dev only)

When SSM is unavailable or broken, the startup script can use a file at **`/app/.env`** in the container. With dev compose, `.:/app` is mounted, so that file is **`.env` in the repo root** on the host.

1. **Create `.env` in the repo root** (e.g. `/home/admin/trucking_erp/.env`):

   ```bash
   # Required (replace YOUR_POSTGRES_PASSWORD with the real postgres password)
   DATABASE_URL=postgresql+asyncpg://postgres:YOUR_POSTGRES_PASSWORD@truckerp-postgres:5432/trucking_erp
   POSTGRES_ADMIN_URL=postgresql://postgres:YOUR_POSTGRES_PASSWORD@truckerp-postgres:5432/postgres
   POSTGRES_PASSWORD=YOUR_POSTGRES_PASSWORD

   # Optional; app has defaults if missing
   JWT_SECRET=dev-change-me

   # Tenant DB (same host/password, different DB name)
   TENANT_DATABASE_URL=postgresql+asyncpg://postgres:YOUR_POSTGRES_PASSWORD@truckerp-postgres:5432/tenant_demo
   ```

2. **If you don’t know the postgres password**  
   - If the postgres volume was recreated by prune, the default may be empty or whatever you set in `POSTGRES_PASSWORD` when the volume was first created.  
   - You can reset it: start only postgres, then  
     `docker compose exec truckerp-postgres psql -U postgres -c "ALTER USER postgres WITH PASSWORD 'yourchosenpassword';"`  
     and use that same password in `.env`.

3. **Restart the API**  
   The script will see SSM fail, then use `.env` and validate that `DATABASE_URL`, `POSTGRES_ADMIN_URL`, and `POSTGRES_PASSWORD` are set and non-empty before starting uvicorn:

   ```bash
   cd /home/admin/trucking_erp
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d truckerp-api
   docker logs truckerp-api --tail 30
   ```

4. **Security**  
   `.env` is gitignored. Use this only for local/dev. Do not commit `.env` or use it in production; use SSM (Option A).

## 4. If the image was pruned

If you ran `docker system prune -a` and the API image was removed, rebuild and then start:

```bash
cd /home/admin/trucking_erp
docker compose -f docker-compose.yml -f docker-compose.dev.yml build truckerp-api
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d truckerp-api
```

Then follow Option A or B above if the container still exits with SSM or secrets errors.

## 5. Quick reference

| Symptom | What to do |
|--------|-------------|
| “FATAL: … missing in truckerp.env” | Fix SSM parameters/path or switch to `.env` (Option B). |
| “ERROR: No secrets. Configure AWS SSM or create …” | Add AWS credentials/path (Option A) or create `.env` (Option B). |
| “FATAL: .env must define non-empty …” | Add missing vars to repo root `.env` (DATABASE_URL, POSTGRES_ADMIN_URL, POSTGRES_PASSWORD). |
| Container exits immediately, no FATAL/ERROR | Run `docker logs truckerp-api --tail 80` and look for Python/Settings errors (e.g. missing env). |
