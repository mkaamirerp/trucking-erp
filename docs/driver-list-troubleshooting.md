# Driver list empty / "List could not be loaded"

> **Document type:** Operational troubleshooting — **not** the tenant migration runbook.  
> **Tenant DB schema upgrades (operators):** `scripts/tenant_upgrade_head.sh` (see `docs/secrets.md`).  
> The restart snippet below is for **picking up API code**, not for applying migrations.

## Where the problem is

**Not schema drift.** The Driver model and tenant DB both use `is_active` (Boolean); there is no "Status era" vs "is_active era" mismatch.

**Actual cause:** The driver **list** is empty because every row fails **DriverOut** validation and is skipped (or the API returns 500 before we added defensive code). The **count** (e.g. "6 drivers on duty") comes from a separate query that only counts rows; it does not serialize each driver. So you see the count but not the list.

## What can make validation fail (per row)

- **Email:** `@demo.local` or other invalid formats fail Pydantic `EmailStr`.  
  **Fix:** Coerce invalid emails to `None` in `_driver_attrs_to_dict` (output only).
- **Phone:** Values that don’t yield 7–15 digits after stripping fail `normalize_phone`.  
  **Fix:** Coerce invalid phones to `None` in `_driver_attrs_to_dict`.
- **Dates:** Future `hire_date` / `termination_date` fail `DriverBase.v_dates`.  
  **Fix:** Coerce future dates to today in `_driver_attrs_to_dict`.
- **termination_date + is_active:** DB has both set; validators require inactive when terminated.  
  **Fix:** `DriverOut` before-validator forces `is_active=False` when `termination_date` is set.
- **Empty names:** `first_name`/`last_name` empty or None fail `min_length=1`.  
  **Fix:** Coerce to `" "` in `_driver_attrs_to_dict`.

## Code that fixes it

- **app/schemas/driver.py:** `_driver_attrs_to_dict` and `DriverOut` before-validator implement the coercions above so **output** never fails validation; list/summary return all rows (with optional fields nulled when invalid).
- **app/routers/drivers.py:** Top-level try/except returns `[]` on any error so the list endpoint never 500s.
- **app/routers/dashboard.py:** Driver-fetch block in try/except returns empty list on error so summary never 500s.

## If the list is still empty

1. **Confirm API has the latest code**  
   Restart the API from the repo root (prod compose file):

   ```bash
   cd /home/admin/trucking_erp
   docker compose -f docker-compose.yml restart truckerp-api
   ```

   If code inside the image seems stale, rebuild and restart: `./scripts/reload_api.sh` or `./scripts/dev-up.sh`.

2. **Confirm DB emails**  
   Demo data should use `@demo.test`, not `@demo.local`.  
   Fix existing rows:  
   `docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "UPDATE drivers SET email = REPLACE(email, '@demo.local', '@demo.test') WHERE email LIKE '%@demo.local';"`

3. **Inspect API response**  
   Call `GET /api/v1/dashboard/summary` (with auth and tenant). Check whether `drivers` is `[]` or has items.  
   Call `GET /api/v1/drivers` (with auth and tenant). Check status and body.

4. **Check API logs**  
   Look for `list_drivers: skip driver id=...` or `Dashboard: skip driver id=...` to see which rows (if any) are still failing validation.
