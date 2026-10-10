# Driver List: Root Cause Analysis & Prevention for New Tenants

## Executive summary

**Symptom:** Dashboard showed "6 drivers on duty" but "List could not be loaded" (or an empty list).

**Root cause:** Two things together:

1. **Strict list/summary schema** – The driver list and dashboard summary used **DriverOut**, which has strict validation (EmailStr, phone format, date rules). Any row that failed validation was **skipped** (or the whole request 500’d). The **count** query does not serialize rows, so it still returned 6; the **list** serialized each row and skipped all of them.

2. **Seed data that fails validation** – Demo/seed data used values that fail those rules (e.g. `@demo.local` for email, which Pydantic’s EmailStr rejects). So every seeded driver failed validation and the list was empty.

**Fix:** Use a **permissive list/summary schema** (DriverListOut) for list and summary only, and ensure **seed data** and any **future tenant data** use validation-safe values (e.g. `@demo.test` for email). Detail/update flows still use strict DriverOut where appropriate.

---

## 0. Where exactly the problem was (so it doesn’t happen with new tenants)

| Role | Location | What was wrong / what to do |
|------|----------|-----------------------------|
| **Strict schema on list** | `app/routers/drivers.py` – list endpoint (e.g. line ~33) | List used `DriverOut` (strict). One bad row → skip or 500. **Now:** `response_model=list[DriverListOut]` and `driver_row_to_list_out(d)` for each row. |
| **Strict schema on summary** | `app/routers/dashboard.py` – summary `drivers` (e.g. lines ~95–101) | Summary built drivers with strict validation. **Now:** `drivers_out: list[DriverListOut]` and `driver_row_to_list_out(d)` for each row. |
| **Strict schema definition** | `app/schemas/driver.py` – `DriverOut` (e.g. line ~135) | `DriverOut` uses EmailStr, phone/date validators. **Keep** for single-driver detail/update. **Do not** use for list/summary. |
| **Permissive list schema** | `app/schemas/driver.py` – `DriverListOut` (e.g. line ~154), `driver_row_to_list_out` (~173) | Use **only** for list and dashboard summary. Ensures one bad row never empties the list. |
| **Bad seed data (root cause)** | `app/routers/dashboard.py` – `DEMO_DRIVERS` (e.g. line ~119) | Emails used `@demo.local` → rejected by EmailStr. **Now:** all demo emails use `@demo.test`. Any **new** seed or default data for a tenant must use validation-safe emails/phones/dates/names (see §3.1). |
| **Existing tenant DBs** | Tenant DB `drivers` table | If a tenant was already seeded with `@demo.local`, list stays empty until fixed. **Fix:** `scripts/fix_demo_emails.sh` or SQL in §3.4. |

**For new tenants:** When adding seed data, default drivers, or sample data during provisioning, follow the rules in **§3.1** and use **DriverListOut** (or equivalent) for any bulk driver list/summary (**§3.2**). See **§3.3** for onboarding/provisioning.

---

## 1. Where the problem was (technical)

### 1.1 Two different code paths

| What you see            | Backend behavior                                                                 |
|-------------------------|------------------------------------------------------------------------------------|
| "6 drivers on duty"     | `SELECT COUNT(*) FROM drivers WHERE tenant_id = ? AND is_active = true` → 6. No per-row serialization. |
| Driver list (cards)     | For each row: `DriverOut.model_validate(driver_orm_row)`. If validation fails → row **skipped** (or 500). |

So the **count** can be 6 while the **list** is empty if every row fails `DriverOut` validation.

### 1.2 What made validation fail (per row)

- **Email:** `DriverOut` uses Pydantic `EmailStr`. Values like `user@demo.local` are rejected (`.local` is special-use). Seed data used `@demo.local` → every row failed.
- **Phone:** `DriverOut` runs `normalize_phone` (7–15 digits after stripping). Wrong length or format → validation error → row skipped.
- **Dates:** `DriverBase.v_dates` rejects future `hire_date` / `termination_date`. Bad or demo dates → row skipped.
- **termination_date + is_active:** If DB has both set, validators require inactive when terminated. Inconsistent state → row skipped.
- **Empty names:** `first_name`/`last_name` must be non-empty (`min_length=1`). Null or "" → row skipped.

So the problem was **not** schema drift (Status vs is_active). The DB and model both use `is_active`. The problem was **strict validation on list/summary output** plus **seed/data that didn’t satisfy those rules**.

### 1.3 Why "List could not be loaded" appeared

- If the API returned **500** (e.g. missing logger, or uncaught exception), the frontend showed "List could not be loaded" with the error body.
- If the API returned **200** with `drivers: []` (all rows skipped), the frontend still showed "List could not be loaded" or an empty list when it expected 6 drivers.

---

## 2. What we changed (so it doesn’t happen again)

### 2.1 Permissive schema for list/summary only

- **DriverListOut** (`app/schemas/driver.py`): Used **only** for:
  - `GET /api/v1/drivers` (list)
  - `drivers` array in `GET /api/v1/dashboard/summary`
- No EmailStr (email is `Optional[str]`).
- No phone/date validators.
- Same field set as the list UI (id, first_name, last_name, email, phone, is_active, etc.).
- **driver_row_to_list_out(d)** builds a dict from the ORM row (with existing coercion) and returns `DriverListOut.model_validate(dict)`, so we **never skip a row** in list/summary because of strict validation.

**Single-driver detail/update** still use **DriverOut** (strict) where validation is appropriate.

### 2.2 Coercion for any remaining strict use

- **_driver_attrs_to_dict** (used by DriverOut and by driver_row_to_list_out):
  - Invalid email (e.g. `.local`, no `@`) → `None`.
  - Phone with &lt; 7 or &gt; 15 digits → `None`.
  - Future dates → today.
  - Empty first/last name → `" "`.
  - termination_date set → is_active forced to False in output.

So even if something still uses DriverOut for a list path, we reduce skip/500 from bad data.

### 2.3 Seed data and DB fixes

- **DEMO_DRIVERS** in `app/routers/dashboard.py`: All emails changed from `@demo.local` to `@demo.test` so new seed runs never write invalid email.
- **Existing DB:** Script or one-off SQL to fix already-seeded tenants:  
  `UPDATE drivers SET email = REPLACE(email, '@demo.local', '@demo.test') WHERE email LIKE '%@demo.local';`
- **fix_demo_emails.sh** (optional): Runs that UPDATE for the demo tenant DB.

### 2.4 Resilience in routes

- **list_drivers:** Top-level try/except; on any error log and return `[]` (no 500).
- **dashboard summary:** Driver-fetch in try/except; on error log and return empty `drivers` (summary still returns counts).

---

## 3. Prevention for new tenants (checklist)

So that **new tenants** never hit "count &gt; 0 but list empty" or "List could not be loaded":

### 3.1 Seed / demo data

- [ ] **Email:** Do **not** use `@*.local` (e.g. `@demo.local`). Use a validation-safe domain (e.g. `@demo.test`, `@example.com`, or real domains).
- [ ] **Phone:** Use values that yield 7–15 digits after stripping (e.g. `+12125551001`, `6472419696`).
- [ ] **Names:** Never seed null or empty `first_name`/`last_name`; use at least one character or a space.
- [ ] **Dates:** Don’t seed future `hire_date`/`termination_date` if any code path uses strict date validators on that data.
- [ ] **termination_date:** If set, ensure `is_active` is false in the same row.

Apply this to:

- `DEMO_DRIVERS` (and any other seed lists) in `app/routers/dashboard.py`.
- Any tenant seeding script or migration that inserts into `drivers`.
- Any CSV/import or API that creates drivers for a new tenant.

### 3.2 Schema choice by endpoint

- [ ] **List/summary (many rows):** Use **DriverListOut** (or an equally permissive schema). Do **not** use DriverOut for list/summary so a few bad rows don’t empty the list.
- [ ] **Single-driver detail/update:** Keep using **DriverOut** (strict) so invalid data is caught where it’s created/updated.

### 3.3 New tenant onboarding / provisioning

- [ ] If you add a "default drivers" or "sample data" step for new tenants, use the same validation-safe rules as in 3.1.
- [ ] If you copy from a template tenant DB, run the same email/phone/date checks (or use DriverListOut for any bulk read of that data).

### 3.4 Optional: one-off fix for existing tenant DBs

If a tenant already has `@demo.local` (or other invalid) emails in `drivers`:

```bash
# Replace TENANT_DB with the tenant’s db_name from platform_tenants.
docker exec truckerp-postgres psql -U postgres -d TENANT_DB -c \
  "UPDATE drivers SET email = REPLACE(email, '@demo.local', '@demo.test') WHERE email LIKE '%@demo.local';"
```

Or use `scripts/fix_demo_emails.sh` for the demo tenant.

---

## 4. Quick reference

| Topic              | Location / action |
|--------------------|-------------------|
| List/summary schema| `DriverListOut` + `driver_row_to_list_out()` in `app/schemas/driver.py` |
| List endpoint      | `app/routers/drivers.py` – `list_drivers` returns `list[DriverListOut]` |
| Dashboard drivers  | `app/routers/dashboard.py` – summary `drivers` built with `driver_row_to_list_out` |
| Seed emails        | `app/routers/dashboard.py` – `DEMO_DRIVERS` use `@demo.test` |
| Fix existing DB    | `scripts/fix_demo_emails.sh` or SQL `UPDATE drivers SET email = REPLACE(...)` |
| Troubleshooting    | `docs/driver-list-troubleshooting.md` (when list is still empty) |

---

## 5. Summary

- **Problem:** List/summary used strict **DriverOut**; seed data (e.g. `@demo.local`) failed validation; every row was skipped → "6 on duty" but empty list or "List could not be loaded."
- **Fix:** Use **DriverListOut** (permissive) for list and summary only; fix seed data to validation-safe values; coerce bad data in shared helper; harden routes so they don’t 500.
- **Prevention for new tenants:** Seed and default data must use validation-safe emails/phones/dates/names; use DriverListOut (or equivalent) for any bulk driver list/summary so one bad row doesn’t empty the list.
