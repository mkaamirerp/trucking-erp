# Archived DB schema markdown (January 2026 snapshot)

This folder is **git-tracked** (see note in `scripts/legacy_operational/README.md` about local `archive/` excludes).

These files were generated against **obsolete** assumptions:

- Postgres container name `trucking_erp-truckerp-postgres-1` (not `truckerp-postgres`)
- Tenant databases `tenant_smoke_active` / `tenant_smoke_provision` instead of canonical **`tenant_demo`**
- README referenced a non-existent `export_schema_docs_v2.sh`

**Current docs:** regenerate from repo root with:

```bash
PG_CONTAINER=truckerp-postgres bash scripts/export_schema_docs.sh
```

Output lives in `docs/db_schema/` (see that folder’s README).
