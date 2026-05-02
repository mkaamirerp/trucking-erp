# Dispatch trip number — locked operational rule (baseline)

This document is **product + engineering baseline**. Trip numbers are **not** display-only labels; they are **stable, system-assigned operational identifiers** tied to a **Trip container**.

**Locked evolution (2026):** Numbers are **minted when a Trip container is created/planned**, not only when a Load enters **`dispatched`**. Legacy paths that allocated via **`dispatch_trips`** on **`dispatched`** remain documented below for migration posture; **new work** aligns allocation with **`trips`** per [Trip container authority](#trip-container-authority-trips-vs-dispatch_trips).

**Implementation:** [`DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md`](./DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md) (schema, API, services, UI, payroll/issue tracing). **Phase 3C proposal:** [`PHASE3C_PLANNED_TRIP_IMPLEMENTATION_PROPOSAL.md`](./PHASE3C_PLANNED_TRIP_IMPLEMENTATION_PROPOSAL.md).

## Business intent: trip number as shared operational reference

Trip number is **not only** a dispatch-assignment identifier. It is the **shared operational reference** for the assigned work across **related workflows**—the main **human-durable handle** for “this piece of work we put on the road.”

**Business meaning:** When the system creates a planned Trip container and mints a trip number (e.g. `IKL10001`), that value should become the **primary colloquial reference** people use to talk about that movement or scheduling shell: operations, drivers, safety, billing-related ops, etc.—**including** trips that temporarily have **no** active Loads or **no** driver/truck/trailer yet.

**Example:** If a driver says “my trip `IKL10001` has an issue,” operations should be able to **find that exact assignment and related context quickly**—not only on the dispatch board, but wherever the product surfaces that work.

**Trip number should help connect (cross-module):**

- Trip container / **`trips`** row (authoritative identity for planned and active operations)  
- Dispatch assignment / **`dispatch_trips`** record **where still used** (legacy or mirrored lifecycle)  
- Underlying **load(s)** via **`trip_loads`** and/or **trailer move**  
- **Assigned driver** and **truck / trailer**  
- **Route / stops** for that movement  
- **Trip issues, notes, exceptions**  
- **Documents** tied to that trip  
- **Settlement / payroll** references **where relevant**—as part of tracing **what work was done** and **what pay belongs to that work**

**Important distinctions:**

| Concept | Role |
|---------|------|
| **Load number** | Broker / commercial / intake reference — **not** the same as trip number |
| **Trip number** | **Operational identifier** for the Trip container (planning shell through execution); **not** the broker load number |
| **Settlement / payroll** | **Not** owned solely by trip number; pay rules remain authoritative—but **trip number is a core cross-module key** for **tracing** operations → settlement / payroll |

**Design expectation for implementation:** Make `trip_number` **visible and searchable** anywhere humans need to **trace the work**, including:

- Dispatch views  
- Trip detail  
- Load detail (where dispatch context applies)  
- Issue / exception workflows  
- Settlement / payroll reference points (line-item detail, exports, support lookups—not replacing payroll’s own keys)  
- Printed / driver-facing operational outputs **where appropriate**

Together, the sections below define **(1)** technical ownership, allocation, and schema rules and **(2)** this **operational, cross-module meaning** so product and engineering stay aligned.

## Locked operational rules

1. **Creation trigger:** A **trip number is minted when a Trip container is created/planned** (same DB transaction as **`trips`** insert, using the shared allocator). It **does not** wait until a Load enters **`dispatched`**.
2. **Scope:** **All** Trip containers that receive a system trip number (planning shells, multi-load trips, trailer moves when modeled) draw from the **same numbering pool** per tenant (see [Same trip-number pool](#same-trip-number-pool-freight--trailer-moves)).
3. **Pre-assignment:** A Trip may exist **before** driver/truck/trailer assignment. A Trip may temporarily have **zero active Loads** for scheduling/planning (`trip_loads` membership absent or all closed—see product rules in [`TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`](./TRIP_CONTAINER_VS_LOAD_FOUNDATION.md)).
4. **Loads without a Trip:** A **commercial Load** may still exist **without** being on any Trip until planning/dispatch attaches it via **`trip_loads`**. **Load cancellation and Trip cancellation are separate**; closing membership or cancelling a Load **must not** automatically cancel the Trip (see foundation doc).
5. **Format:** Fixed **tenant prefix** + **auto numeric** suffix, e.g. `IKL10001`. No spaces. Canonical storage on the **Trip container** is the **full string** (`trips.trip_number`).
6. **Prefix:** Configured **once** in **admin** (tenant operational settings). After lock, **it does not change** (no in-app edit path; support/data repair only if ever required).
7. **Numeric portion:** Generated **only** by the **backend** inside the tenant DB transaction that creates the Trip (or legacy **`dispatch_trips`** path during transition). The frontend **never** chooses or increments sequence values.
8. **Stability:** After minting, `trip_number` is **immutable** (no user rename, no regeneration). Corrections are **exception/support** processes, not normal product flows.
9. **Audit:** **Cancelled, abandoned, or empty planned Trips** remain rows forever for audit; **trip numbers are never reused** (see [Trip number re-use](#trip-number-re-use)).

## Trip container authority (`trips` vs `dispatch_trips`)

**Target architecture:**

- **`trips`** is the **authoritative owner** of **`trip_number`** for the **Trip container** (planning through execution).
- **`trip_loads`** is the **authoritative membership** between Trip and Load(s).
- **`dispatch_trips`** may remain during migration as a **legacy or mirrored** row for freight flows that historically allocated on **`dispatched`**; **dual-write / alignment** is an implementation concern documented in the implementation plan. **Do not** introduce a second allocator or a second numbering pool.

**Until services fully flip:** code may still reflect **`dispatch_trips`** for some writes; the **product rule** is nonetheless: **one pool**, **mint at Trip plan/create**, **number lives on `trips`**.

## Owning entity (historical note — `dispatch_trips`)

**Legacy / transitional:** Where **`dispatch_trips`** still exists, each row **represented** a dispatched assignment and **held** `trip_number` with exactly **one** of `load_id` / `trailer_move_id` — [exactly one target](#1-exactly-one-assignment-target-schema--design-rule).

**Going forward:** **`trips.trip_number`** is the **canonical** string for the container; **`dispatch_trips`** linkage (if retained) should **reference or mirror** that identity per implementation plan—**not** mint a competing number for the same logical Trip.

**Why not only `loads.trip_number`?** Load-level **`trip_number`** (if present) is **read-model / convenience only** for search and UI; **`trips`** (and allocator) authorize identity.

## 1. Exactly one assignment target (schema + design rule)

Each `dispatch_trips` row **must** refer to **exactly one** dispatch target:

- **Either** `load_id IS NOT NULL` **or** `trailer_move_id IS NOT NULL`
- **Not both** populated.
- **Not neither** populated.

**Enforcement (required):**

- PostgreSQL **`CHECK`** constraint on `dispatch_trips`, e.g.  
  `(CASE WHEN load_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN trailer_move_id IS NOT NULL THEN 1 ELSE 0 END) = 1`
- **`job_type`** must be consistent with which FK is set (`freight_load` ↔ `load_id`, `trailer_move` ↔ `trailer_move_id`) — enforce with a second `CHECK` or a small set of allowed (`job_type`, flags) combinations.

This is a **locked design rule**, not optional validation in application code only.

## 2. Assignment lifecycle

**Container-first note:** For **new** work, operational identity is the **`trips`** row (**`trip_number`** minted at **plan/create**). The bullets below describe **historical `dispatch_trips`** behavior and **must be reconciled** during dual-write so a **single** trip identity does not receive **two** numbers ([implementation plan](./DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md) §4.1–4.2). **Manual Trip cancel** and **`trip_loads`** membership rules: [`TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`](./TRIP_CONTAINER_VS_LOAD_FOUNDATION.md) §11.1.

### One load vs many `dispatch_trips` rows over time

- A **single load** may have **multiple** `dispatch_trips` rows **over its lifetime** if the business voids or cancels a dispatch and later commits a **new** dispatch for the same load. Each such event that **allocates a new operational trip identity** creates a **new** row and a **new** `trip_number`.
- Conversely, **reassignment** that only adjusts **resources** on the same committed dispatch (e.g. change driver/truck while the same operational trip continues) **does not** allocate a new `trip_number` — it updates assignment fields on the load / move **without** creating a new `dispatch_trips` row (same trip, same number).

*Implementation note:* model **at most one active trip** per load **and**, when `trailer_moves` exists, **at most one active trip per trailer move** — same partial-unique pattern on `dispatch_trips` (`WHERE status = 'active'`); historical rows remain for audit.

### Reassignment

- **Same trip continues:** mutate `driver_id` / `truck_id` / `trailer_id` (or equivalent) on the load or trailer move; **do not** issue a new `trip_number`.
- **New operational trip** (product-defined: e.g. cancel and re-dispatch as a new leg): **new** `dispatch_trips` row + **new** number; prior row moves to **`cancelled`** / **`superseded`** (or similar), still holding its immutable `trip_number`.

### Undo / cancel assignment

- **Do not delete** `dispatch_trips` rows in normal product flows; **do not** strip or reuse `trip_number`.
- Cancelled / undone assignments keep the row for audit; **`trip_number` stays stable** on that row.
- The load may return to a pre-dispatch state without an **active** trip link; **historical** trip rows remain queryable.

### Trip number re-use

- **Trip numbers are never re-used.** Once issued, that string remains tied to **`trips.id`** (and any legacy **`dispatch_trips.id`** row that referenced the same logical trip) for the tenant forever. Sequence only moves **forward**. Gaps in the numeric sequence (e.g. after cancelled or abandoned planned trips) are **acceptable**.

## 3. Allocation timing

**Locked timing (current product):** A trip number is minted in the **same DB transaction** as **`trips`** row creation for a **planned Trip container** (scheduling shell). **No** wait for Load **`dispatched`**.

**Legacy / transitional note:** Earlier implementation tied the **first** allocation to the load entering **`dispatched`** via **`dispatch_trips`**. That timing is **superseded** for new work: **plan/create Trip → mint**. During migration, services may **align or dual-write** legacy rows per [`DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md`](./DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md)—**without** a second pool.

**Trip numbers must not be allocated:**

- On **draft load creation**, email/intake draft, or any pre-dispatch **load** stage (unless/until product explicitly attaches that load to a Trip and that attach does **not** itself mint—a **new Trip** mint still flows from **Trip create**).
- In the **frontend** or via any client-supplied value.

**Missing allocator transaction:** If prefix is not locked or numbering row is incomplete, **planned Trip create** and **dispatch paths** that require a number **must fail** with the same class of error as [§4](#4-missing-prefix-behavior).

**Cancellation:** Cancelling a **Load** or closing **`trip_loads`** membership **does not** free or recycle a trip number. **Manually cancelling a Trip** sets **`trips.status = cancelled`** and **`cancelled_at`** when available; **`trip_number` unchanged** (see foundation doc for Load vs Trip cancel).

## 4. Missing prefix behavior

If the tenant admin has **not** configured and **locked** the trip-number prefix (or numbering row is incomplete):

- **Planned Trip create is blocked** (same class of failure as dispatch).
- **Dispatch assignment** that requires a new number is blocked.
- API returns a **clear, actionable error** (e.g. HTTP **409 Conflict** or **422 Unprocessable Entity**) with a **stable machine-readable code** (e.g. `TRIP_NUMBER_PREFIX_NOT_CONFIGURED`) and a short message directing admins to operational/dispatch settings.
- **No** silent fallback prefix and **no** mint without `trip_number`.

## Same trip-number pool (freight + trailer moves)

**Locked business rule:** Freight assignments and trailer moves draw from the **same** `next_numeric` sequence and the **same** `prefix || numeric` format. Trailer-move implementation may land later; when it does, it **must not** introduce a separate pool, prefix, or format.

## Uniqueness scope

- **`trip_number` is unique per tenant on `trips`:** `UNIQUE (tenant_id, trip_number)` (**authoritative** for the container).
- Historically **`dispatch_trips`** may also enforce `UNIQUE (tenant_id, trip_number)` during migration; **must not** allow two different meanings for the same string in one tenant.
- **Not** globally unique across tenants (prefix may overlap between different companies in different tenants).
- **`load_number`** (broker / commercial reference) remains **separate** from **`trip_number`**; neither replaces the other.

## Trailer moves

- Assigning a trailer move follows the **same** rules as freight: **`dispatch_trips`**, same allocator, same format, same immutability and lifecycle rules.
- **`dispatch_trips.trailer_move_id`** links the trip to `trailer_moves` when that entity exists.

## Where the prefix is stored

**Tenant DB** (business data), not platform DB:

- Table (recommended): **`tenant_dispatch_numbering`**, **one row per tenant** (`tenant_id` primary key).
- Columns (conceptual):
  - `trip_number_prefix` — `VARCHAR`, validated (e.g. uppercase A–Z / digits, max length 8–16 per product decision).
  - `prefix_locked_at` — `TIMESTAMPTZ`, set when admin saves the prefix the first time; while NULL, prefix may be set once; once locked, **updates forbidden** via API.

## Numeric sequence — safe under concurrency

**Goal:** For a tenant, each new trip receives the **next** integer in a **single global dispatch sequence** (shared by loads and trailer moves).

**Recommended pattern (PostgreSQL, tenant DB):**

- Store **`next_numeric`** (bigint) on **`tenant_dispatch_numbering`** (or a dedicated sequence row keyed by `tenant_id`).
- Inside the **same DB transaction** as creating **`trips`** (and during transition, when still inserting **`dispatch_trips`**, same rules):
  1. `SELECT … FROM tenant_dispatch_numbering WHERE tenant_id = :tid FOR UPDATE` (row lock).
  2. Assert prefix is present and locked; otherwise raise [missing prefix](#4-missing-prefix-behavior).
  3. Read `next_numeric`, form `trip_number = prefix || str(next_numeric)` (zero-pad width per policy, e.g. 5 digits).
  4. `UPDATE … SET next_numeric = next_numeric + 1 WHERE tenant_id = :tid`.
  5. `INSERT INTO trips (tenant_id, trip_number, …)` with immutable `trip_number`.  
     If insert hits **unique violation**, abort; do not “reuse” numbers.  
     (Legacy: `INSERT INTO dispatch_trips` only as aligned by implementation plan—not a second mint for the same logical Trip.)

**Padding / width:** Fixed digit count for numeric segment (e.g. 5 digits → `10001`). Document in code constants; overflow handling (widen string or bump width) is a **future migration**, not silent truncation.

## Schema (target)

| Object | Purpose |
|--------|---------|
| `tenant_dispatch_numbering` | `trip_number_prefix`, `prefix_locked_at`, `next_numeric` (and optional audit columns) |
| `trips` | **Trip container:** `trip_number` **canonical**; `status`; nullable assignment; `cancelled_at` when schema supports it; `UNIQUE (tenant_id, trip_number)` |
| `trip_loads` | Authoritative Trip↔Load membership; partial unique active membership |
| `dispatch_trips` | **Legacy / mirrored** freight assignment row where retained; must not contradict `trips.trip_number` for the same logical trip |
| `loads` | Commercial record; optional read-model **`trip_number` / `active_dispatch_trip_id` / `active_trip_id`** only as documented |
| `trailer_moves` | Future; same pool; ties to Trip container per implementation plan |

## API (target)

| Area | Behavior |
|------|-----------|
| **Admin / settings** | `GET`/`PUT` prefix (PUT allowed only until `prefix_locked_at` is set); **no** sequence exposure |
| **Planned Trip create** | Mint `trip_number` in txn with `trips` insert; **zero active loads allowed** |
| **Dispatch assign** | Same pool; legacy paths may touch `dispatch_trips` until unified — implementation plan |
| **Reads** | Trip / load / board payloads include **`trip_number`** from **`trips`** (or derived read-model) |
| **Search / filter** | List and search support **`trip_number`**; document in OpenAPI |
| **Writes** | **No** public endpoint to set or change `trip_number` after mint |
| **Trip cancel** | `trips.status = cancelled`; **`cancelled_at`** when available; number **immutable**; close active memberships per rules |

## UI and operational surfaces (implementation)

When implementation starts, **`trip_number`** must appear in at least:

| Surface | Expectation |
|---------|-------------|
| **Dispatch board / assignment views** | Visible for assigned jobs; consistent with API |
| **Load detail** | Where dispatch context is shown |
| **Trip detail / movement detail** | Dedicated trip or trailer-move views show the canonical **`trip_number`** |
| **Admin setup** | Prefix configuration and lock; link or message when **planned Trip create** or dispatch is blocked |
| **Search / filters** | User can find loads/trips by **`trip_number`** where the product exposes search |
| **Issue / exception workflows** | Trips, loads, and driver-reported issues tie back to **`trip_number`** for fast lookup |
| **Settlement / payroll reference points** | Pay lines, exports, or support views include **`trip_number`** **where relevant** for tracing work → pay (without making trip number the sole owner of payroll logic) |
| **Printed or driver-facing outputs** | Rate cons summaries, trip sheets, driver comms — use **`trip_number`** as the internal operational id **where applicable**; keep **`load_number`** for broker/carrier reference when distinct |

## Compliance checklist for future PRs

- [ ] **`trips`** holds **canonical** `trip_number`; **`UNIQUE (tenant_id, trip_number)`**; mint on **planned Trip create** ([§3](#3-allocation-timing)).
- [ ] **`trip_loads`** is authoritative membership; **not** `loads.active_trip_id` alone.
- [ ] **`dispatch_trips`** (if still present) **does not** create duplicate identities or pools; lifecycle matches migration doc.
- [ ] No number reuse; cancel / abandon keeps rows; sequence forward-only ([§2](#2-assignment-lifecycle)).
- [ ] Missing locked prefix → **blocked** planned Trip create + dispatch + **clear admin-setup error** ([§4](#4-missing-prefix-behavior)).
- [ ] **Load cancel ≠ Trip cancel** unless explicit separate action ([`TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`](./TRIP_CONTAINER_VS_LOAD_FOUNDATION.md)).
- [ ] **Cross-module tracing:** `trip_number` visible/searchable per [Business intent](#business-intent-trip-number-as-shared-operational-reference).
