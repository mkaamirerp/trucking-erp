# Config and infra guardrails

Three layers enforce that critical config (YAML, env, nginx, secrets) is not changed by mistake.

## Layer A — Pre-commit (blocks local mistakes)

**Protected files:**  
`docker-compose.yml`, `docker-compose.*.yml`, `.env*` (except `.env.example`), `infra/nginx/*`, `scripts/start_api_with_ssm.sh`, `scripts/*ssm*.sh`, `scripts/render_truckerp_env_from_ssm.sh`, `scripts/with_env.sh`, `run/secrets` (if tracked).

**Behavior:**  
A commit that touches any protected file **fails** unless an override is set.

**Install the hook (once):**
```bash
./scripts/install_protected_files_hook.sh
```

**Bypass (when you intend to change config):**
```bash
APPROVED_CONFIG_CHANGE=1 git commit -m "CONFIG-CHANGE: <reason>"
```

---

## Layer B — CI (blocks PRs)

**Behavior:**  
If the diff vs base branch changes any protected file, the **Config Guard** workflow fails unless one of:

- PR title contains `CONFIG-CHANGE: <reason>`
- Any commit message in the PR contains `CONFIG-CHANGE: <reason>`
- `docs/CONFIG_CHANGE_APPROVAL.md` is updated in the same change set with a short justification

No approval → CI fails.

---

## Layer C — Runtime “single source of truth”

- **Public server / production:** Use **`docker compose -f docker-compose.yml` only** (single file). No `docker-compose.dev.yml` on internet-facing hosts. SSM-only secrets per `scripts/start_api_with_ssm.sh`.
- **Local-only file:** `docker-compose.dev.yml` is for engineering machines (bind mounts, API `:8000` on host, `SSM_ENV=dev`). Read the warning banner at the top of that file. Never put dev-only mounts in `docker-compose.yml`.

**Usage:**

- **Deploy / public server (canonical):**  
  `docker compose -f docker-compose.yml up -d`  
  Rebuild API/nginx via `.cursor/rules/rebuild-restart-commands.mdc`, `scripts/reload_api.sh`, and `scripts/publish_frontend.sh`.

- **Prod-shaped stack on a dev machine (still no dev overlay):**  
  `./scripts/dev-up.sh` — same as **`docker compose -f docker-compose.yml`** build/up only.

- **Explicit local overlay (laptop / sandbox only, never public server):**  
  `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`  
  Nginx may serve `./apps/web/dist` from a bind mount per that file; do not document this path as production-safe.

- **Frontend baked into nginx image:**  
  `./scripts/prod-build-nginx.sh` or `./scripts/publish_frontend.sh`  
  then `docker compose -f docker-compose.yml up -d truckerp-nginx` as needed.

This keeps prod stable and limits “works locally but not in CI/prod” drift.
