# TruckERP — Decision 11 / Load.status target model and board migration

**Status:** **LOCKED** (target **meaning** and **migration direction**; this doc does **not** mandate immediate schema drops or board rewrites).  
**Code anchor (legacy-dispatch cutover Slice 1):** `7012f40a` — `fix(trips): block legacy load-status dispatch mint path` — generic **`Load` PATCH** cannot transition **into** **`Load.status = dispatched`** ( **`409`**, **`LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED`** ).

**Related:** `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`, `DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md`, `DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md`, `DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md` (draft), `DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md`, `DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md`, `PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md`, `PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md`, `DISPATCH_TRIP_NUMBER_RULE.md`, `DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md`.

**Context:** Slice 1 blocked **new** generic **`Load` PATCH** transitions **into** **`Load.status = dispatched`**. Old **`dispatch_trips`** and old **`Load.status`** operational values remain for **read** / **compatibility**; **new** trip execution **must not** depend on them as **writers**.

---

## Locked decision

**`Load.status` is commercial / readiness state, not trip execution state.**

---

## Target **new-write** `Load.status` values

| Value | Role |
|-------|------|
| **`draft`** | Incomplete or still under review; intake/PDF may be unverified; broker/ref or stop details may be missing; **not** ready for dispatch **planning**. |
| **`ready`** | Verified enough for **dispatch planning**; **Ready / Unassigned Load Planning Queue** (**Decision 9**); may later join new/existing trip, combine/split, or be held. |
| **`cancelled`** | **Commercial load** cancelled or no longer to be worked — **not** the same as **`Trip.status = cancelled`**. If a **trip** is cancelled but the **broker load** remains valid, **do not** automatically force **`Load.status = cancelled`**. |

---

## Meanings (detail)

### `draft`

- Load **incomplete** or **still being reviewed**.
- Intake/PDF data may be **unverified**.
- Missing broker/load reference or missing stop details **may** still exist.
- **Not** ready for dispatch planning.

### `ready`

- Load **verified enough** for dispatch planning.
- Goes to **Ready / Unassigned Load Planning Queue**.
- Can later be added to a **new** trip or an **existing** trip.
- Can be **combined** with another load or **split** into its own trip.
- Can be **held** for later planning.

### `cancelled`

- **Commercial load itself** is cancelled or **no longer** to be worked.
- **≠** **`Trip.status = cancelled`**.
- **Trip** cancelled while **load** still valid → **load** should **not** auto-**`cancelled`** without product rules.

---

## Legacy `Load.status` values (read / compatibility — not target new-write execution states)

These **may remain temporarily** for **historical** rows, **read** compatibility, **old** board display, **old** tests, **old** dashboards/reporting:

- `unassigned`
- `assigned`
- `dispatched`
- `arrived_pickup`
- `in_transit`
- `arrived_delivery`
- `delivered`
- `issue_hold`

**Important:** **`Load.status = dispatched`** **must not** be used as a **new** **execution trigger**. Slice 1 already blocks **generic PATCH** **into** **`dispatched`** with **`LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED`**.

**Operational state** belongs to:

- **`Trip.status`**
- **`TripLoad`** membership
- **Driver dispatch package** status (future)
- **Future** stop/custody/execution events

---

## `Trip.status` target (reminder)

- `planned`
- `assigned`
- `in_progress`
- `completed`
- `cancelled`

(See **Decision 7**.)

---

## Driver package status (later — conceptual)

- `not_sent`
- `sent`
- `viewed`
- `accepted`
- `outdated` / `superseded`

*(Design detail in **Decision 8** draft; not implemented in this decision.)*

---

## Future stop/custody state (later — conceptual)

- `pending`
- `en_route`
- `arrived`
- `loaded` / `unloaded`
- `delivered`
- `departed`

---

## Target board model

| Surface | Basis | Purpose |
|---------|--------|---------|
| **Load planning queue** | **Load**-based | **Ready** / **unassigned** **commercial** loads; planning, combining, splitting, holding. |
| **Trip board / workspace** | **Trip**-based | **Operational execution** — `planned`, `assigned`, `in_progress`, `completed`, `cancelled`; assignment, package state, active execution; **member load** cards/details **inside** trips. |

### Load planning queue

- Shows **ready** loads **not yet committed** to a trip.
- **Load**-based.
- Supports dispatch **planning**, **combining**, **splitting**, **holding**.

### Trip board / workspace

- **Trip**-based.
- **Owns** operational execution.
- Shows trip **assignment**, **package** state, **active execution**, **completion/cancellation**.
- May show **member load** cards/details **inside** trips.

---

## Hard boundaries — Decision 11 does **NOT** (by this doc alone)

- Remove old **`Load.status`** values from **schema** immediately
- **Drop** **`dispatch_trips`**
- **Rewrite** the dispatch **board** immediately
- Change **payroll** metadata immediately
- **Delete** old rows
- **Force** a full **data migration** in this documentation step

**Decision 11** only locks **target meaning** and **migration direction**.

---

## Exception / recovery note

Operational problems (**breakdown**, **driver unavailable**, **trailer issue**, **accident**, **border/customs**, **broker cancellation after dispatch**, **repower/reassign**, etc.) **must not** be modeled **only** as **`Load.status`**.

**Example — truck breaks down en route:**

- **Commercial load** may remain **active**.
- **Original trip** may get an **exception/issue/recovery** treatment **later** (separate future decision).
- Dispatch may **repower/reassign** to another **trip**.
- Dispatch may **return** load to **planning queue**.
- Dispatch may **`Load.status = cancelled`** only if the **commercial load** is **truly** cancelled with broker.

**Note:** **`Load.status = cancelled`** = **commercial** load no longer worked. **Trip** exceptions, **repower**, **recovery** workflows → **separate future decision**, **not** Decision 11 core.

---

## Cross-check

| Decision / slice | Alignment |
|------------------|-----------|
| **Decision 6** | **Assign** / **Assign & Send** are **explicit** actions — **not** **`Load.status = dispatched`**. |
| **Decision 7** | **Active execution** starts from **first execution signal**, **not** **`Load.status`**. |
| **Decision 9** | **Save Ready** → **Ready / Unassigned** planning queue — aligns with **`ready`** target. |
| **Decision 10** | **Future assignment** conflicts guarded at **trip/resource scheduling** layer. |
| **Slice 1 (`7012f40a`)** | Generic **PATCH** **into** **`dispatched`** **blocked**. |

---

## Implementation note

**Do not implement** full board split, payroll, or status enum contraction in **this** documentation step alone — follow phased migration after owner approval.

---

*End of Decision 11 — Load.status target model and board migration.*
