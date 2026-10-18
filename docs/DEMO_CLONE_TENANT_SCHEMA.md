# Disposable tenant_demo clone — tenant schema target

`scripts/demo_clone_runner.py` copies **`tenant_demo`** (read-only dump) onto isolated Postgres, optionally upgrades **only the clone**, then runs pytest. **`tenant_demo` is never migrated or written.**

## Default revision (application ORM compatibility)

| Item | Value |
|------|--------|
| Default clone upgrade | `dw1d_load_commercial_evidence_retention_varchar32` |
| Constant | `DEFAULT_DEMO_CLONE_TENANT_REVISION` in `scripts/demo_clone_runner.py` |

This revision is on the **DW-1** line from production’s current stamp (`x5y6z7a8b9c0` via merge `dw0_merge_tenant_heads_a1b2_x5`). It matches the Load/workspace ORM columns used on `gpt-review` (for example `loads.promotion_origin_workspace_draft_id`). Clones left at the dump baseline alone will not match current app models.

**Never** use `alembic upgrade head` or `heads` on clones. The runner refuses those targets.

## Overrides

| Flag / env | Behavior |
|------------|----------|
| *(none)* | Upgrade clone to `DEFAULT_DEMO_CLONE_TENANT_REVISION` |
| `--revision <id>` | Upgrade clone to that explicit revision only |
| `--baseline-only` | No upgrade; clone stays at `tenant_demo`’s stamped revision |
| `DEMO_CLONE_TENANT_REVISION` | Default revision when `--revision` is omitted (still explicit id, not head) |

For POD-specific targets on other lines, see `docs/load_trip/POD_MIGRATION_TARGETS.md`. Pick **one** explicit revision per clone; do not chain both POD heads.

## Pytest database URLs

The runner sets both `TENANT_DATABASE_URL` (sync) and `ALEMBIC_TENANT_DATABASE_URL` (async) on the isolated clone. Tests must not point at `tenant_demo` or production hosts.
