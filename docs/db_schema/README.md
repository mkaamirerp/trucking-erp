# Database schema snapshots

**Status:** Generated live-database evidence only — **not an architecture or migration source of truth**.

This folder is the output location for `scripts/export_schema_docs.sh`.

The previously committed snapshots dated `2026-04-13` were removed because both `trucking_erp__schema.md` and `tenant_demo__schema.md` contained only the `alembic_version` table. That export was incomplete and could mislead maintainers about the real TruckERP schema.

## Source of truth

Use, in this order:

1. Current Alembic migrations (`alembic_platform/` and `alembic_tenant/`).
2. Current SQLAlchemy models / application contracts.
3. A live database inspected at the migration revision actually deployed.
4. Files in this folder only as a generated convenience snapshot from that live database.

A generated schema file must never be used to override current migrations or code.

## Expected generated files

A valid export normally produces:

- `trucking_erp__schema.md` — platform / control-plane database.
- `tenant_demo__schema.md` — canonical demo tenant business database.

These files may be absent when no verified current export has been committed.

## Regenerate

Run from the TruckERP host while the intended Postgres container and fully migrated databases are running:

```bash
cd /home/admin/trucking_erp
PG_CONTAINER=truckerp-postgres bash scripts/export_schema_docs.sh
```

## Acceptance check before committing generated output

Do **not** commit the generated files merely because the script completed successfully.

Verify at minimum:

- both expected databases were queried;
- each database contains substantially more than only `alembic_version`;
- the reported tables match the current platform/tenant migration families;
- the generation timestamp and Postgres container are correct;
- unexpected missing tables are investigated before the snapshot is accepted.

If either database exports only `alembic_version`, treat the export as **invalid** and do not commit it.

## Related

- `docs/DATABASES_PLATFORM_AND_DEMO.md` — database ownership / platform-vs-tenant explanation; verify dated operational details against current code before relying on counts or revision numbers.
- `scripts/export_schema_docs.sh` — snapshot generator. Audit the generator separately from the generated documentation.
