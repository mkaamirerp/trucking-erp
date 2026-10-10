# Onboarding cleanup job

Safe deletion of old OTP tokens and signup drafts in the **platform** DB. Does not touch tenant DBs.

## What gets deleted

| Target | Rule | Default retention |
|--------|------|-------------------|
| **OTP tokens** | `created_at < now_utc - OTP_RETENTION_DAYS` | 30 days |
| **Drafts** | `created_at < now_utc - DRAFT_RETENTION_DAYS` **and** `status IN ('PENDING','STALE','FAILED')` **and** `tenant_id IS NULL` | 14 days |

- **COMPLETED** drafts (tenant-linked) are **never** deleted by this job.
- Draft delete explicitly requires `tenant_id IS NULL` so no active-tenant data is removed.

## Env (override in container or cron)

| Variable | Default | Description |
|----------|---------|-------------|
| `OTP_RETENTION_DAYS` | 30 | Delete OTP tokens older than this many days |
| `DRAFT_RETENTION_DAYS` | 14 | Delete qualifying drafts older than this many days |
| `CLEANUP_DRY_RUN` | `true` | If `true`/`1`/`yes`, only log what would be deleted; no deletes. Set to `false` for real cleanup (e.g. in cron). |

## Running

### Manual (with platform DB env)

```bash
./scripts/cleanup_onboarding.sh
```

Or via the shared DB runner (same env as Alembic):

```bash
./scripts/db_run.sh "python -m app.scripts.cleanup_onboarding"
```

### Daily cron (example)

Run at 03:30 Toronto time (adjust for your timezone or use UTC).

1. Set env so real deletes run (e.g. in the crontab line or in a file sourced by cron):
   - `CLEANUP_DRY_RUN=false`
2. Add to crontab (`crontab -e` or `sudo crontab -e`):

```cron
30 3 * * * cd /home/admin/trucking_erp && CLEANUP_DRY_RUN=false ./scripts/cleanup_onboarding.sh >> /var/log/truckerp_cleanup.log 2>&1
```

If your cron runs as a user that can’t run Docker, run the script as the same user that runs the API container, or wrap in a su/sudo call.

## Batching

- OTP: batches of 5,000.
- Drafts: batches of 1,000.

Logs show per-batch and total counts. Exit code 0 on success, 1 on failure.

## Safety

- **Dry run default**: `CLEANUP_DRY_RUN` defaults to `true`, so by default nothing is deleted. Enable real deletes only where intended (e.g. cron).
- **No recent PENDING**: 14-day cutoff keeps recent signup drafts.
- **No tenant-linked drafts**: Filter includes `tenant_id IS NULL`; COMPLETED drafts are excluded by status.
- **Order**: OTP rows are deleted first; draft deletes do not cascade to OTP (OTP has `onboarding_payload_id` with ON DELETE SET NULL).
