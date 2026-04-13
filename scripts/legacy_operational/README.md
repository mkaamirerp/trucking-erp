# Legacy operational scripts (read before use)

**Path:** `scripts/legacy_operational/` — tracked in git (not under `scripts/archive/`, which may match a local `.git/info/exclude` pattern).

Scripts here are **kept for history or one-off recovery** only. They often assume:

- old Compose project names / container names,
- local `.env` or systemd layouts,
- **obsolete tenant database names** (e.g. `tenant_smoke_*`),

and can **conflict** with current production guidance (Docker Compose + SSM, `tenant_demo`, `container_name: truckerp-postgres`).

**Do not run** anything here against production unless you have read the script and verified it matches your environment.

Active maintenance scripts live under `scripts/` (repo root) and `tools/`.
