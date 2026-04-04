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

- **Standard deployment:** Image-only (or as defined in `docker-compose.yml`), SSM-only for secrets where applicable. Use **`docker compose -f docker-compose.yml`** — do not assume a dev overlay on the server.
- **Optional local dev:** Host mounts and relaxed startup may exist **only** in `docker-compose.dev.yml`. Never put dev-only mounts in `docker-compose.yml`.

**Usage:**

- **Deployment / primary server:**  
  `docker compose -f docker-compose.yml up -d`  
  Rebuild services (API, nginx) after code or image changes as documented in `.cursor/rules/rebuild-restart-commands.mdc` and `scripts/reload_api.sh`.

- **Optional local iteration (bind mounts, etc.):**  
  `./scripts/dev-up.sh`  
  or: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`  
  Only when you intentionally use the dev overlay. Nginx may serve `./apps/web/dist` from the host depending on that file — after frontend edits, `npm run build` in `apps/web` may be enough without an nginx image rebuild.

- **Bake frontend into nginx image (some workflows):**  
  `./scripts/prod-build-nginx.sh`  
  then `docker compose -f docker-compose.yml up -d` so nginx serves assets from the image.

This keeps prod stable and limits “works locally but not in CI/prod” drift.
