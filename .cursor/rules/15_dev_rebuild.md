# Rebuild/restart API after changes (mandatory)

After **any** change to backend/API code or config that the running API uses:

1. **Rebuild and restart the API in the same turn** — do not leave it to the user unless they said they will handle deployment.
2. **Commands:**
   - **Production / standard server (image-only):** `/home/admin/trucking_erp-prod-main/scripts/reload_api.sh` only. Do **not** `cd /home/admin/trucking_erp` or run `docker compose build` / `up -d truckerp-api` directly.
   - **Optional local dev:** If using a dev overlay with bind mounts, follow `./scripts/dev-up.sh` or project dev docs — not the default for deployment hosts.
3. If you changed **frontend** (`apps/web/`): **`./scripts/reload_nginx_web.sh`** (canonical: build + rebuild `truckerp-nginx` image). Prod compose bakes `dist` into the image — **`restart` alone is not enough**. See `docs/FRONTEND_DEPLOY.md` and `.cursor/rules/rebuild-restart-commands.mdc`.
4. Only skip if the user explicitly said they will handle deployment/restart.

Applies after edits to: `app/**/*.py` (routers, middleware, deps, config, models), `alembic_platform/**`, or docker/compose that affect the API or nginx container.
