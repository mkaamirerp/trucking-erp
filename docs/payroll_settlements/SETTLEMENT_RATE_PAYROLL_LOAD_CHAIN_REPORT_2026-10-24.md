# Settlement rate — payroll / load chain (read-only report, 2026-10-24)

**Mode:** Investigation only. **No code, schema, API, or UI changes.**

**Authority for shapes:** SQLAlchemy models and Alembic revisions in this repo. **DB spot-check:** read-only `\d` / `information_schema` on disposable clone `tenant_flowtest_3cb8dd02` and `tenant_demo` (not used for mutation). **Note:** `tenant_demo` at Alembic head `fmp02_fmp_tenant_scope` still has **legacy B7** `pay_run_items` (no `payees` table); application code targets **B8-style** models — see §1 drift callout.

---

## 1. Load → trip → driver → payee → pay run (tables and keys)

### 1.1 Operational / commercial path (load execution)

| Step | Table | Key columns | FK / link |
|------|--------|-------------|-----------|
| Commercial row | `loads` | `id`, `tenant_id`, `rate`, `customer_rate` | `loads.driver_id` → `drivers.id` (**legacy** load-level assignment; Issue 0A freeze — not primary Trip path) |
| Trip container | `trips` | `id`, `tenant_id`, `driver_id`, `trip_number`, `status` | `trips.driver_id` → `drivers.id` |
| Membership | `trip_loads` | `trip_id`, `load_id`, `tenant_id`, `status_within_trip`, `completed_at`, `removed_at` | `(tenant_id, load_id)` → `loads`; `trip_id` → `trips` |
| Person (people-first) | `drivers` | `id`, `tenant_id`, `person_id`, `payee_id` | `(tenant_id, person_id)` → `people`; `payee_id` → `payees.id` (nullable until wired) |

**Where is a driver linked to a load today?**

1. **Preferred (Trip):** `trip_loads.load_id` + `trips.driver_id` on the trip that owns the membership (`app/models/trip.py` `Trip` / `TripLoad`).
2. **Legacy:** `loads.driver_id` (`app/models/load.py:57`) — still used by some summaries (e.g. driver week revenue).
3. **Payroll path does not join loads at all** except optional **metadata** on pay run items (see §2).

There is **no FK** from `pay_entries`, `pay_run_items`, or `pay_runs` to `loads` or `trip_loads`.

### 1.2 Payroll path (as implemented in code)

| Table | Role | Links |
|-------|------|--------|
| `pay_periods` | Calendar window | `tenant_id` |
| `pay_entries` | Manual / imported lines per driver | `pay_period_id` → `pay_periods`; `driver_id` → `drivers`; optional `pay_profile_id` → `pay_profiles` |
| `pay_profiles` | Legacy per-driver pay type | `driver_id` → `drivers` (`app/models/payroll.py:115–140`) |
| `pay_runs` | Generated settlement run | `pay_period_id` → `pay_periods`; snapshots on finalize (`calculation_snapshot_json`) |
| `pay_run_items` | Lines on a run | `pay_run_id` → `pay_runs`; **`payee_id` → `payees`** (`app/models/payroll.py:86–112`) |
| `payees` | Settlement payee identity | `worker_type`, `payee_type` (`app/models/payee.py:44–64`) |
| `compensation_profiles` | O/O dispatch fee, gross calc | `payee_id` → `payees` (`app/models/payee.py:67–113`) |

**Chain in words:** `loads` ⇏ (no direct FK) ⇐ optional trace via `PayEntry.reference_code` → `PayRunItem.metadata_json.load_id` (`app/routers/pay_runs.py:52–84`, `235–296`).

### 1.3 Schema drift (demo / disposable clones vs code)

- **Code:** `PayRunItem` uses `payee_id`, `amount_signed`, `source_type`, `metadata_json` (`app/models/payroll.py:86–108`).
- **`tenant_demo` / `tenant_flowtest_*` (checked 2026-10-24):** `pay_run_items` still has `driver_id`, `entry_type`, `amount`, `source_entry_id` per B7 migration `alembic_tenant/versions/ed1b0b2f4d99_b7_pay_runs.py:58–82`. **`payees` table absent** on `tenant_demo`.
- **B8 migration** `b8f9cfe34f1b_b8_payroll_and_settlements.py` in repo currently ends after enum creation (no `payees` / redesigned `pay_run_items` DDL in file). Treat **models + routers** as the intended contract; **DB alignment** is a separate owner-approved migration task.

---

## 2. What payroll does with loads today

### 2.1 `app/routers/payroll.py` (pay periods, profiles, entries)

- **CRUD** for `pay_periods`, `pay_profiles`, `pay_entries`.
- **Entry types** (`app/schemas/payroll.py:11`): `MILES`, `HOURS`, `GROSS`, `ADJUSTMENT`, `DEDUCTION`.
- **Pay profile pay types** (`app/schemas/payroll.py:10`): `PER_MILE`, `HOURLY`, `PERCENTAGE`, `SALARY` with `rate_amount` / `rate_unit`.
- **Amount:** `amount` or `quantity * rate_amount` (`app/routers/payroll.py:425–427`).
- **No read of `Load.rate` or `Load.customer_rate`.** Optional `reference_code` string only (`app/routers/payroll.py:425–440`).

### 2.2 `app/routers/pay_runs.py` (generate / finalize)

- **Generate:** copies active `pay_entries` → `pay_run_items`; amount from entry; **`source_type` fixed to `EARNING`** for all generated lines (`app/routers/pay_runs.py:256–298`).
- **Load linkage:** if `reference_code` is all digits and matches a `loads.id`, enriches `metadata_json` with `load_id`, `trip_number`, `dispatch_trip_id` (`app/routers/pay_runs.py:235–296`). **Does not read load money fields.**
- **Finalize:** stores aggregate totals in `pay_runs.calculation_snapshot_json` (`app/routers/pay_runs.py:337–346`). **No per-load rate snapshot.**

### 2.3 `GET /payroll/loads/{load_id}/settlement`

- Returns `pay_run_items` where `metadata_json @> {"load_id": N}` (`app/routers/pay_runs.py:463–533`).
- Sums **posted line amounts**, not `loads.rate` / `customer_rate`.

**Answer:** **No pay is computed from `Load.rate` or `Load.customer_rate` in current payroll routers.** Settlement is entry-driven; load money is display/commercial only unless operators manually enter GROSS lines.

---

## 3. Driver classification and rate types

### 3.1 Onboarding / people (`driver_person_extensions`)

| Field | Allowed values | Source |
|-------|----------------|--------|
| `employment_relationship_type` | `company_driver`, `owner_operator` | `app/schemas/driver_person_extension.py:14` |
| `driver_operating_subtype` | `long_haul`, `city_local`, `shunt_yard` | `app/schemas/driver_person_extension.py:15` |
| `team_role_type` | `primary`, `co_driver` | `app/schemas/driver_person_extension.py:16` |
| `equipment_contribution_type` | `company_equipment`, `driver_truck_only`, `driver_truck_and_trailer`, `unspecified` | `app/schemas/driver_person_extension.py:17–18` |

**Beyond company driver / owner operator:** `WorkerType` on payees includes `EMPLOYEE_DRIVER`, `CONTRACTOR_COMPANY_DRIVER`, `OWNER_OPERATOR_LEASED_ON`, `THIRD_PARTY_CARRIER` (`app/models/enums.py:6–10`). UI compensation card exposes subset of `GrossCalcType` (`app/schemas/driver_compensation_setup.py:13–20`).

### 3.2 Gross calc types (`GrossCalcType`)

`CPM`, `PERCENT_REVENUE`, `FLAT_PER_LOAD`, `HOURLY`, `SALARY`, `HYBRID` (`app/models/enums.py:68–74`). Stored on `compensation_profiles.gross_calc_type`.

### 3.3 Legacy `pay_profiles.pay_type`

String: `per_mile`, `hourly`, `percentage`, `salary` (`app/models/payroll.py:124–126`) — parallel to older payroll entry workflow.

### 3.4 `dispatch_fee_basis`

- **Column:** `compensation_profiles.dispatch_fee_basis` — `Text`, default **`GROSS`** (`app/models/payee.py:94`).
- **Write path:** free string, default/strip to `GROSS` (`app/services/driver_compensation_setup.py:109`, `125`).
- **No enum or runtime calculator** in repo interprets non-`GROSS` values today. **`GROSS` is intended** to mean owner-operator settlement gross (per owner decision: sum of effective settlement rates), but **no code applies dispatch fee to load rates yet.**

---

## 4. Deductions (fuel, tolls, ELD, other) vs pay run

| Domain | Tables / fields | Links to driver / payee / pay run | Applied at pay-run generate? |
|--------|-----------------|-----------------------------------|------------------------------|
| **Payroll entries** | `pay_entries` `entry_type=DEDUCTION` | `driver_id` | Yes — copied as positive `amount_signed` lines if entered (`generate_pay_run`) |
| **Pay run items** | `pay_run_items` `source_type` | `payee_id` | Deductions only if created as items (generate sets all to `EARNING` today) |
| **Fuel** | `fuel_transactions` — `settlement_deduction_candidate`, `settlement_deduction_basis_amount`, `settlement_ref`, `owner_operator_payee_id` | Payee on transaction (`app/models/fuel.py` ~307–322) | **No** — Fuel marks candidates; [`PAYROLL_OO_FUEL_SETTLEMENT_LINKAGE.md`](./PAYROLL_OO_FUEL_SETTLEMENT_LINKAGE.md) defers assignment to future Settlement |
| **Tolls** | `toll_*` tables | Operational / review; no `pay_run_id` FK found in models | **No** automatic pay-run deduction |
| **ELD** | No dedicated settlement deduction table in tenant models | — | **No** |
| **Escrow** | `escrow_accounts`, `escrow_ledger_entries.pay_run_id` | `payee_id` | Optional link on ledger entry; not wired in `generate_pay_run` |
| **Charge rules** | `comp_profile_charge_rules` + `charge_categories` | `compensation_profile_id` | **No** auto-rollup into pay run in current generate path |

---

## 5. Readers of `Load.rate` / `customer_rate` in money sums

| Location | Field used | Should use (per owner decision) |
|----------|------------|----------------------------------|
| `app/routers/dashboard.py:84` | `sum(Load.rate)` week revenue | **Broker rate** (company gross) ✓ |
| `app/routers/drivers.py:293` | `sum(Load.rate)` driver week “revenue” | **Broker rate today** — for **company driver** reporting may stay broker; for **O/O driver gross** should become **effective settlement rate** when driver is owner-operator |
| `app/services/trips.py:382–383` | exposes `rate`, `customer_rate` on trip read-model | **Display:** broker + settlement; **no sum** |
| `apps/web` Trip / dispatch / workspace | display both fields | Relabel `customer_rate` in UI when implemented |
| Payroll / pay runs | none | Settlement engine should use **effective settlement rate** per load when auto-building GROSS lines |

**No `sum(customer_rate)`** in backend found. Parser/lab may compare both (`app/services/load_lab_review.py:304–310`).

---

## 6. Two drivers, two trips (yard / handoff) — model + settlement sketch

**Model allows:**

- Multiple `trip_loads` rows per `load_id` over time if prior memberships are **completed** or **removed** (`completed_at` / `removed_at`; partial uniques in `app/models/trip.py:93–120`).
- At most **one open `active`** membership per load (`uq_trip_loads_one_open_active_per_load`).
- Each `trips` row has one `driver_id` (handoff = **new trip**, new driver).

**Settlement (report only, not implemented):**

- Owner decision ties settlement to **effective settlement rate per load** — **one load row, one broker rate, one optional settlement rate**; it does **not** split settlement across drivers automatically.
- A handoff likely needs either: (a) **manual** settlement rate / pay entries per driver-leg, (b) **future** leg-level settlement snapshot, or (c) business rule that only the **delivering** trip’s driver earns the load gross. **Not encoded in schema today.**

---

## 7. Where a settlement snapshot could live (options)

### Option A — Columns on `pay_run_items` (or parallel `pay_run_load_snapshots`)

- At finalize (or generate), for each load-attributed line store: `load_id`, `broker_rate_snapshot`, `settlement_rate_snapshot`, `effective_settlement_rate_snapshot`, `dispatch_fee_snapshot`, currency.
- **Pros:** Simple queries per pay run; aligns with existing `metadata_json` tracing.
- **Risks:** Wide rows; easy to duplicate load-level truth; must not update when load changes post-finalize.
- **Contract change:** Owner-approved migration + finalize behavior; extend `PayRunItem` / metadata contract.

### Option B — Child table `pay_run_load_settlement_snapshots` (1:N load × pay run)

- Immutable rows keyed `(tenant_id, pay_run_id, load_id)` with money snapshots and optional `trip_id` / `driver_id` leg.
- **Pros:** Normalized; supports **multi-driver** legs later; clear immutability boundary.
- **Risks:** More joins; backfill for historical runs; RBAC on regeneration.
- **Contract change:** New table + finalize pipeline; settlement report module reads only snapshots.

**Shared requirement:** Finalized runs must read **snapshots only**, never live `loads.rate` / `customer_rate` (`SETTLEMENT_RATE_OWNER_DECISION_2026-10-24.md` §8).

---

**STOP** — awaiting owner review on GitHub (`gpt-review`).
