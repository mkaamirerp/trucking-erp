# Phase 3A — First Implementation Slice (Report)

**Status:** Implementation slice (Alembic + model + API + tests). **No UI** in this slice.

## Final decisions (open items from schema lock — locked here)

1. **`insurance_commercial_approved`** — `NOT NULL` with database default **`false`**. “Not cleared” until explicitly set to approved in product workflows; no nullable tri-state in v1.

2. **`team_role_type` requiredness** — When **`is_team_driver` is `true`**, **`team_role_type` is required** and must be **`primary`** or **`co_driver`**. When **`is_team_driver` is `false`**, **`team_role_type` must be omitted or `null`** (stored as SQL `NULL`).

3. **Equipment alignment matrix** — Enforced on create/update:
   - **`company_equipment`** → `provides_own_truck = false`, `provides_own_trailer = false`
   - **`driver_truck_only`** → `provides_own_truck = true`, `provides_own_trailer = false`
   - **`driver_truck_and_trailer`** → `provides_own_truck = true`, `provides_own_trailer = true`
   - **`unspecified`** → no boolean constraint (escape hatch)

4. **Final table name** — **`driver_person_extensions`**

5. **FK / on-delete** — Composite **`FOREIGN KEY (tenant_id, person_id) REFERENCES people (tenant_id, id) ON DELETE CASCADE`**, matching **`driver_profiles`** / **`person_roles`** composite pattern.

---

## Files touched (see git for authoritative list)

- `alembic_tenant/versions/<rev>_driver_person_extensions.py` — tenant migration  
- `app/models/driver_person_extension.py` — SQLAlchemy model  
- `app/models/person.py` — optional `driver_person_extension` relationship  
- `app/models/__init__.py` — import new model  
- `app/schemas/driver_person_extension.py` — Pydantic read/write + validation  
- `app/routers/driver_person_extension.py` — admin GET/PUT  
- `app/main.py` — register router  
- `tests/test_driver_person_extension.py` — API + validation tests  
- This report  

---

## API contract (summary)

| Method | Path | Auth | Behavior |
|--------|------|------|----------|
| `GET` | `/api/v1/driver-person-extensions/{person_id}` | Tenant + tenant admin | Returns extension row or **404** if none |
| `PUT` | `/api/v1/driver-person-extensions/{person_id}` | Tenant + tenant admin | Upserts extension for person; **404** if person not in tenant |

**Base path:** `/api/v1/driver-person-extensions`  
**Guards:** `require_tenant`, `get_current_user`, `is_tenant_admin`, `require_entitlement("admin_sensitive")` (aligned with other admin routes).

---

## Migration summary

- **One new table:** `driver_person_extensions`  
- **Unique:** `(tenant_id, person_id)`  
- **FK:** to `people(tenant_id, id)` **ON DELETE CASCADE**  
- **No** other tables; **no** asset or payee FKs  

---

## Test results

**Host (no tenant DB URL):**  
`ENVIRONMENT=test DATABASE_URL=postgresql://… pytest tests/test_driver_person_extension.py -v`  

- **6 passed** — `TestDriverPersonExtensionWriteValidation` (Pydantic rules, no DB).  
- **8 skipped** — integration tests (`TestDriverPersonExtensionAPI`, `TestDriverPersonExtensionUniqueness`) require **`DATABASE_URL`** (platform) **and** **`ALEMBIC_TENANT_DATABASE_URL` or `TENANT_DATABASE_URL`** (tenant), with a reachable Postgres host (e.g. run from an environment that resolves the DB hostname, or the Docker stack network).

Integration tests additionally require an active **platform subscription** for the demo workspace (entitlement `admin_sensitive`), same as other admin routes.

---

## What remains (later UI slice)

- Admin UI forms for the eight fields  
- Optional: seed extension on driver approval (out of scope unless requested)  
- Product workflow for `insurance_commercial_approved` beyond boolean  

---

**Stop before UI** per slice scope.
