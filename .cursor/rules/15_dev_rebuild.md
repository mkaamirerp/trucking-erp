# Rebuild/restart API after changes (mandatory)

After **any** change to backend/API code or config that the running API uses:

1. **Rebuild and restart the API in the same turn** — do not leave it to the user unless they said they will handle deployment.
2. **Commands (dev playground / this host):**
   - **Default:** `/home/admin/trucking_erp/scripts/reload_api.sh` (branch `main`, clean worktree).
   - **Alias:** `scripts/dev_reload_api.sh` (same guards).
3. If you changed **frontend** (`apps/web/`): **`./scripts/reload_nginx_web.sh`**. Prod compose bakes `dist` into the image — **`restart` alone is not enough**. See `docs/FRONTEND_DEPLOY.md` and `.cursor/rules/rebuild-restart-commands.mdc`.
4. Only skip if the user explicitly said they will handle deployment/restart.

Applies after edits to: `app/**/*.py`, `alembic_platform/**`, or docker/compose that affect the API or nginx container.

Integration tests on this host: see `.cursor/rules/dev-playground-host.mdc`.
