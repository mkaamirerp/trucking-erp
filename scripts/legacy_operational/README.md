# Legacy operational scripts (read before use)

**Path:** `scripts/legacy_operational/` — tracked in git (not under `scripts/archive/`, which may match a local `.git/info/exclude` pattern).

Scripts here are **kept for history or one-off recovery** only. They often assume:

- old Compose project names / container names,
- local `.env` or systemd layouts,
- **obsolete tenant database names** (e.g. `tenant_smoke_*`),

and can **conflict** with current production guidance (Docker Compose + SSM, `tenant_demo`, `container_name: truckerp-postgres`).

**Do not run** anything here against production unless you have read the script and verified it matches your environment.

Active maintenance scripts live under `scripts/` (repo root) and `tools/`.

## Scripts in this folder (archived from repo root)

| File | Former purpose (summary) |
|------|---------------------------|
| `fix_tenant_routing.sh` | Legacy compose patch + tenant smoke URL (see its header). |
| `one_go_truckerp_auto.sh` | systemd + `/etc/truckerp` + provision (host model). |
| `fix_truckerp_one_code_auto.sh` | Same class: root, env file, restart, provision. |
| `fix_public_schema_and_provision.sh` | Docker `shared-postgres` + registry probe + provision. |
| `erp_audit.sh` | Long host-based audit (temp uvicorn, old container defaults). |
| `deep_audit_v2.sh` | Read-only capture whose body/summary taught host uvicorn + `shared-postgres` (archived; see script banner). |

**`change_db_password_everywhere.sh`** only scans `scripts/*.sh` (top-level `scripts/` only), not this directory — archived copies are **not** URL-rewrite targets unless that script is extended later.

## Next audit backlog (not archived — review before changing behavior)

| Script | Why revisit |
|--------|-------------|
| **`change_db_password_everywhere.sh`** (repo root) | Defaults still encode an older mental model (`PG_CONTAINER=shared-postgres`, host `venv` uvicorn restart). Behavior was intentionally untouched in recent cleanups; a future pass should align **comments/defaults/docs** with Docker + `truckerp-postgres` + API container without breaking callers who rely on overrides. |
