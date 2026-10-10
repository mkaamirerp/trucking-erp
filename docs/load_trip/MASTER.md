# TruckERP Load / Trip Master Architecture

**Status:** CANONICAL ARCHITECTURE LOCK — **SOLE** Load / Trip / TripLoad / Dispatch / Custody authority

## Authority rule

This file is the **only** canonical architecture **and** remediation/work-order document for Load / Trip / TripLoad / Dispatch / Custody / Trip Container / Load–Trip planning / legacy retirement.

Before changing related code, schema, APIs, UI, migrations, or business rules, agents **must read this file first**.

If any other documentation conflicts with this master:

**STOP.**

Do **not** choose whichever document appears newer or says "LOCKED."

**Report the conflict.**

The master remains authoritative until an **owner-approved decision** explicitly updates **this** master.

A new decision / phase / index / tracker document does **not** silently supersede this master and must not be reintroduced as a second Load/Trip authority.

After an approved architecture change:

1. update **this** master,
2. then implement.

**Required-read scope:** Load, Trip, TripLoad, Dispatch, Trip Container, Load Workspace, Trip Workspace, assignment, `Load.status`, `Trip.status`, trip number, `dispatch_trips`, `active_trip_id`, custody, terminal/yard, handoff, recovery/repower, LTL, operational board/planning queue, payroll/read-model dependencies involving Load/Trip.

**Synthesis note:** This master consolidates previously separate Decision / Phase / index / foundation / remediation documents. Implementation status requires **code / test / migration evidence**, not the existence of prose alone.

---

# IMPLEMENTATION STATUS / WORK ORDER

Status vocabulary:

| Mark | Meaning |
|------|---------|
| ✅ DONE / SHIPPED | Implemented in code with confirming tests/evidence; no further work for that item |
| ✅ CODE COMPLETE / REVIEW ACCEPTED — NOT DEPLOYED | Accepted on `main` with regression tests; production deploy + live verification still pending |
| ☑ AUDIT / DESIGN COMPLETE | Investigation/design/reconciliation complete; implementation or migration still pending |
| ⬜ NOT IMPLEMENTED | Approved rule exists; code/work still needed |
| ⚠ OWNER DECISION REQUIRED | Unsafe to implement until owner decides |
| 🚫 BLOCKED | Prerequisite prevents work |

**Do not mark ✅ because a document was written.**

| Order | ID | Work item | Status | Evidence / current state | Next action |
|------:|----|-----------|--------|--------------------------|-------------|
| 1 | DOC-1 | One-master Load/Trip documentation consolidation | ✅ DONE / SHIPPED | Sole authority at `docs/load_trip/MASTER.md`; competing Decision/Phase/index/foundation/remediation MDs retired; docs tree reorganized by module | Maintain master + module tree |
| 2 | DOC-2 | AGENTS.md + Cursor read-before-write enforcement | ✅ DONE / SHIPPED | Already on `main` in `cc1a1f1` (`AGENTS.md` Load/Trip section; `.cursor/rules/load-trip-master-architecture.mdc`). Working-tree pointer refinements (sole-authority wording; trip-container rule retarget) ride with DOC-1 commit | Keep pointers current |
| 3 | 0A | Freeze legacy Load / Dispatch writers | ✅ DONE / SHIPPED | Independently accepted review commit `26621fe2e0c9c843f18f5b820c0cfc663c178c23` (`review/load-issue0a`; acceptance recorded in former integrity §16 / commit `53e81b0`). Same freeze patch is on `main` as `7fbd69c2eec3fee384676886cd8c675fe7773933` (identical `git patch-id`; 26621fe is not an ancestor of current HEAD). Tests: `tests/test_load_writer_freeze_issue0a.py`; `apps/web/src/loadWorkspace/loadWriterFreeze.test.ts`. Rejects legacy ops status + Load assignment; removes Assign strip / `?dispatchAssign=1`. **Issue 4** (legacy Load assignment executable) closed by same freeze | No further 0A work; do not reopen writers |
| 4 | 26 | Money mutation vs audit atomicity | ✅ CODE COMPLETE / REVIEW ACCEPTED — NOT DEPLOYED | Independent review accepted. Commits `ede7ba80d0154f39db5a4f23813b7eaceae99030` (implementation), `e7ab68ddbea4106aca891455a7b094ebb5277ae3` (flush-path regression). Load `rate`/`customer_rate` PATCH + required `load_updated` audit = **one transaction**; failed required audit rolls back money, `concurrency_version`, and audit work; money audit uses exact **decimal strings**; targeted `await db.refresh(load)` replaces `expire_all()`; non-money best-effort audit unchanged. **11** targeted tests passed (`tests/test_load_money_audit_atomicity_issue26.py` + `tests/test_load_audit_events_unittest.py`). **Production deploy + verification pending** — not marked shipped live | Deploy via `reload_api.sh` + verify money PATCH/audit on running API |
| 5 | 0B-AUDIT | Trip.status contamination audit (`active` / `open`, mirrors) | ☑ AUDIT / DESIGN COMPLETE | Issue 0B investigation completed; mapping proposal only | Owner approve migration mapping |
| 6 | 0B-MIG | Historical Trip.status / mirror data migration | ⬜ NOT IMPLEMENTED | No approved migration run; historical findings remain open | 🚫 until owner approves 0B mapping (Issue 26 code prerequisite met on `main`) |
| 7 | 0C-AUDIT | Legacy operator surface retirement map | ☑ AUDIT / DESIGN COMPLETE | Issue 0C map delivered; historical findings remain open for reference | Reference only |
| 8 | 0C-IMPL | Retire `/dispatch` as ops authority; Trip-first nav/readers | ⬜ NOT IMPLEMENTED | **On hold by owner decision.** Slice 1 (F1/F2 nav → Trip Container) shipped separately; broader 0C UI retirement not active | No further 0C implementation until owner lifts hold |
| 9 | 0D | Legacy mirror / backfill safety (`dispatch_trips`, Load.trip_number, active_dispatch_trip_id, payroll readers) | ⬜ NOT IMPLEMENTED | Mirrors still consumed (e.g. pay_runs meta); no tenant-safe cleanup approved | Audit readers → read-only → remove only after proof |
| 10 | I1 | New-write `Load.status` commercial boundary | ✅ DONE / SHIPPED | Covered by accepted 0A (`26621fe…` / mainline `7fbd69c…`): create=`draft`; writable PATCH statuses `draft`/`ready`; legacy ops rejected | Watch for residual holes only |
| 11 | I3 | Mark Ready bypass / draft→ready authority | ⬜ NOT IMPLEMENTED | **Proposed next backend integrity finding** for investigation (not started, not implemented). Still listed open after 0A; generic draft/ready PATCH authority needs product gates | Investigate Mark Ready bypass contract before implementation |
| 12 | I12 | TripLoad planned membership requires Load `ready` (unless approved exception) | ⬜ NOT IMPLEMENTED | Integrity Phase 1 item; planned membership insert does not currently require ready | Gate membership create |
| 13 | I2 | Full stop replacement destroys stop/action/history | ⬜ NOT IMPLEMENTED | Integrity Issue 2 | Safer stop persistence |
| 14 | I5 | Hard DELETE unsafe for commercial/history Loads | ⬜ NOT IMPLEMENTED | Integrity Issue 5 | Soft-cancel / block policy |
| 15 | I9 | Load audit trail incomplete | ⬜ NOT IMPLEMENTED | Integrity Issue 9 | Expand audit events |
| 16 | I10 | Unknown `Load.status` → Ready on legacy board | ⬜ NOT IMPLEMENTED | `list_loads_for_board` unknown→ready confirmed | Explicit unknown bucket |
| 17 | I13 | Planned Trip discoverability from Load (`active_trip_id` gap) | ⬜ NOT IMPLEMENTED | Create Planned Trip gated on ACTIVE-only mirror | Open-planned discovery API + UI |
| 18 | I14 | Custody → Trip close operator workflow | ⬜ NOT IMPLEMENTED | Backend complete/custody slices exist; product wiring incomplete | Wire correct operator path |
| 19 | I15 | Block silent assignment swap on `in_progress` | ⬜ NOT IMPLEMENTED | Decision 13 / integrity Issue 15 | Enforce immutability + recovery path |
| 20 | I16 | Decision 10 future-assignment conflict guard | ⬜ NOT IMPLEMENTED | Columns + schedule PATCH exist (`planned_start_at` / `expected_completion_at`); assignment overlap guard not enforced | Implement conflict check on assign |
| 21 | I17 | Current/open TripLoad row selection contract | ⬜ NOT IMPLEMENTED | Integrity Issue 17 | Safe current-row lookups |
| 22 | I6 | Rate Confirmation evidence/classification gate | ☑ AUDIT / DESIGN COMPLETE | Agriculture classified as model quality (gpt-4o-mini); not hydration corruption | Parser quality track (not Trip ops) |
| 23 | I7 | Raw PDF overwrites Internal Notes | ⬜ NOT IMPLEMENTED | Integrity Issue 7 | Separate evidence vs notes |
| 24 | I11 | Parse context API drift | ⬜ NOT IMPLEMENTED | Integrity Issue 11 | Contract cleanup |
| 25 | I8 | Load money float at API/parser boundary | ⬜ NOT IMPLEMENTED | DB NUMERIC; Pydantic/parser still float | Decimal end-to-end |
| 26 | I18–I22 | Parser hydration / stop coercion / field contract / exclusion / inbox hydration | ⬜ NOT IMPLEMENTED | Integrity Phase 3 new issues | Parser/intake slices |
| 27 | PKG | Driver dispatch package (former Decision 8) | ⚠ OWNER DECISION REQUIRED | Schema still **DRAFT / NOT LOCKED** | Owner lock package before build |
| 28 | UI-SALVAGE | DeprecatedDispatch visual salvage vs Trip Container parity | ⬜ NOT IMPLEMENTED | Routes still split; 000/001 rules absorbed below | Product UI iteration under Trip Container |

**Exact next executable item:** **Issue 26 production deploy + verification** (code complete on `main`, not deployed). Then owner approval for **0B migration mapping**. **Issue 3 (Mark Ready bypass)** is the proposed next **backend integrity investigation** — do not start without explicit approval. **0C UI retirement** remains on hold by owner decision. **0B** / **0D** historical findings stay open.

---

## 1. Four truths

| Truth | Role |
|-------|------|
| **LOAD** | Commercial / broker / customer / revenue truth |
| **TRIP** | Operational / movement / payable execution truth |
| **TRIPLOAD** | Explicit membership between Load and Trip |
| **CUSTODY / AUDIT** | Continuity of physical responsibility, location, handoff, and transfer |

These are **separate but reconcilable** truths.

**Never** duplicate a commercial Load merely because the freight moves across multiple Trips.

**Future reservation ≠ current custody ≠ execution eligibility.**

---

## 2. Load ownership


**Implementation state:** ✅ new-write commercial statuses enforced (0A). Legacy ops statuses readable. ⬜ I3 Mark Ready gates; ⬜ I10 board unknown bucket.
### Load owns

- broker / customer relationship
- broker load / reference identifiers
- rate / revenue
- rate confirmation and commercial documents
- commodity / weight
- contractual pickup / delivery obligations
- commercial notes
- commercial cancellation
- other broker / customer facts

### Target new-write `Load.status`

| Value | Meaning |
|-------|---------|
| **`draft`** | Incomplete / unverified commercial Load |
| **`ready`** | Commercially verified enough for **dispatch planning** |
| **`cancelled`** | Commercial Load itself is cancelled / no longer worked |

**`Load.status` is NOT the execution ladder.**

### Legacy `Load.status` values (historical / read compatibility only)

May exist on historical rows and compatibility read paths:

- `unassigned`
- `assigned`
- `dispatched`
- `arrived_pickup`
- `in_transit`
- `arrived_delivery`
- `delivered`
- `issue_hold`

They **must not** be used for **new** operational execution truth.

**`Load.status = dispatched`** is **not** a new execution trigger.

Commercial Load cancel (`Load.status = cancelled`) is **not** the same as `Trip.status = cancelled`. Trip cancel while Load remains valid must **not** auto-force Load cancelled without explicit product rules.

Primary detail: `load_trip/MASTER.md`.

---

## 3. Trip ownership


**Implementation state:** ✅ planned/assigned/in_progress/completed APIs shipped. ⬜ full product completion/custody UX (I14).
### Trip owns

- trip number
- driver assignment
- truck assignment
- trailer assignment
- movement / execution lifecycle
- operational responsibility
- execution timing
- operational completion / cancellation

### Canonical `Trip.status`

```
planned → assigned → in_progress → completed
cancelled  (terminal negative state)
```

| Value | Meaning |
|-------|---------|
| **`planned`** | Trip exists; resources not yet committed |
| **`assigned`** | Driver / truck / trailer committed; not necessarily moving |
| **`in_progress`** | First real execution signal occurred |
| **`completed`** | This Trip’s operational responsibility is finished |
| **`cancelled`** | Trip cancelled; record and trip number remain for audit |

**Assignment alone does NOT mean `in_progress`.**

**`Trip.status = completed` does NOT mean Load delivered.**

### Do NOT use as canonical Trip header lifecycle

- `dispatched`
- `in_transit`
- `at_pickup`
- `at_delivery`
- `delivered`
- `problem_hold`
- `open`
- `active`

Granular road / stop / facility / problem conditions belong in **stop-level status**, **timeline**, or **custody** — **not** as Trip header replacements for the ladder above.

Legacy rows may still contain invalid header values (e.g. historical `active` / `open` contamination from mirror writers). Those are **data/remediation** concerns, not the target product vocabulary.

Primary detail: `load_trip/MASTER.md` §4.

---

## 4. TripLoad membership

TripLoad (`trip_loads`) is the **membership bridge**.

- One Trip may carry **multiple** Loads.
- One Load may participate in **multiple** Trips over its lifecycle.

### Canonical membership meanings (`status_within_trip`)

| Value | Meaning |
|-------|---------|
| **`planned`** | Future reservation / planned membership |
| **`active`** | Current movement responsibility |
| **`completed`** | That Trip’s responsibility for that Load completed normally |
| **`removed`** | Membership removed / replanned / cancelled from that Trip |

### Open vs active

**Open membership:**

```text
status_within_trip IN ('planned', 'active')
AND completed_at IS NULL
AND removed_at IS NULL
```

**Active membership:**

```text
status_within_trip = 'active'
AND completed_at IS NULL
AND removed_at IS NULL
```

**Open is NOT the same as active.**

### V1 cardinality per Load

- maximum **one** open **active** membership
- maximum **one** open **planned** membership
- unlimited completed / removed history

**Valid:** active Trip A + planned Trip B.

**Invalid:** two open active memberships; two open planned memberships.

Completing A does **NOT** automatically activate B.

### V1 cardinality per Trip

A Trip **may** simultaneously have **many** ACTIVE TripLoad memberships (many Loads on one movement). This is required for LTL consolidation (see §13C).

The one-ACTIVE-per-**Load** constraint is unchanged.

### Completion vs removal timestamps

- **completed:** set `completed_at`; do **not** misuse `removed_at`
- **removed:** set `removed_at`; do **not** misuse `completed_at`

Do not confuse `trip_loads.status_within_trip = removed` with `Load.status = cancelled`.

Primary detail: Appendix B; §13D; §13B.

---

## 5. `loads.active_trip_id`

**Lock:**

`loads.active_trip_id` is a **backend compatibility / read convenience mirror** of the Load’s **CURRENT ACTIVE Trip only**.

It is **NOT**:

- TripLoad source of truth
- a planned Trip pointer
- an arbitrary open-membership pointer
- something the frontend may write or “repair”

**TripLoad membership is authoritative.**

A Load may have:

- active Trip A, **and**
- planned Trip B,

while `active_trip_id` points **only** to A.

Older docs that treated `active_trip_id` as “any open membership” or as live operational authority **conflict with this master** — see §18.

---

## 6. `dispatch_trips`

**Current target role:**

`dispatch_trips` is **legacy / compatibility / migration infrastructure**.

It is **not** the authority for **new** Trip execution.

**New Load writes must not mint execution by:**

```text
Load.status = dispatched  →  dispatch_trips
```

Canonical new operational work uses:

- Trip
- TripLoad
- Trip assignment
- Trip execution APIs
- Custody / events

Legacy rows, read paths, and backfill evidence may remain until migration is proven safe.

**Do not** delete `dispatch_trips` or compatibility mirrors merely because they are no longer new-write authority.

Payroll / reporting / read-model dependencies must be audited first (see §16).

Primary detail: Appendix A; §6; work order 0A–0D.

---

## 7. Trip number

**Lock:**

- Trip number belongs to the **Trip container**.
- Trip number is minted when the **planned Trip is created**, according to the current allocator contract.
- It is **never reused**.
- Cancelling a Trip does **not** release / reuse its number.
- One Trip has **one** operational trip number regardless of number of member Loads / stops.
- Assignment is **optional** at plan time (Trip may exist before driver / truck / trailer).
- A planned Trip may temporarily have **zero** active TripLoad memberships (scheduling / planning shell). Empty planned, cancelled, or abandoned Trips remain audit rows; the number stays tied to that `trips.id`.

Stop-level fields (pickup number, PO, appointment, facility) are **not** trip numbers.

Legacy `dispatch_trips` allocation on `Load.status = dispatched` is **historical compatibility only**.

Primary detail: Appendix A.

---

## 8. Workspace / UI authority

### Load Workspace (`LoadWorkspacePage`)

Owns:

- commercial Load creation
- commercial editing
- PDF / Rate Confirmation verification
- Save Draft
- Mark / Save Ready
- commercial Load facts

**Must not own new operational:**

- driver assignment
- truck assignment
- trailer assignment
- Trip execution progression

### Trip Workspace / Trip Container

Owns:

- operational Trip authority
- Trip membership
- driver / truck / trailer assignment
- start execution
- completion / cancellation
- operational context

**Locked product identity:** Trip = Trip Container = Dispatch Control Center — one Trip-backed operational world. Operator language may say “Dispatch”; backend may say “Trip.” That must **not** imply a second lifecycle from `Load.status` lanes.

### Legacy `/dispatch` board

`DeprecatedDispatchPage` / `/dispatch` is **compatibility / visual salvage** during retirement — **not** current operational authority.

Do **not** build a second Load page pretending to be Trip execution.

Do **not** revive `Load.status = dispatched` as a new writer.

Do **not** write `dispatch_trips` from **new Trip** flows.

Primary detail: Appendix J (UI); §2 / Issue 0A–0C work order.

---

## 9. Planning queue vs operational board

### Load planning queue

Based on **commercial Load readiness**.

- Ready Loads not yet committed to current execution
- Used for: planning, combining, splitting, holding, adding to new/existing Trip

**Save Ready** (without a Trip action) does **not** by itself: create Trip, assign equipment, send package, start `in_progress`, set `Load.status = dispatched`, start custody, or start payroll.

### Trip operational board / container

Based on **`Trip.status`**:

`planned` | `assigned` | `in_progress` | `completed` | `cancelled`

Used for: operational assignment, movement, execution, completion, exceptions.

### Legacy board

Legacy `/dispatch` Load.status board is **compatibility / read-only during retirement** and must **not** be treated as current operational authority.

### Needs Next Trip / At Yard (future planning / custody view)

Loads that are **not** finally delivered and sit at a yard / terminal awaiting another Trip should be visible for next-leg planning.

Row concepts (product, not locked UI layout):

- Load identity / broker
- current custody location (yard / terminal)
- contractual final receiver / destination (from the commercial Load — **not** rewritten to the yard)
- equipment / commodity needs as available
- ready-for-next-Trip posture

Current origin / location comes from **custody**; final destination comes from the **original Load contract**.

Primary detail: Appendix H; §12 / §13A / §13C.

---

## 10. Driver / truck / trailer


**Implementation state:** ✅ Trip assignment API. ⬜ Decision 10 conflict guard on assign (I16). ⬜ in_progress immutability (I15).
**Current / new operational assignment authority lives on Trip.**

Legacy `Load.driver_id` / `Load.truck_id` / `Load.trailer_id` may remain **readable** as historical compatibility snapshots.

- Do **not** create new Load-level operational assignment.
- Do **not** remove historical snapshots until readers / payroll / history are migrated.
- Do **not** silently sync Trip assignment back onto Load assignment fields as the default.

### Future assignment while another Trip is `in_progress`

A driver / truck / trailer may have a **future assigned** Trip while currently executing another Trip with status **`in_progress`**.

This is **allowed** for advance planning.

**However:** the next Trip’s planned start must **not** overlap impossibly with the current `in_progress` Trip’s expected completion.

Locked schedule bound field names (Decision 10):

| Field | Meaning |
|-------|---------|
| **`planned_start_at`** | Next / candidate Trip’s planned operational start |
| **`expected_completion_at`** | Current `in_progress` Trip’s expected finish |

**If both bounds exist** and:

```text
next.planned_start_at < current.expected_completion_at
```

then this is a **scheduling conflict**.

- Do **NOT** silently allow impossible schedules.
- If one or both schedule bounds are **missing**: do **NOT** invent dates; do **NOT** silently hard-block assignment solely because data is missing. Missing scheduling data may be surfaced as incomplete / warning according to later UI policy.

This guard applies **separately** to:

- driver
- truck
- trailer

**Assignment still does NOT:**

- start execution
- start custody
- trigger payroll
- set `Load.status = dispatched`
- rewrite board state

Supervisor override / exact UX remains detailed Decision 10 implementation policy unless already locked elsewhere.

Primary detail: Appendix B / G; Decision 10 rules in §10.

---

## 11. Completion / delivery

**Lock:**

- **Trip completion ≠ Load delivery.**
- A Trip may complete while the Load remains commercially active if responsibility is transferred through an **explicit** custody / handoff path.
- A Load may continue through another Trip.
- Load final delivery and receiver proof are **separate** from Trip header completion.
- Do **not** introduce `Trip.status = delivered`.

Custody event type `delivered` (receiver / proof) may exist and is **not** the Trip header state.

Primary detail: Appendix C / E; §11.

---

## 11A. Operational continuity — partial delivery / rejection / yard return

Do **not** reintroduce an obsolete Load operational status ladder. These are continuity rules only.

### Partial delivery

A Load may have some contractual obligations / stops completed while others remain outstanding.

Do **NOT** create another commercial Load merely because only part of the work remains.

Remaining responsibility may continue:

- on the same Trip, or
- on a later Trip,

depending on dispatch / custody reality.

### Rejected delivery

If the receiver rejects freight:

- Load is **not** automatically commercially cancelled
- freight custody must remain **explicit**
- freight may remain with driver / trailer
- dispatcher may choose reattempt, yard / terminal return, handoff, recovery, or another approved path

Do **NOT** silently mark the Load delivered.

### Yard return

If undelivered / rejected freight returns to yard:

- commercial Load remains the **same** Load
- final delivery is still outstanding unless broker / customer obligation is actually complete
- custody moves **explicitly** to yard / terminal / trailer / staged state
- later continuation may use a **new Trip** under the same Load

### Reassignment / remaining stops

Remaining freight / stops may continue on a new Trip.

Same commercial Load persists.

Do **NOT** duplicate the commercial Load merely because execution branches.

Primary detail: multi-Trip rules in §13A; custody in §12 / Decision 12.

---

## 12. Custody / terminal / handoff


**Implementation state:** ☑ / partial custody slices. ⬜ full operator workflow (I14).
**Lock:**

- Custody is **separate** from commercial Load state and Trip header lifecycle.
- Terminal / yard must use **structured tenant-owned identity** (not free-text as the identity of “which terminal”).
- Handoff / transfer must be **auditable**.
- Trailer-to-trailer transfer must **not** be implemented as a silent `trailer_id` overwrite.
- Custody history must preserve **continuity** (append-only with void/correct patterns as locked).
- Trip must **not** close with undelivered freight unless responsibility / custody is **explicitly resolved** per locked custody rules.
- Do **not** copy every custody / stop condition into `Trip.status`.

### Yard / custody granularity

“At yard” is **too vague** as the final custody model.

Custody / location must be able to distinguish concepts such as:

- at terminal on trailer
- staged at terminal
- transfer pending
- transferred / waiting dispatch
- attached to next Trip

Exact enum names may remain implementation detail. **Master rule:** terminal / yard custody must be **more granular** than a single generic “at yard.”

### Active Trip A + planned Trip B

**ACTIVE** Trip A + **PLANNED** Trip B for the **same** Load is **valid**.

Example:

- **Trip A:** current active movement to yard
- **Trip B:** future planned movement from yard to final receiver

When Trip A completes / hands off at yard:

- custody / handoff must be **explicitly** recorded
- Trip A membership may close according to the applicable transition
- Trip B does **NOT** automatically become active

**Trip B activation is explicit.**

**Future reservation ≠ current custody ≠ execution eligibility.**

### Whole-load V1; future partial quantity

V1 may support **whole-load** custody / transfer only.

Do **not** design schema / history in a way that prevents future partial quantity / pallet / skid transfer support.

Do **NOT** implement quantity transfer now.

Primary detail: Appendix E.
---

## 13. Exception / recovery / repower

**Lock:**

- Trip exception ≠ Load cancellation.
- Preserve original Trip + trip number.
- Recovery / repower requiring another operational movement creates / uses a **separate** Trip with its **own** number and custody chain.
- Do **not** silently swap assignment on historical execution.
- Commercial Load may remain valid through recovery.
- `Load.status = cancelled` only for true commercial cancel.

Payroll guard (summary): incomplete trip responsibility → review-required posture — no silent auto full pay / auto zero as the default; recovery trip payroll separate from original. Detail remains in Decision 13.

Primary detail: `load_trip/MASTER.md`.

---

## 13A. Multi-Trip continuation / relay — LOCKED

A single commercial Load may be executed through multiple Trips.

The Load is **NOT** duplicated merely because:

- a long-haul driver hands the freight/trailer to a city driver,
- freight is staged at a company yard/terminal,
- a driver/truck breaks down,
- a repower/recovery movement is required,
- responsibility transfers to another Trip.

The commercial Load keeps its original broker/customer obligation, commercial pickup/delivery, references, documents, and revenue.

Each Trip represents only the operational responsibility assigned to that Trip/driver/truck.

### Planned relay example

**Commercial Load:** Boston → Toronto

| | |
|--|--|
| **Trip 1** | Boston → Company Yard — Long-haul Driver A / Truck A |
| **Trip 1 end** | Responsibility ends at the yard through an **explicit planned** handoff/custody transition |
| **Trip 2** | Company Yard → Toronto receiver — Day Driver B / Truck B |
| | Same Load. New Trip. New trip number. Separate TripLoad history. Separate operational/pay responsibility. |

The Load’s contractual origin/destination remains **Boston → Toronto**.

**Do NOT** rewrite the Load to Boston → Yard.

### Breakdown / repower example

**Commercial Load:** Toronto → Boston

**Trip 1 originally assigned responsibility:** Toronto → Boston — Driver A / Truck A

**Actual event:** Truck breaks down in Albany.

**Preserve Trip 1:**

- same trip number
- same Driver A / Truck A historical assignment
- original assigned Toronto → Boston responsibility remains historically visible
- actual Trip 1 responsibility ended at Albany because of the exception

**Do NOT** rewrite Trip 1 as though Driver B was always assigned.  
**Do NOT** silently change the original assigned destination from Boston to Albany.

Record **explicit custody/handoff** at Albany.

**Trip 2:** Albany → Boston — Driver B / Truck B — new Trip number — same commercial Load — new TripLoad membership.

Trip 2 becomes the current **ACTIVE** Trip when its membership becomes active.

`loads.active_trip_id` points only to the current ACTIVE Trip. It never represents both Trip 1 and Trip 2.

### Payroll / mileage responsibility

Load mileage/revenue and driver Trip mileage/pay responsibility are **separate** concepts.

**Example:** Toronto → Boston planned distance ≈ 500 miles.

If Driver A’s responsibility ends in Albany after ≈ 320 miles, do **NOT** automatically pay:

- the full 500 miles, or
- zero miles.

Trip 1 is an incomplete responsibility case and follows Decision 13 **`review_required`** / pay-review policy.

Trip 2 payroll is calculated/reviewed separately for Albany → Boston.

The settlement/payroll system must be able to trace which Trip performed which operational segment.

### Core rule

Same Load, multiple Trips when operational responsibility changes.

- Preserve the original Trip and its historical assignment.
- Record custody/handoff explicitly.
- Create the continuation/recovery Trip with a new Trip number.
- Keep operational and payroll responsibility separate by Trip.

Primary detail: Appendix E / F.

---

## 13B. Commercial Load cancel vs Trip lifecycle — LOCKED

**Commercial cancellation and operational Trip lifecycle are separate truths.**

### Load cancel ≠ Trip cancel

Cancelling a commercial Load (`Load.status = cancelled` when the broker / customer job is truly cancelled) does **NOT** automatically cancel the Trip.

- Close / remove that Load’s TripLoad membership as appropriate.
- Commercial cancel ≠ `trip_loads` `removed` alone — membership end and commercial cancel are distinct actions unless product explicitly runs both.

### Multi-load Trip — one Load cancels

If a Trip has multiple Loads and one Load cancels:

- that Load becomes commercially cancelled
- that Load’s TripLoad membership is closed / removed
- the Trip **continues** with remaining member Loads

### Only Load cancels before assignment / execution

If the only Load on a planned Trip cancels before assignment / execution:

- Load becomes commercially cancelled
- TripLoad membership is closed / removed
- Trip may remain as an **empty planned** / audit container until the dispatcher **explicitly cancels the Trip** or **adds another Load**
- trip number is **not** reused

### Only Load cancels after driver / equipment commitment or work began

If the commercial Load cancels **AFTER**:

- driver was assigned / sent
- Trip work began
- deadhead occurred
- equipment was committed
- or operational responsibility was partially performed

then:

`Load.status` may become **`cancelled`** if the broker / customer job is **truly** cancelled.

**BUT:**

Do **NOT** erase / cancel-away the operational history.

The Trip remains preserved as an operational / audit / pay record.

Dispatcher may later: cancel the Trip, complete with exception, or add another Load — **not** automatic Trip cancel.

Trip outcome may require:

- cancellation
- exception closeout
- incomplete responsibility review
- TONU review
- deadhead review
- partial driver / OO pay review
- expense recovery
- settlement review

according to policy.

Do **NOT** automatically pay full amount.  
Do **NOT** automatically pay zero.  
Do **NOT** delete the Trip.  
Do **NOT** reuse the trip number.

### Manual Trip cancel

When the dispatcher cancels the Trip:

- `Trip.status = cancelled` (with `cancelled_at` when schema supports it)
- trip number unchanged forever
- active TripLoad memberships closed / removed
- commercial Loads are **not** auto-cancelled unless a separate explicit commercial cancel runs

Primary detail: Appendix F / A; §13B.

---

## 13C. LTL consolidation / deconsolidation — LOCKED


**Implementation state:** ☑ architecture locked. ⬜ bulk membership UI/API productization.
Business / data behavior only. **Do not** treat this section as a locked UI design. Trip board / manifest presentation will be designed iteratively later.

### Architecture reminder

| Concept | Role |
|---------|------|
| **LOAD** | One independent broker / customer commercial shipment |
| **TRIP** | One driver / truck / trailer operational movement |
| **TRIPLOAD** | Membership showing which commercial Loads are carried by a Trip |
| **CUSTODY** | Where each Load is physically / responsibly located between Trips |

A commercial Load must **NOT** be merged with unrelated customer shipments simply because they share a trailer.

A Trip **MAY** carry many Loads.

A Load **MAY** participate in many Trips over time.

For normal **V1 LTL** operation, each individual Load has at most **one ACTIVE** TripLoad membership at a time.

A Trip may simultaneously have **MANY ACTIVE** TripLoad memberships.

### Canonical example — Atlanta → Toronto

There are **10 independent commercial Loads**:

| Load | Client / PO |
|------|-------------|
| L1 | Client A / PO A |
| L2 | Client B / PO B |
| L3 | Client C / PO C |
| L4 | Client D / PO D |
| L5 | Client E / PO E |
| L6 | Client F / PO F |
| L7 | Client G / PO G |
| L8 | Client H / PO H |
| L9 | Client I / PO I |
| L10 | Client J / PO J |

These remain **10 independent commercial Loads** throughout the movement.

#### Stage 1 — Atlanta local collection

Multiple local drivers collect different Loads.

Example:

| Trip | Driver | Carries |
|------|--------|---------|
| ATL-101 | Driver A | L1, L2, L3, L4 |
| ATL-102 | Driver B | L5, L6, L7 |
| ATL-103 | Driver C | L8, L9, L10 |

Rules:

- Each local Trip may carry multiple Loads.
- Each individual Load has one ACTIVE TripLoad membership while physically moving.
- No new commercial Load is created.
- Commercial revenue remains on each original Load.

When a local pickup Trip reaches Atlanta terminal:

- that Trip’s responsibility for its member Loads ends through the applicable handoff / custody transition
- TripLoad membership closes according to normal completion rules
- custody is **explicitly** recorded at Atlanta terminal
- `active_trip_id` clears unless another Trip has actually become ACTIVE
- Load is **NOT** final-delivered
- Load is **NOT** commercially cancelled

#### Stage 2 — Atlanta terminal consolidation

All 10 Loads consolidate onto one linehaul Trip.

Example:

**Trip LH-2001** — Atlanta Terminal → Toronto Terminal  
Driver: Long-haul Driver · Truck: 55 · Trailer: 13006  
Member Loads: L1…L10

When linehaul movement becomes active:

- LH-2001 has **10 ACTIVE** TripLoad memberships
- each Load has LH-2001 as its **sole ACTIVE** Trip
- `loads.active_trip_id` for each Load may point to LH-2001 as the ACTIVE-only compatibility mirror
- commercial Load identity remains unchanged
- broker / customer revenue remains unchanged and independent per Load

**Key LTL rule:** MANY LOADS → ONE TRIP. This is normal and must be fully supported.

#### Stage 3 — Toronto terminal

When LH-2001 reaches Toronto terminal and responsibility is handed off:

- LH-2001 TripLoad memberships complete according to custody / completion rules
- custody for all 10 Loads is **explicitly** recorded at Toronto terminal
- `active_trip_id` clears when there is no current ACTIVE Trip
- Trip completion does **NOT** mean member Loads are final-delivered
- the 10 commercial Loads remain independently active until their contractual delivery obligations are satisfied

#### Stage 4 — Toronto local delivery / deconsolidation

Toronto local dispatch may divide the 10 Loads among multiple local Trips.

Example:

| Trip | Driver | Carries |
|------|--------|---------|
| TOR-3001 | Driver X | L1, L2, L3, L4 |
| TOR-3002 | Driver Y | L5, L6, L7, L8, L9, L10 |

Rules:

- TOR-3001 may have 4 ACTIVE TripLoad memberships
- TOR-3002 may have 6 ACTIVE TripLoad memberships
- each individual Load still has only one ACTIVE TripLoad membership
- prior pickup and linehaul Trip history is preserved
- no commercial Loads are duplicated
- no broker / customer revenue is duplicated

Each Load reaches final delivery independently according to its own commercial obligation.

### Core LTL rules

1. Each independent customer / broker shipment remains its own commercial Load.
2. Multiple Loads may be carried simultaneously by one Trip.
3. Multiple local pickup Trips may feed different Loads into the same terminal.
4. A linehaul Trip may consolidate many Loads from terminal custody.
5. A destination terminal may later deconsolidate those Loads into multiple local-delivery Trips.
6. LTL consolidation / deconsolidation changes Trip membership and custody. It does **NOT** merge commercial Load identity.
7. A Trip may have many ACTIVE TripLoad memberships.
8. In normal V1 LTL operation, each individual Load may have at most one ACTIVE TripLoad membership at a time.
9. ACTIVE Trip A + PLANNED Trip B for the same Load remains valid where already locked (§4 / §12).
10. Completing / handoff of Trip A does **NOT** auto-activate Trip B.
11. Terminal custody must exist explicitly between movements where applicable.
12. Trip completion at a terminal does **NOT** equal Load final delivery.
13. Final delivery is evaluated independently per commercial Load.
14. Broker / customer revenue belongs to the Load, not the Trip.
15. Do **NOT** duplicate revenue merely because a Load travels across multiple Trips.
16. Do **NOT** merge multiple customer Loads into one commercial Load merely because they share a trailer.

### Normal LTL vs true freight split

**NORMAL LTL (supported by current architecture):**

10 commercial Loads → consolidated onto one Trip / trailer → later divided among different Trips.

**TRUE PARTIAL FREIGHT SPLIT (future — not V1 LTL):**

ONE commercial Load (e.g. 10 pallets) → 5 pallets simultaneously on Trip A → 5 pallets simultaneously on Trip B.

Current V1 **one-ACTIVE-TripLoad-per-Load** remains for normal LTL.

Concurrent physical splitting of **ONE** commercial Load across multiple ACTIVE Trips is a **future** quantity-allocation capability. Future architecture may require pieces / pallets / skid count / weight / quantity / unit / portion-level custody / reconciliation across active portions.

Do **NOT** implement this now.

Do **NOT** weaken the current one-ACTIVE-per-Load constraint solely for normal LTL.

### Bulk operation principle — UI not locked

Many Loads must **NOT** force many individual dispatcher workflow actions.

Operational workflows must support **bulk** Trip membership / consolidation / deconsolidation so a dispatcher can move groups of Loads onto or off a Trip without manually processing each Load as a separate dispatch job.

**Do NOT** lock the exact UI now. Do **NOT** specify final screen layout, cards, accordions, manifest design, button placement, drag/drop, or grouping visuals. Those will be iterated later.

Architecture only needs to support:

- bulk add Loads to Trip
- bulk remove / replan Loads from Trip
- manifest / read model for member Loads
- individual Load auditability underneath the bulk action

### Profit / pay traceability (LTL-compatible)

Each Load keeps its own commercial revenue (§15A).

Trip costs may be shared / allocated operationally later, but every Trip that handled a Load must remain traceable to that Load.

Example chain for L1:

```text
ATL local pickup Trip
→ Atlanta terminal custody
→ Atlanta→Toronto linehaul Trip
→ Toronto terminal custody
→ Toronto local delivery Trip
→ final delivery
```

That full chain must remain auditable.

No revenue duplication. No history overwrite. No Trip replacement.

### Acceptance scenario (canonical test target)

**GIVEN:** 10 independent commercial Loads

**WHEN:** 4 collected on ATL-101, 3 on ATL-102, 3 on ATL-103

**THEN:**

- exactly 10 commercial Loads still exist
- each moving Load has exactly one ACTIVE TripLoad
- each local Trip may contain multiple Loads

**WHEN:** all local Trips hand freight to Atlanta terminal

**THEN:**

- pickup Trip memberships close correctly
- Atlanta terminal custody exists for all 10 Loads
- none is automatically final-delivered
- none is automatically cancelled

**WHEN:** all 10 Loads activate on LH-2001 Atlanta → Toronto

**THEN:**

- LH-2001 has 10 ACTIVE TripLoad memberships
- every Load has LH-2001 as its sole ACTIVE Trip
- no commercial Load / revenue duplication occurs

**WHEN:** LH-2001 hands all 10 Loads to Toronto terminal

**THEN:**

- linehaul memberships close correctly
- Toronto terminal custody exists
- no Load is automatically final-delivered

**WHEN:** L1–L4 activate on TOR-3001 **AND** L5–L10 activate on TOR-3002

**THEN:**

- TOR-3001 has 4 ACTIVE Loads
- TOR-3002 has 6 ACTIVE Loads
- each Load has only one ACTIVE Trip
- all prior TripLoad / custody history remains preserved
- all 10 commercial Loads remain independently traceable

### Negative acceptance rules

Future implementation / tests must reject or prevent:

- same Load ACTIVE on two Trips simultaneously in normal V1 LTL flow
- Load disappearing between Trip completion and terminal custody
- final-delivering Loads merely because linehaul Trip completed
- creating replacement Loads at Toronto
- merging unrelated customer Loads because they share a trailer
- overwriting prior TripLoad history instead of preserving it
- duplicating broker / customer revenue across Trips
- auto-activating the next planned Trip after prior Trip completes

Primary cross-refs: §4–§5, §11–§13A, §15A, Appendix E / F.

---

## 13D. City Pickup / Send City Driver — LOCKED

A broker Load is **not** inherently “city” or “long-haul.” Distance does not create a second commercial Load. Driver type / pay comes from driver configuration.

**Normal assignment:** Dispatcher may assign a city, long-haul, company, owner-operator, or team driver **directly** to a Trip for the same commercial Load.

**City Pickup / Send City Driver:** Use only when the dispatcher wants a **separate pickup → yard / terminal** operational movement for the **same** commercial Load.

- Creates an operational Trip (new trip number) + TripLoad membership to that Load.
- Does **NOT** create another commercial Load unless there is a separate broker / customer contract.
- Example: Load Mississauga → Boston; City Pickup Trip Mississauga → Terminal A; later linehaul Trip Terminal A → Boston (same Load; §13A).

When the city pickup Trip completes at yard / terminal:

- Trip completes per Trip rules
- Load remains commercially active if final receiver is elsewhere
- custody / location updates to yard / terminal explicitly
- Load becomes available for the next Trip (no auto-activate of a planned next Trip)

**Do NOT** invent a separate “Create City Delivery Trip” product type merely because distance is short — use normal Trip assignment when the city driver will deliver the contractual destination.

UI for the Send City Pickup action is **not** locked here (questions such as pickup stop, drop yard/terminal, driver/equipment, planned vs assign now are product detail).

---

## 14. Load parser / intake boundary

Parser / intake **hydrates / proposes** commercial Load data.

- AI / parser output is **not** operational execution truth.
- Human review / acceptance boundary applies.
- Parser / intake must **not** automatically:
  - create Trip execution
  - assign driver / truck / trailer
  - start custody
  - start payroll
  - advance `Trip.status`
  - write `dispatch_trips`
  - set `Load.status = dispatched`

Load review remains **commercial intake**.

Primary detail: Appendix M; §14.

---

## 15. Payroll / finance compatibility

**Going forward:** Trip is operational / payable tracing truth.

**Today:** Legacy `Load.trip_number` / `active_dispatch_trip_id` / `dispatch_trips` may still be consumed by existing payroll / reporting code.

**Do NOT remove those mirrors until:**

1. exact finance / payroll readers are identified,
2. canonical Trip replacements are proven,
3. historical tracing is preserved,
4. regression tests pass.

**No silent money / history changes.**

Trip completion makes a Trip **eligible** for payroll / settlement review; it does **not** mean the driver has been paid. A single Load may produce multiple payable Trips (e.g. city pickup + linehaul).

Primary detail: Appendix L / F; Issue 0D in work order.

---

## 15A. Profit / traceability — LOCKED

One commercial Load owns the broker / customer **revenue**.

That Load may be served by **one or multiple** Trips.

TruckERP must preserve traceability from the Load to:

- every related Trip
- driver / payee settlement generated from those Trips
- fuel / toll / other allocated operating expenses where applicable
- recovery / repower Trip costs

This allows eventual calculation of:

```text
Load revenue
minus related Trip / pay / operating costs
= true load profitability
```

Do **NOT** duplicate revenue when a Load spans multiple Trips.

Do **NOT** treat each Trip as a separate broker revenue record unless there is actually a separate commercial contract.

**LTL compatibility (§13C):** ten independent Loads on one linehaul Trip keep ten independent revenue records; Trip costs may be allocated later, but each Load’s multi-Trip custody chain remains separately traceable.

Primary detail: §13C (LTL); Decision 13 payroll guards.

---

## 16. Document precedence (post-consolidation)

This master is the **sole** Load/Trip shared-architecture and remediation authority.

Narrow **parser** / **email** / **fuel** / **toll** / **general payroll module** docs may remain for their domains but **must not** redefine Load/Trip ownership, status ladders, or dispatch authority.

If a retained parser or payroll doc conflicts with this master on Load/Trip semantics: **STOP and report**.

---

## 17. Known historical conflicts (preserved without deleted files)

### A. Former Load operational status ladder

**Historical:** Draft → Ready → Assigned → Dispatched → In Transit → Delivered → Closed.

**Current:** `Load.status` = `draft` / `ready` / `cancelled` only for new writes. Execution on Trip.

### B. Former granular Trip header statuses

**Historical:** `dispatched` / `in_transit` / `at_pickup` / `at_delivery` / `delivered` / `problem_hold` as Trip.status.

**Current:** `planned` / `assigned` / `in_progress` / `completed` / `cancelled`.

### C. Former `dispatch_trips` live authority

**Historical:** Phase 1 mirror-only `trips`.

**Current:** Trip APIs own new work; `dispatch_trips` legacy compatibility (Appendix A / §6).

### D. Former Assign-on-Load-Workspace home

**Historical:** Decision 6 placed Assign / Assign & Send on Load Workspace.

**Current:** Trip Workspace owns assignment; package send remains ⚠ DRAFT (Appendix I).

### E. Former `active_trip_id` = any open membership

**Current:** ACTIVE Trip only (§5).

---

## 18. Items needing owner decision

1. Decision 8 / Appendix I package schema lock.
2. Decision 10 warn-vs-block / supervisor override UX.
3. 0B status mapping approval before migration.
4. When `/dispatch` is physically removed vs renamed.
5. Shared LTL Trip cost allocation formula.
6. True one-Load concurrent quantity split (future).
7. Assign & Send product home (Trip-only vs Load shortcut).

---

## 19. Read-before-write checklist

1. Read **this file** (work order + architecture + appendices).
2. Confirm status of the item in the work-order table.
3. If conflict or ⚠ / 🚫 — **STOP**.
4. Implement only after master updated for architecture changes.



---

# APPENDICES — Absorbed detail (former separate MDs)

Former Decision / Phase / index / foundation / remediation documents are **deleted**. Their current rules live here. Historical commit SHAs in old trackers are not re-litigated here.

---

## Appendix A — Trip number allocator (absorbed)

**Implementation state:** ✅ mint on planned `trips` create shipped; legacy `dispatch_trips` path remains for transitional/historical compatibility only.

**Rules:**

1. Format: tenant **prefix** + auto **numeric** suffix (e.g. `IKL10001`); no spaces; full string on `trips.trip_number`.
2. Backend-only mint inside tenant DB transaction; frontend never chooses sequence.
3. Table: `tenant_dispatch_numbering` — `trip_number_prefix`, `prefix_locked_at`, `next_numeric` (row lock `FOR UPDATE` on mint).
4. Missing / unlocked prefix → **fail** planned Trip create (and any path requiring a number); no silent fallback prefix.
5. One pool for freight (and future trailer moves); never a second sequence.
6. Never reuse numbers; gaps OK; cancel/abandon keeps the row.
7. Admin may set prefix until locked; then updates forbidden via API.

**Tests / proof:** `tests/test_dispatch_trip_numbers.py`; admin dispatch-numbering UI.

---

## Appendix B — Trip assignment API (absorbed Decision 14 / 3L-B)

**Implementation state:** ✅ `PUT /api/v1/trips/{id}/assignment` shipped.

**Rules:**

- Trip owns driver/truck/trailer for operational assignment.
- While Load has **active** TripLoad on a non-cancelled Trip, effective assignment is Trip’s resources.
- UI must not write/repair `loads.active_trip_id`.
- No default silent sync Trip → Load assignment fields.
- Assignment ≠ `in_progress` (see Appendix C).

**Tests / proof:** Trip assignment slice tests; TripWorkspace assignment UI.

---

## Appendix C — Active execution signal (absorbed Decision 7)

**Implementation state:** ✅ `POST /api/v1/trips/{id}/execution-signal` shipped (`assigned` → `in_progress`).

**Rules:**

- First real execution signal starts active execution — not Assign, not package send.
- Ladder: `planned` → `assigned` → `in_progress` → `completed`; `cancelled` terminal negative.
- No `Trip.status = dispatched` after `assigned`.

**Tests / proof:** `tests/test_trip_execution_signal_slice7.py`.

---

## Appendix D — Trip complete (absorbed)

**Implementation state:** ✅ `POST /api/v1/trips/{id}/complete` shipped with OPEN-membership guard.

**Rules:**

- `in_progress` → `completed` only when zero OPEN TripLoads.
- Does not mutate Load.status, auto-activate planned B, or mint `dispatch_trips`.

**Tests / proof:** `tests/test_trip_complete_slice.py`.

---

## Appendix E — Custody / terminal / yard (absorbed Decision 12 + foundation)

**Implementation state:** ☑ / partial — custody services and slices exist; full operator workflow (Issue 14) and full event allowlist expansion still open.

**Rules (canonical):**

- Structured tenant terminal identity (not free-text as identity).
- Auditable handoff/transfer; no silent `trailer_id` overwrite.
- Append-only history with void/correct patterns.
- Trip must not close with undelivered freight unless custody/handoff accounts for it.
- Granularity beyond “at yard” (on trailer / staged / transfer pending / waiting dispatch / attached to next Trip).
- V1 whole-load transfer; do not block future quantity portions.
- Candidate event types (names may adjust): `picked_up`, `arrived_terminal`, `dropped_at_terminal`, `staged_at_terminal`, `handoff`, `trailer_transfer`, `picked_up_from_terminal`, `delivered` (receiver proof — not Trip header).

**Tests / proof:** custody operational slice tests (partial coverage).

---

## Appendix F — Exception / recovery / repower (absorbed Decision 13)

**Implementation state:** ☑ design locked in master §13 / §13A / §13B; product workflow ⬜.

**Base dispatcher options:**

1. Repower / reassign to another Trip (new Trip + number)
2. Drop / handoff at terminal/safe location (custody required)
3. Return Load to Ready / Unassigned planning queue
4. Cancel Load with broker/customer (commercial cancel only)
5. Issue / Recovery Hold (visible hold; no false delivery)

**Payroll:** incomplete trip responsibility → `review_required`; no auto full/zero; recovery Trip pay separate.

**Planned handoff complete ≠ failed final-delivery assignment** (payroll block basis = trip responsibility, not final Load delivery alone).

---

## Appendix G — Future assignment conflict (absorbed Decision 10)

**Implementation state:** ☑ columns + schedule PATCH shipped; ⬜ overlap guard on assignment.

**Fields:** `trips.planned_start_at`, `trips.expected_completion_at` (trip-level; do not infer guard from LoadStop appointments).

**Conflict:** both bounds exist and `next.planned_start_at < current.expected_completion_at` for same driver/truck/trailer with current `in_progress`.

Missing bounds → do not invent dates; do not silent hard-block solely for missing data.

Supervisor override UX ⚠ until product locks warn-vs-block.

---

## Appendix H — Load Workspace actions (absorbed Decision 6 / 9)

**Implementation state:** ✅ Mark ready / commercial save paths exist; ⬜ Assign & Send package; Assign UI home is Trip Workspace (Decision 6 Load-home superseded).

| Action | Meaning |
|--------|---------|
| Save Draft | Commercial incomplete |
| Save / Mark Ready | Commercial readiness for planning queue — not execution |
| Assign | Trip commitment (Trip API) — not Load PATCH |
| Assign & Send | Composite package send — **DRAFT** (Appendix I) |

Save Ready alone must not create Trip, assign equipment, start custody, start payroll, or set `Load.status = dispatched`.

---

## Appendix I — Driver dispatch package (absorbed Decision 8 — DRAFT)

**Status:** ⚠ **DRAFT / NOT LOCKED** — design preservation only.

Package = versioned snapshot sent to driver (trip number, equipment, stops, refs, docs/instructions). Not `Trip.status`, not custody, not payroll start.

Financial visibility: broker rate hidden by default; internal vs driver-visible views; two pay branches preserved conceptually.

**Do not implement persistence until owner locks this appendix.**

---

## Appendix J — UI / Trip Container identity (absorbed 000 / 001)

**Implementation state:** ☑ product identity locked; ⬜ physical route collapse.

| Route | Page | Role |
|-------|------|------|
| `/trips/container` | TripContainerPage | Trip-backed Dispatch Control Center list |
| `/trips/:id` | TripWorkspacePage | Trip mutations |
| `/dispatch` | DeprecatedDispatchPage | Legacy Load.status board — salvage/read-only during retirement |
| `/loads`, `/loads/:id` | Load list / LoadWorkspace | Commercial / readiness / documents |

**Salvage from DeprecatedDispatchPage:** visual patterns only — not Load.status authority, not assignment writers.

**Wireframe note (001):** accordion Trip Container is a presentation contract for Trip-backed board; iterate UI without creating a second product identity.

**Classify UI changes as:** (1) visual salvage, (2) Trip read-model integration, (3) operational mutation, (4) legacy cleanup.

---

## Appendix K — Schema / DDL highlights (absorbed TRIP_FIRST / 3L-C)

**Implementation state:** ☑ core `trips` / `trip_loads` / custody tables exist; further DDL per custody expand ⬜.

- Composite tenant isolation `(tenant_id, id)` on tenant tables.
- `trips.trip_number` unique per tenant; mint at plan/create.
- `trip_loads` membership timestamps: `completed_at` vs `removed_at` distinct.
- Do not reintroduce load-first operational authority through legacy field habits.
- Prefer custody events + timeline projections before inventing full `trip_stops` CRUD.

---

## Appendix L — Payroll / pay-run tracing (absorbed PAYROLL_TRIP_TRACING)

**Implementation state:** transitional.

- Pay-run item `metadata_json` may carry `reference_code`, and optionally `load_id` / `trip_number` / `dispatch_trip_id` from Load read-model.
- Transitional rule: numeric `reference_code` → `loads.id` (interim — not final design).
- Do not assume all numeric refs are load ids.
- Intended: explicit Trip/Load links; prefer canonical `trips.trip_number`.
- **0D dependency:** do not drop Load mirrors until pay readers migrate.

---

## Appendix M — Parser / intake safety (absorbed trackers — architecture only)

**Implementation state:** parser tracks separate; architecture boundaries locked.

Parser/intake must **not** automatically: create Trip execution, assign equipment, write `dispatch_trips`, set `Load.status = dispatched`, start custody, or start payroll.

Human review/acceptance for commercial hydration. Load Lab is proving surface, not production SoR.

Duplicate / revised RC commercial handling: see commercial Load identity rules in §2; do not create stealth operational state from parse.

---

## Appendix N — Issue register (absorbed LOAD_INTEGRITY tracker)

Former `LOAD_INTEGRITY_AUDIT_AND_REMEDIATION_PLAN.md` is retired. Use the **IMPLEMENTATION STATUS / WORK ORDER** table as the living tracker.

### Original issue summaries (still applicable unless ✅ above)

| ID | Summary | Status |
|----|---------|--------|
| 0A | Freeze legacy writers | ✅ |
| 0B | Trip.status contamination | ☑ audit / ⬜ migration |
| 0C | Operator surface retirement | ☑ audit / ⬜ impl (UI retirement **on hold** by owner) |
| 0D | Mirror/backfill safety | ⬜ |
| 1 | New-write Load.status | ✅ via 0A |
| 2 | Stop replacement history loss | ⬜ |
| 3 | Mark Ready bypass | ⬜ proposed next backend integrity investigation (not started) |
| 4 | Legacy Load assignment executable | ✅ via 0A |
| 5 | Hard DELETE | ⬜ |
| 6 | RC evidence/classification | ☑ audit (Agriculture = model quality) |
| 7 | PDF → Internal Notes | ⬜ |
| 8 | Money float boundary | ⬜ |
| 9 | Audit incomplete | ⬜ |
| 10 | Unknown status → Ready | ⬜ |
| 11 | Parse context drift | ⬜ |
| 12 | TripLoad requires ready | ⬜ |
| 13 | Planned Trip discoverability | ⬜ |
| 14 | Custody→complete workflow | ⬜ |
| 15 | In-progress assignment immutability | ⬜ |
| 16 | Decision 10 conflict guard | ⬜ |
| 17 | Current TripLoad row selection | ⬜ |
| 18–22 | Parser hydration / coercion / contracts / exclusion / inbox | ⬜ |
| 26 | Commit-then-audit money failure | ✅ CODE COMPLETE / REVIEW ACCEPTED — NOT DEPLOYED |

**Issue 26 closure record (code only — not production deployed):**

1. Load `rate` / `customer_rate` PATCH and required `load_updated` audit share **one database transaction** (`app/services/loads.py` `update_load`).
2. Failed **required** audit rolls back **money mutation**, **`concurrency_version`**, and pending audit work (`write_audit_event` with `best_effort=False` + `db.rollback()`).
3. Money audit `changed_fields` use exact **decimal strings** (never floats).
4. Targeted **`await db.refresh(load)`** after CAS flush replaces session-wide `expire_all()` for accurate before/after diffs.
5. Non-money Load PATCH **best-effort** audit behavior is unchanged.
6. **11** targeted regression tests passed (Issue 26 suite + `test_load_audit_events_unittest.py`).
7. Accepted commits: `ede7ba80d0154f39db5a4f23813b7eaceae99030`, `e7ab68ddbea4106aca891455a7b094ebb5277ae3`.
8. **Production deployment and live verification remain pending** — do not treat as shipped in runtime until API reload + operator verification.

### Gates

- No 0B migration without owner-approved mapping (Issue 26 **code** accepted on `main`; deploy/verify before relying in production).
- No broad Load.status board rewrite without 0C plan execution.
- No silent money/history changes.
- No deploy/migration from documentation alone.

---

## Appendix O — Shipped Trip API surface (quick reference)

| API | Role | State |
|-----|------|-------|
| `POST /trips` | Create planned Trip + mint number | ✅ |
| TripLoad add/remove/cancel planned flows | Membership | ✅ |
| `PUT /trips/{id}/assignment` | Equipment commitment | ✅ |
| `POST /trips/{id}/execution-signal` | Start `in_progress` | ✅ |
| `POST /trips/{id}/complete` | Complete when no OPEN members | ✅ |
| Schedule bounds PATCH | `planned_start_at` / `expected_completion_at` | ✅ fields |
| Assignment conflict guard | Decision 10 | ⬜ |
| Assign & Send package | Decision 8 | ⚠ draft |

---

## Appendix P — Document retirement record

Deleted Load/Trip authority/detail MDs (content reconciled into this master):

- `DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md` … `DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md`
- `PHASE3L_A_TRIP_EXECUTION_CUSTODY_DECISION_RECORD.md` … `PHASE3L_D_OWNER_DECISION_CHECKLIST.md`
- `000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`, `001_TRIP_CONTAINER_ACCORDION_WIREFRAME.md`
- `DISPATCH_TRIP_NUMBER_RULE.md`, `DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md`
- `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`
- `TRIP_FIRST_DDL_CONTRACT.md`
- `TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md`
- `TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`, `trip-foundation.md`
- `TRIP_CONTAINER_ARCHITECTURE_GAP_REPORT.md`, `TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md`, `TRIP_CONTAINER_OPERATIONAL_RULES.md`
- `LOAD_INTEGRITY_AUDIT_AND_REMEDIATION_PLAN.md`
- `LOAD_LIFECYCLE_AND_OPERATIONAL_EVENTS_LOCK.md`
- `LOAD_PAGE_INTAKE_IMPLEMENTATION_TRACKER.md`, `LOAD_PAGE_PDF_INTAKE_CLEANUP_MAP.md`, `LOAD_DUPLICATE_REVISED_RC.md`
- `PHASE1_TRIP_FOUNDATION_PLAN.md`, `PHASE3C_PLANNED_TRIP_IMPLEMENTATION_PROPOSAL.md`, `PHASE3D_TRIP_ACTION_READ_FIRST.md`, `PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md`
- `PAYROLL_TRIP_TRACING.md` (tracing rules absorbed; payroll module docs remain)

**Retained non-master docs (not Load/Trip architecture authority):** parser/AI design (`TruckERP_Load_Rate_Confirmation_*`, `load_parser/*`, Load Lab baselines), email intake filtering, fuel/toll/payroll module docs that are not Load/Trip lifecycle masters, general blueprint pages (must defer here for Load/Trip).

