# Dispatch trip number — locked operational rule (baseline)

This document is **product + engineering baseline**. Trip numbers are **not** display-only labels; they are **stable, system-assigned operational identifiers** created whenever dispatch assigns work.

**Implementation:** [`DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md`](./DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md) (schema, API, services, UI, payroll/issue tracing).

## Business intent: trip number as shared operational reference

Trip number is **not only** a dispatch-assignment identifier. It is the **shared operational reference** for the assigned work across **related workflows**—the main **human-durable handle** for “this piece of work we put on the road.”

**Business meaning:** When dispatch assigns a job and the system creates a trip number (e.g. `IKL10001`), that value should become the **primary colloquial reference** people use to talk about that assignment: operations, drivers, safety, billing-related ops, etc.

**Example:** If a driver says “my trip `IKL10001` has an issue,” operations should be able to **find that exact assignment and related context quickly**—not only on the dispatch board, but wherever the product surfaces that work.

**Trip number should help connect (cross-module):**

- Dispatch assignment / `dispatch_trips` record  
- Underlying **load** or **trailer move**  
- **Assigned driver** and **truck / trailer**  
- **Route / stops** for that movement  
- **Trip issues, notes, exceptions**  
- **Documents** tied to that trip  
- **Settlement / payroll** references **where relevant**—as part of tracing **what work was done** and **what pay belongs to that work**

**Important distinctions:**

| Concept | Role |
|---------|------|
| **Load number** | Broker / commercial / intake reference — **not** the same as trip number |
| **Trip number** | **Operational movement identifier** for the dispatch-assigned work unit |
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

1. **Creation trigger:** Any time **dispatch assigns a job**, a **trip number must be created** at that moment (same transaction as the assignment becoming effective).
2. **Scope:** Applies to **normal dispatched freight loads** and **trailer moves** (non-freight dispatch work). Both use the **same numbering pool** for a tenant (see [Same trip-number pool](#same-trip-number-pool-freight--trailer-moves)).
3. **Pre-dispatch:** A **load** (or future trailer-move draft) may exist **without** a trip number while it is **not** dispatch-assigned. Once dispatch assigns it, **trip number is mandatory** and must be present before the assignment is considered committed.
4. **Format:** Fixed **tenant prefix** + **auto numeric** suffix, e.g. `IKL10001`. No spaces. Canonical storage is the **full string** (`trip_number`).
5. **Prefix:** Configured **once** in **admin** (tenant operational settings). After lock, **it does not change** (no in-app edit path; support/data repair only if ever required).
6. **Numeric portion:** Generated **only** by the **backend** inside the tenant DB transaction that performs assignment. The frontend **never** chooses or increments sequence values.
7. **Stability:** After assignment, `trip_number` is **immutable** (no user rename, no regeneration). Corrections are **exception/support** processes, not normal product flows.

## Owning entity

**Canonical owner:** a dedicated tenant row representing the **dispatched trip** (recommended table name: **`dispatch_trips`**).

- One row is created **when dispatch assignment is committed** (see [Allocation timing](#allocation-timing)).
- The row **holds** `trip_number` and links to exactly **one** operational target via **either** `load_id` **or** `trailer_move_id` — [exactly one target](#1-exactly-one-assignment-target-schema--design-rule).

**Why not only `loads.trip_number`?** A single **`dispatch_trips`** table keeps **one sequence**, one uniqueness story, and one API shape for **both** loads and trailer moves. Optional denormalized columns on `loads` / `trailer_moves` are **read-model / convenience only**; **`dispatch_trips` remains the only source of truth** — application code must not treat load-level `trip_number` as authoritative or patch it independently (see implementation plan).

**Interim phase (until `trailer_moves` exists):** Backend allocates trip numbers for freight loads by creating `dispatch_trips` with `job_type = freight_load` and `load_id` set. Trailer moves **must** follow the same allocator and format when their entity ships.

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

- **Trip numbers are never re-used.** Once issued, that string remains tied to that `dispatch_trips.id` for the tenant forever. Sequence only moves **forward**. Gaps in the numeric sequence (e.g. after cancelled commits) are **acceptable**.

## 3. Allocation timing

**Locked timing — generation happens only when:**

- Dispatch **assignment is committed** in the backend (DB transaction that persists “this job is assigned by dispatch” and triggers trip creation + sequence bump).

**Locked business event (TruckERP v1 — freight loads):**  
“Dispatch assigns the job” means the load **first enters `dispatched` status**. That transition is the **birth** of the trip number (`dispatch_trips` insert + allocation). Setting resources or moving to **`assigned`** alone is **not** dispatch commit in v1 and **does not** allocate a trip number. *(If the business ever redefines commit as `assigned`, that must be an explicit product change to this baseline—not an ad hoc code tweak.)*

**Trailer moves (future):** Mirror the same idea: trip number is created when the trailer-move job enters its **committed assigned/dispatched state** (status name aligned with freight when that module ships).

**Trip numbers must not be allocated:**

- On **draft load creation**, email/intake draft, or any pre-dispatch stage.
- On **pre-assignment** placeholders (e.g. “saved” truck/driver picks that are not yet committed dispatch).
- In the **frontend** or via any client-supplied value.

If a request would commit assignment without a trip allocation path, the transaction **must fail** (and must not partially persist assignment without `dispatch_trips` + `trip_number`).

## 4. Missing prefix behavior

If the tenant admin has **not** configured and **locked** the trip-number prefix (or numbering row is incomplete):

- **Dispatch assignment is blocked.**
- API returns a **clear, actionable error** (e.g. HTTP **409 Conflict** or **422 Unprocessable Entity**) with a **stable machine-readable code** (e.g. `TRIP_NUMBER_PREFIX_NOT_CONFIGURED`) and a short message directing admins to operational/dispatch settings.
- **No** silent fallback prefix and **no** assignment without `trip_number`.

## Same trip-number pool (freight + trailer moves)

**Locked business rule:** Freight assignments and trailer moves draw from the **same** `next_numeric` sequence and the **same** `prefix || numeric` format. Trailer-move implementation may land later; when it does, it **must not** introduce a separate pool, prefix, or format.

## Uniqueness scope

- **`trip_number` is unique per tenant:** `UNIQUE (tenant_id, trip_number)` on **`dispatch_trips`** (authoritative).
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
- Inside the **same DB transaction** as creating **`dispatch_trips`**:
  1. `SELECT … FROM tenant_dispatch_numbering WHERE tenant_id = :tid FOR UPDATE` (row lock).
  2. Assert prefix is present and locked; otherwise raise [missing prefix](#4-missing-prefix-behavior).
  3. Read `next_numeric`, form `trip_number = prefix || str(next_numeric)` (zero-pad width per policy, e.g. 5 digits).
  4. `UPDATE … SET next_numeric = next_numeric + 1 WHERE tenant_id = :tid`.
  5. `INSERT INTO dispatch_trips (tenant_id, trip_number, …)`  
     If insert hits **unique violation**, abort; do not “reuse” numbers.

**Padding / width:** Fixed digit count for numeric segment (e.g. 5 digits → `10001`). Document in code constants; overflow handling (widen string or bump width) is a **future migration**, not silent truncation.

## Schema (target)

| Object | Purpose |
|--------|---------|
| `tenant_dispatch_numbering` | `trip_number_prefix`, `prefix_locked_at`, `next_numeric` (and optional audit columns) |
| `dispatch_trips` | `id`, `tenant_id`, `trip_number`, `job_type`, `load_id` nullable, `trailer_move_id` nullable, lifecycle `status` if needed, `assigned_at`, FKs, `UNIQUE (tenant_id, trip_number)`, **exactly-one-target `CHECK`** |
| `loads` | May expose `trip_number` via join to active `dispatch_trips`; optional cached column only if kept consistent |
| `trailer_moves` | Future; links to `dispatch_trips` as above |

## API (target)

| Area | Behavior |
|------|-----------|
| **Admin / settings** | `GET`/`PUT` prefix (PUT allowed only until `prefix_locked_at` is set); **no** sequence exposure |
| **Dispatch assign** | Allocate trip only on **committed** assignment txn; return `trip_number` on relevant DTOs |
| **Reads** | Load / board / trailer payloads include **`trip_number`** when an active (or requested) trip applies |
| **Search / filter** | List and search endpoints support filtering by **`trip_number`** (exact and/or normalized prefix+number per API design); document in OpenAPI |
| **Writes** | **No** public endpoint to set or change `trip_number` after assignment |

## UI and operational surfaces (implementation)

When implementation starts, **`trip_number`** must appear in at least:

| Surface | Expectation |
|---------|-------------|
| **Dispatch board / assignment views** | Visible for assigned jobs; consistent with API |
| **Load detail** | Where dispatch context is shown |
| **Trip detail / movement detail** | Dedicated trip or trailer-move views show the canonical **`trip_number`** |
| **Admin setup** | Prefix configuration and lock; link or message when assignment is blocked |
| **Search / filters** | User can find loads/trips by **`trip_number`** where the product exposes search |
| **Issue / exception workflows** | Trips, loads, and driver-reported issues tie back to **`trip_number`** for fast lookup |
| **Settlement / payroll reference points** | Pay lines, exports, or support views include **`trip_number`** **where relevant** for tracing work → pay (without making trip number the sole owner of payroll logic) |
| **Printed or driver-facing outputs** | Rate cons summaries, trip sheets, driver comms — use **`trip_number`** as the internal operational id **where applicable**; keep **`load_number`** for broker/carrier reference when distinct |

## Compliance checklist for future PRs

- [ ] **`dispatch_trips`** is canonical; **`CHECK`** enforces exactly one of `load_id` / `trailer_move_id`.
- [ ] Assignment lifecycle matches [§2](#2-assignment-lifecycle): no number reuse; cancel keeps rows; resource-only reassignment does not mint new trip.
- [ ] Allocation only on **committed** dispatch assignment — not draft, not placeholder, not frontend ([§3](#3-allocation-timing)).
- [ ] Missing locked prefix → **blocked** dispatch + **clear admin-setup error** ([§4](#4-missing-prefix-behavior)).
- [ ] **`UNIQUE (tenant_id, trip_number)`** enforced; sequence **never** driven from client.
- [ ] Freight and trailer moves share **one** pool and format ([Same trip-number pool](#same-trip-number-pool-freight--trailer-moves)).
- [ ] Surfaces include board, detail, trip/movement detail, search/filter contracts, and operational outputs ([UI and operational surfaces](#ui-and-operational-surfaces-implementation)).
- [ ] **Cross-module tracing:** `trip_number` is visible and searchable per [Business intent](#business-intent-trip-number-as-shared-operational-reference) (issues/exceptions, documents, settlement/payroll tracing as applicable).
