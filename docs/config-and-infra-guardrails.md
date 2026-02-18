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

- **Prod:** Image-only, no host mounts, SSM-only for secrets. Use `docker-compose.yml` only.
- **Dev:** Host mounts allowed **only** in `docker-compose.dev.yml`, never in `docker-compose.yml`.

**Usage:**

- **See changes locally (dev):**  
  `./scripts/dev-up.sh`  
  or: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`  
  Nginx serves `./apps/web/dist` from the host. After editing the frontend, run `npm run build` in `apps/web` and refresh — no image rebuild.

- **Move to Docker (prod-like / deploy):**  
  `./scripts/prod-build-nginx.sh`  
  Builds the frontend and bakes it into the nginx image. Then run `docker compose up -d` (without the dev file) so nginx serves from the image.

- **Production-like (default compose):**  
  `docker compose up -d`  
  Nginx serves the frontend built into the image. Frontend changes require running `prod-build-nginx.sh` then `docker compose up -d`.

This keeps prod stable and limits “works locally but not in CI/prod” drift.
