# Load Integrity Audit & Issue-by-Issue Remediation Plan

**Status:** ACTIVE AUDIT / GAME-PLAN DOCUMENT — no Load fixes are authorized by this document alone.  
**Purpose:** Preserve the current Load integrity audit, cross-check it against TruckERP's locked Load/Trip/parser architecture, and provide one numbered issue register to resolve with Cursor one issue at a time. After each issue is investigated, tested, and accepted, this document must be updated before moving to the next issue. A later independent Antigravity review is the final second-opinion gate after the Load issues are closed.

**Created:** 2026-10-06  
**Scope:** Load commercial model, Load Page, Rate Confirmation intake/parser boundary, Load status/readiness, stops, assignment boundary, deletion, audit, money types, and adjacent Trip/custody integration boundaries.  
**Non-scope for this audit phase:** implementing fixes, migrations, deploys, broad Trip redesign, payroll, settlement, accounting, or changing locked architecture without an explicit owner decision.

---

## 0. Locked architecture this audit must obey

This audit was cross-checked against the current Load/Trip documentation spine and prior owner decisions.

Primary references:

- `docs/TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`
- `docs/trip-foundation.md`
- `docs/DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`
- `docs/LOAD_PAGE_INTAKE_IMPLEMENTATION_TRACKER.md`
- `docs/TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`
- `docs/CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`
- `docs/TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md`
- `docs/LOAD_PAGE_PDF_INTAKE_CLEANUP_MAP.md`

Locked rules that govern every issue below:

1. **Load = commercial / broker / customer truth.** Revenue, rate confirmation, contractual stops, documents, references, and broker/customer facts belong to the Load.
2. **Trip = operational / payable execution truth.** Driver/truck/trailer assignment, trip number, execution lifecycle, and movement belong to Trip.
3. **TripLoad = explicit Load↔Trip membership bridge.** One Trip may carry multiple Loads and one Load may move through multiple Trips. Do not duplicate a commercial Load to represent another execution segment.
4. **Custody/Audit = physical continuity truth.** Yard/terminal handoffs, transfers, custody, and history must remain auditable. No silent disappearance.
5. **Target new-write Load.status = commercial/readiness only:** `draft`, `ready`, `cancelled`. Legacy operational statuses may remain readable for old rows but are not the target for new writes.
6. **Save Draft / Save Ready are load preparation states, not execution.** Ready means available to the planning queue; it must not silently create a Trip, assignment, custody, payroll, or dispatch execution.
7. **Trip status owns execution:** `planned → assigned → in_progress → completed`, with `cancelled` as the negative terminal state.
8. **Load.status must not become the execution ladder.**
9. **Parser output is hydration/review evidence only.** PDF parsing must not automatically create trips, assign equipment, trigger payroll/custody, or become operational truth without human review/save.
10. **Canonical Load page is `LoadWorkspacePage`.** Load Lab is proving/debug/regression, not a separate production business truth.
11. **Rate Confirmation reference semantics stay distinct:** internal TruckERP `load_number` is not the broker's load identifier; `broker_load_reference` / typed references preserve broker-document meaning.
12. **Rate = linehaul/commercial rate according to the frozen parser field contract, not an arbitrary document total.**
13. **No silent money edits, no silent state changes, and no silent history deletion.**
14. **Issue-by-issue remediation only.** Investigate → report → challenge → smallest safe change → tests → review → accept → document → next issue.

---

# 1. Preserved Load audit report

The following is the complete current audit report that triggered this remediation plan.

## Overall assessment

The Load module should **not yet be called safe/Gold**. Several parts are good: tenant scoping is generally present, optimistic concurrency exists, client writes to `trip_number` / `active_trip_id` are rejected, PDF parsing does not automatically create Loads or Trips, and the Rate Confirmation parser has been consolidated onto one product path.

However, there are real logic gaps that can create invalid state or silently destroy business/execution history.

| Severity | Finding | Why it matters |
|---|---|---|
| **CRITICAL** | **Load status architecture can still be bypassed** | `LoadCreate` accepts the legacy status set. A caller can create a new Load directly as `dispatched`, `in_transit`, `delivered`, `assigned`, etc. `create_load()` inserts it without requiring a Trip. |
| **CRITICAL** | **Editing a Load can destroy stop execution history** | `update_load()` deletes every `LoadStop` and recreates them whenever `stops` is included. Stop IDs change; stop actions can cascade away; `arrived_at` / `departed_at` history is lost. The normal Load UI sends the full stop collection on Save. |
| **HIGH** | **Mark Ready gate is bypassable** | `POST /loads` can create `status="ready"` directly and generic PATCH can move draft→ready, bypassing `mark_load_ready()` checks for broker, broker reference, pickup and delivery. |
| **HIGH** | **Load Workspace still performs legacy assignment through the Load** | `LoadWorkspacePage.onDispatchAssign()` PATCHes `status:"assigned"` plus driver/truck/trailer directly onto the Load, conflicting with the Trip-first architecture. |
| **HIGH** | **Hard DELETE is unsafe for commercial truth** | `delete_load()` physically deletes the Load using only tenant/id/concurrency gate. There is no explicit status/trip/custody/history protection and no delete audit. |
| **HIGH/MEDIUM** | **Rate-confirmation parser classifies document type but does not enforce it as a hydration gate** | AI may return another document type; current mapping records `document_type` in context but still maps extracted values into the Load hydration response. |
| **MEDIUM** | **Parsing replaces Internal Notes with the entire PDF text** | `applyLoadDocumentParseResponse()` uses `res.raw_text` as `internal_notes`, mixing immutable source evidence with operator-owned notes and risking overwrite on an existing Load. |
| **MEDIUM** | **Money still crosses API/parser as float** | `rate` and `customer_rate` are `Optional[float]` at Pydantic/parser boundaries even though DB storage is NUMERIC. Load revenue feeds AR/factoring/commission/settlement later. |
| **MEDIUM** | **Load audit is incomplete** | `create_load()` discards actor/request information for its audit call; `mark_load_ready()` has no corresponding audit event; hard delete has none. |
| **MEDIUM** | **Unknown legacy status can be displayed as Ready** | `list_loads_for_board()` falls back unknown statuses into the `ready` bucket. Corrupt/unknown state must not silently look ready. |
| **LOW** | **Parse context contract has drift** | `/parse-document` accepts `email_thread_id` and `load_id`, but the orchestrator currently discards them rather than preserving/echoing them as context. |

### 1. Load status can still create fake execution

Locked architecture:

```text
Load = commercial / broker truth
Trip = operational execution truth

Target new Load.status:
draft
ready
cancelled
```

Current `app/schemas/load.py` still exposes the legacy status set to normal Load writes:

```python
DISPATCH_STATUSES = {
    "draft", "ready",
    "unassigned", "assigned", "dispatched",
    "arrived_pickup", "in_transit",
    "arrived_delivery", "delivered", "issue_hold",
}
```

`LoadCreate` inherits that status field, and `create_load()` builds the ORM row directly from the validated payload. Therefore a normal caller can create a brand-new commercial Load already marked with a legacy execution state without any Trip, TripLoad membership, custody record, or execution history.

The generic PATCH guard only specifically blocks **new transitions into `dispatched`**. It does not enforce the locked target new-write set for the other legacy operational statuses.

### 2. Stop replacement can silently destroy execution/custody history

`LoadStop` contains operational/history-bearing fields including:

```text
scheduled_at
arrived_at
departed_at
```

and owns `LoadStopAction` children such as:

```text
live_load
drop_trailer
hook_trailer
relay
yard_move
```

Current `update_load()` behavior for a payload containing `stops` is full replacement:

```text
DELETE existing LoadStop rows
→ recreate submitted LoadStop rows
```

The canonical Load Workspace normal Save builds a full persistence payload including `draftStops`, so this is not merely an exotic API path.

Risk example:

```text
Existing stop
  arrived_at = 10:15
  departed_at = 11:02
  action = drop_trailer

User edits commodity and presses Save
        ↓
frontend sends all stops
        ↓
backend deletes old stops
        ↓
stop IDs / arrival / departure / actions can disappear
        ↓
new stop rows are created
```

This violates the locked rule: **no silent disappearance of operational/custody history**.

### 3. `mark-ready` is not authoritative

`mark_load_ready()` itself has useful gates:

- current status must be `draft`
- broker or broker snapshot exists
- broker load reference exists
- at least one pickup
- at least one delivery/drop
- optimistic concurrency must match

But normal create/update contracts can write `ready` directly. Therefore these validations can be bypassed.

The desired architecture is:

```text
draft Load
→ save commercial fields
→ explicit Mark Ready gate
→ ready planning queue
```

not:

```text
generic POST/PATCH status=ready
→ bypass readiness validation
```

### 4. Load Workspace still contains executable legacy assignment

Current `LoadWorkspacePage.onDispatchAssign()` performs a direct Load PATCH conceptually equivalent to:

```typescript
{
  status: "assigned",
  driver_id,
  truck_id,
  trailer_id
}
```

The UI message itself calls this a legacy path.

This conflicts with the locked model:

```text
Load
  ↓
TripLoad membership
  ↓
Trip
  ↓
Trip assignment
```

Driver/truck/trailer assignment for new work belongs on the Trip, not as a new execution state written onto the commercial Load.

### 5. Hard DELETE is unsafe for commercial truth

Current `delete_load()` performs a physical delete guarded by tenant/id/concurrency version.

There is no explicit business protection for:

- existing TripLoad membership
- active or historical Trip linkage
- custody events/history
- accounting/revenue references
- document snapshots
- operational history
- audit preservation
- cancellation semantics

The locked architecture already distinguishes **cancellation** from record destruction. A commercial Load that has participated in execution should not silently disappear.

### 6. Rate Confirmation classification is not yet an enforcement gate

The Rate Confirmation semantic schema can classify the uploaded document. The product parser currently moves `document_type` and `classification_reasoning` into response context, but it still maps the extracted structure into `LoadDocumentParseResponse`.

Therefore classification exists, but the product path does not yet clearly prove:

```text
selected profile = Rate Confirmation
AND evidence supports Rate Confirmation
→ hydrate Load review fields
```

For a non-rate-con document, the safe behavior should be fail/review without contaminating the Load form.

This is analogous to the Toll evidence-first gate:

```text
profile selected
→ evidence check
→ parse
→ review
```

### 7. Full PDF text should not become Internal Notes

The frontend helper currently does conceptually:

```typescript
let notesBody = res.raw_text?.trim() || "";
setInternalNotes(notesBody);
```

`raw_text` is source evidence/debug material.

`internal_notes` is an operator-owned business field.

Those should not be the same storage concept.

Especially dangerous on an existing Load:

```text
dispatcher writes useful internal notes
       ↓
uploads another rate con
       ↓
parser hydration
       ↓
internal notes replaced by PDF text
```

That is a silent overwrite.

### 8. Money should eventually stop using floats

Database storage is NUMERIC, but Python/Pydantic and semantic parser boundaries currently use `Optional[float]` for `rate` and `customer_rate`.

Load revenue ultimately feeds AR, factoring, commission, profitability, and settlements. Monetary boundaries should be Decimal-safe.

### 9. Load audit is incomplete

Current audit behavior is not uniform.

Known concerns:

- create route has user/request available, but `create_load()` currently writes `load_created` with `actor_user_id=None` and `request_id=None`
- `mark_load_ready()` changes business state but does not visibly emit the same central audit event pattern
- hard delete has no durable delete/cancel audit trail in the current function
- stop full-replacement can radically change data without a detailed stop-level history

### 10. Unknown legacy status can be displayed as Ready

`list_loads_for_board()` groups known statuses, but an unknown/unrecognized status falls back into `ready`.

Unknown/corrupt state is not the same as commercial readiness. Fail closed or surface an explicit unknown bucket; do not silently promote state.

### 11. Parse context contract has drift

`POST /api/v1/loads/parse-document` accepts optional:

- `email_thread_id`
- `load_id`

The orchestrator currently discards them.

This is low severity, but it is contract drift: either preserve/echo them as safe context or remove them from the public contract when no caller needs them.

---

# 2. Cross-check against prior Load documentation and decisions

## 2.1 Status model — audit CONFIRMED by docs

The current master index and Decision 11 explicitly lock:

```text
new-write Load.status:
draft
ready
cancelled
```

Legacy values such as `assigned`, `dispatched`, `in_transit`, and `delivered` are read/compatibility state, not the target for new writes.

Therefore Finding 1 and Finding 3 are implementation gaps against an already locked decision.

## 2.2 Load vs Trip assignment — audit CONFIRMED by docs

The Trip execution/custody spine locks:

- Load = commercial truth
- Trip = execution/assignment truth
- TripLoad = membership
- new execution does not use `Load.status = dispatched`
- Trip assignment is the intended authority

Therefore Finding 4 is genuine legacy executable code.

## 2.3 Stops / custody continuity — audit CONFIRMED and more serious than old parser-stop cleanup

The older Load Page cleanup report already documented serialization/persistence of all submitted stops and identified parser stop-quality problems.

The current audit adds a more serious consequence: full replacement of existing `LoadStop` rows can collide with execution/history fields and child `LoadStopAction` rows.

The locked custody architecture says physical/history continuity must be auditable and must not silently disappear.

Therefore this must be treated as a data-integrity issue, not merely a parser cleanliness issue.

## 2.4 Parser boundary — audit CONFIRMED by parser docs

Current parser architecture already locks:

- one shared Document Parser architecture
- Rate Confirmation is an explicit profile
- parser output hydrates review/workspace fields
- parser does not create Trip/dispatch/payroll/custody state
- human verifies and saves

The docs also describe Rate Confirmation classification fields. The audit question is whether non-rate-con classification is actually enforced before hydration.

## 2.5 Raw evidence vs editable business fields — audit CONSISTENT with architecture

TruckERP's document architecture distinguishes source evidence from human-reviewed/product values. Using full `raw_text` as mutable `internal_notes` weakens that boundary.

## 2.6 Commercial money — audit CONSISTENT with finance locks

Revenue belongs to the commercial Load, and Load revenue later drives AR/factoring/profitability/commission/settlement logic. Money boundaries elsewhere in TruckERP are strict and Decimal-safe.

## 2.7 Delete vs cancel — audit CONSISTENT with continuity rules

Trip cancellation never means deleting the historical Trip. A commercial Load that has entered business/execution history should likewise not disappear silently. Exact Load cancellation/delete policy may still require an owner decision, but unrestricted hard delete deserves an explicit gate.

---

# 3. Numbered issue register — one issue at a time


## ISSUE 0 — Legacy Load/Dispatch footprint inventory and scrub gate

**Priority:** FIRST, before Issue 1.  
**Purpose:** Identify every legacy Load/dispatch writer, UI path, compatibility mirror, status surface, parser branch, board path, constant, test, script, and stale configuration so we know what must be removed, what must remain read-only for historical compatibility, and what must be archived rather than executed.

**Important:** "Scrub legacy" does **not** mean blindly deleting anything containing the word `legacy`. Some migrations, historical docs, read-side compatibility, and backfill/archaeology tools may still be required to understand or safely read old data. The target is:

```text
remove executable legacy business logic
remove legacy writers
remove legacy UI actions
remove dead feature flags / dead runtime paths
remove misleading compatibility fallbacks

but preserve only what is genuinely required for:
historical reads
database migration history
safe backfill/transition evidence
archived documentation
```

### Known live/runtime legacy footprints already visible

The initial repository scan has already found concrete runtime footprints that must be audited:

- `app/services/loads.py` still imports and uses legacy dispatch constants including `LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED`, `PRE_DISPATCH_TRIP_CANCEL_STATUSES`, and `TRIP_ALLOCATED_AT_LOAD_STATUS`.
- `app/constants/trip_dispatch.py` still carries the old load-status-driven dispatch vocabulary and compatibility constants.
- `apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx` still renders the broad legacy Load status list and special-cases `dispatched`.
- `apps/web/src/loadWorkspace/DispatchAssignmentStrip.tsx` is explicitly documented as a **Legacy dispatch context panel** and still patches Load driver/truck/trailer + status.
- `apps/web/src/pages/LoadWorkspacePage.tsx` still contains the legacy Load assignment writer.
- `app/routers/dispatch.py` + `loads_service.list_loads_for_board()` still expose the legacy load-status dispatch board.
- `DeprecatedDispatchPage` remains part of the legacy board path.
- `app/core/config.py` still contains an old `load_parse_document_semantic_adapter_enabled` flag/comment describing a legacy regex-vs-semantic cutover even though the current product parser path has moved on.
- `app/routers/load_lab.py` / Load Lab UI still expose `truckerjson` as a legacy parse contract for lab comparison. This may be intentionally lab-only and must be classified before removal.
- `app/services/trip_mirror_catchup.py` and historical Trip/dispatch mirror fields exist for migration/backfill compatibility and must not be deleted blindly.
- older Alembic migrations and archived docs contain legacy terminology; migration history must not be rewritten merely to make grep clean.

### ISSUE 0 audit questions

1. Search the entire repo, not only `app/services/loads.py`, for executable legacy Load/dispatch behavior.
2. Classify every result into exactly one bucket:
   - **REMOVE NOW — executable legacy writer/path**
   - **REPLACE NOW — live path with a Trip-first equivalent**
   - **READ-ONLY COMPATIBILITY — required to display old rows**
   - **MIGRATION/BACKFILL — required temporarily for historical data transition**
   - **LAB/TEST ONLY — intentionally isolated proving path**
   - **ARCHIVE/DOC ONLY — non-runtime**
   - **FALSE POSITIVE — word legacy but unrelated to Load**
3. Enumerate every writer to:
   - `Load.status`
   - `Load.driver_id`
   - `Load.truck_id`
   - `Load.trailer_id`
   - `Load.trip_number`
   - `Load.active_dispatch_trip_id`
   - `Load.active_trip_id`
4. Enumerate every caller of `dispatch_trips` and prove whether it is still required.
5. Enumerate every frontend route/action that opens the legacy board or legacy assignment strip.
6. Find all status dropdowns/filters/API allowlists that still expose operational Load statuses.
7. Find dead feature flags and old parser/runtime branches that are no longer authoritative.
8. Find compatibility mirrors and determine whether any current writer still treats them as authority.
9. Find tests that preserve legacy behavior and classify whether they should become historical read tests or be removed/replaced.
10. Find scripts/backfills that could still be run accidentally in production; identify which should be moved/guarded/archived.
11. Do not delete Alembic migration history.
12. Do not remove the ability to read old production rows until a deliberate data migration proves they are gone or converted.
13. Do not change code during the first audit pass.

### ISSUE 0 output

Cursor must return a table:

| Path / symbol | Current runtime? | Writes state? | Legacy purpose | Classification | Safe action | Dependency/blocker |
|---|---:|---:|---|---|---|---|

Then return a proposed **legacy removal sequence**, smallest and safest first.

### ISSUE 0 acceptance concept

Before Issue 1 begins, we have a complete map of the legacy footprint and a signed-off removal order.

The end state should be:

```text
Load runtime
  = commercial/readiness only

Trip runtime
  = assignment/execution only

Legacy Load execution
  = no live writer
  = no live UI action
  = no silent fallback
  = historical read compatibility only until data migration closes it
```

---

**Rule:** Do not fix several of these together. Cursor audits one numbered issue, returns evidence, then ChatGPT independently reviews that evidence. If anything is unclear, Cursor is sent back for a second focused audit. Only after the issue is understood do we authorize the smallest repair.

## ISSUE 1 — New-write Load.status can violate the Trip-first architecture

**Severity:** CRITICAL  
**Current concern:** `LoadCreate` and generic Load PATCH expose legacy operational statuses. Only transition into `dispatched` has a special guard.  
**Locked target:** new Load writes use `draft | ready | cancelled`; legacy execution states are read-compatibility only.

### Audit questions

1. Enumerate every code path that can INSERT or UPDATE `loads.status`.
2. Separate normal product UI/API, email intake, seed/demo, migrations, tests, admin/internal scripts.
3. Prove whether normal API can create `assigned`, `in_transit`, `delivered`, etc.
4. Prove whether generic PATCH can write each legacy value.
5. Find all frontend status selectors/writers.
6. Find tests that intentionally or accidentally normalize the bypass.
7. Identify read-side compatibility that must remain for old rows.
8. Propose the smallest enforcement boundary without deleting legacy read support.
9. Do not fix yet.

### Acceptance concept

No normal new-write product path can create a legacy execution Load status. Old rows remain readable.

---

## ISSUE 2 — Full stop replacement can destroy stop/action/history truth

**Severity:** CRITICAL  
**Current concern:** normal Save may delete and recreate all stops, losing IDs and execution/history fields.

### Audit questions

1. Prove exactly when the frontend includes `stops` in Save/PATCH.
2. Prove exact backend delete/recreate behavior.
3. Enumerate every FK/relationship referencing `load_stops.id`.
4. Check `LoadStopAction` cascade behavior.
5. Check custody/events/Trip stop references or future links to `LoadStop`.
6. Check whether `scheduled_at`, `arrived_at`, `departed_at` are user-editable or operational-only.
7. Construct a regression scenario: existing stop with arrival/departure/action → edit unrelated Load field → save → inspect history.
8. Decide whether stop IDs must become stable.
9. Distinguish commercial stop editing from execution/custody event history.
10. Do not fix until the data-loss surface is proven.

### Acceptance concept

Editing commercial Load details cannot silently erase stop execution/history. Stop changes preserve identity/history or use an explicit audited replacement model.

---

## ISSUE 3 — Mark Ready can be bypassed

**Severity:** HIGH  
**Current concern:** create/PATCH can set `ready` without `mark_load_ready()` validation.

### Audit questions

1. Enumerate all paths writing draft→ready.
2. Prove whether POST create with `status=ready` succeeds without readiness prerequisites.
3. Prove whether generic PATCH draft→ready bypasses the gate.
4. Check email-intake draft creation.
5. Check seed/demo scripts separately from product paths.
6. Check frontend Save payload status behavior.
7. Identify tests that rely on direct ready writes.
8. Propose one authoritative readiness transition.

### Acceptance concept

`mark_load_ready` or an equivalent central domain service becomes the only normal transition into `ready`.

---

## ISSUE 4 — Legacy Load assignment is still executable

**Severity:** HIGH  
**Current concern:** `LoadWorkspacePage.onDispatchAssign()` writes Load assignment/status directly.

### Audit questions

1. Identify exactly how `?dispatchAssign=1` is entered.
2. Find all callers/navigation paths from the legacy board.
3. Prove whether the UI can still execute this path in production.
4. Trace backend effects of `status="assigned"` + driver/truck/trailer.
5. Compare with `PUT /trips/{id}/assignment`.
6. Check whether Load-level driver/truck/trailer fields remain required snapshots/read models or are still treated as authority.
7. Determine the safe removal/disable/migration path.
8. Do not redesign the Trip UI inside this issue.

### Acceptance concept

New assignment goes through Trip authority. Legacy Load assignment cannot create new operational truth.

---

## ISSUE 5 — Hard DELETE can erase commercial/history truth

**Severity:** HIGH  
**Current concern:** physical delete has no clear business-state guard.

### Audit questions

1. Find every caller of DELETE `/loads/{id}`.
2. Determine whether UI exposes delete and under what states.
3. Enumerate DB relationships/cascades from Load.
4. Test deletion of untouched draft, ready Load, Load with TripLoad history, custody events, notes, customs snapshot, and intake/accounting references.
5. Determine what must block delete.
6. Determine whether untouched draft deletion is acceptable.
7. Define cancellation vs deletion semantics from existing docs; identify any remaining owner decision.
8. Require auditability.

### Acceptance concept

Historical/commercial truth cannot disappear. If deletion remains, it is restricted to a narrowly defined never-used draft case; otherwise use explicit cancellation.

---

## ISSUE 6 — Rate Confirmation evidence/classification gate

**Severity:** HIGH/MEDIUM  
**Current concern:** classification may be informational instead of a fail-closed hydration gate.

### Audit questions

1. Enumerate allowed `document_type` values in the semantic model.
2. Show behavior for rate confirmation, driver information sheet, invoice, unrelated PDF, and ambiguous/unknown document.
3. Determine whether non-rate-con output still hydrates extracted Load fields.
4. Inspect prompt/schema instructions and mechanical validation.
5. Check digital, scanned/OCR, and mixed PDF paths.
6. Check whether filename/MIME can incorrectly substitute for business evidence.
7. Define the minimum evidence gate consistent with the shared parser architecture.
8. Preserve profile-explicit architecture; do not invent global auto-routing.

### Acceptance concept

Load Rate Confirmation intake only hydrates Load review fields when Rate Confirmation evidence passes. Wrong/ambiguous documents fail closed or require explicit review without contaminating fields.

---

## ISSUE 7 — Raw PDF evidence overwrites Internal Notes

**Severity:** MEDIUM  
**Current concern:** `raw_text` is assigned to `internal_notes`.

### Audit questions

1. Prove behavior on a new Load.
2. Prove behavior on an existing Load with operator notes.
3. Check Load Lab and intake mode behavior.
4. Determine whether any tests intentionally expect raw text in notes.
5. Find the intended durable home for source PDF/raw text today.
6. Separate source evidence, extracted customs note, and operator internal notes.
7. Do not lose existing user notes during parse/hydration.

### Acceptance concept

Parsing never silently overwrites operator notes. Raw source evidence remains source evidence.

---

## ISSUE 8 — Load money boundary uses float

**Severity:** MEDIUM  
**Current concern:** `rate` and `customer_rate` are floats in API/parser schemas while DB is NUMERIC.

### Audit questions

1. Trace rate/customer_rate from OpenAI output → Pydantic → TS state → API JSON → Pydantic → SQLAlchemy NUMERIC.
2. Test decimal edge cases.
3. Check AR/factoring/commission consumers.
4. Determine one canonical decimal serialization strategy.
5. Check compatibility impact on frontend form values and existing API clients.
6. Do not combine with broader accounting redesign.

### Acceptance concept

Commercial money is Decimal-safe end to end without changing the business meaning of Rate.

---

## ISSUE 9 — Load audit trail is incomplete

**Severity:** MEDIUM  
**Current concern:** mutation audit coverage and actor/request propagation are inconsistent.

### Audit questions

1. Inventory every Load mutation endpoint/service.
2. For each, record whether audit exists, actor exists, request/correlation ID exists, before/after fields exist.
3. Confirm `create_load` loses actor/request context.
4. Confirm Mark Ready audit behavior.
5. Confirm delete/cancel audit behavior.
6. Confirm stop edits are auditable enough.
7. Check best-effort semantics and whether critical business-state audit should be stronger.
8. Do not make audit failures break unrelated operations without explicit architecture decision.

### Acceptance concept

Every important Load business mutation has attributable audit evidence with consistent actor/request correlation.

---

## ISSUE 10 — Unknown status silently maps to Ready on legacy board

**Severity:** MEDIUM  
**Current concern:** unknown state can be shown as ready.

### Audit questions

1. Prove fallback behavior.
2. Find which unknown/legacy values can reach it.
3. Check whether this can make a bad row dispatchable/plannable.
4. Decide explicit unknown/legacy bucket vs omission/error.
5. Keep read compatibility without false readiness.

### Acceptance concept

Unknown state never becomes Ready by default.

---

## ISSUE 11 — Parse context API drift

**Severity:** LOW  
**Current concern:** accepted `email_thread_id` / `load_id` values are discarded.

### Audit questions

1. Find all callers supplying either field.
2. Determine whether product needs safe echo/context correlation.
3. Check privacy/tenant implications.
4. Either preserve them intentionally in the public context contract or remove dead parameters in a version-safe way.

### Acceptance concept

Public API arguments have a truthful purpose; no misleading dead contract.

---

# 4. Additional audit challenges Cursor must try to disprove

These are not yet separate confirmed issues. Cursor's whole-module audit must explicitly test them so we do not miss a neighboring defect.

1. **Broker/contact consistency:** changing broker without changing an existing `broker_contact_id` may leave a contact attached to the old broker if the payload omits `broker_contact_id`.
2. **Load number race behavior:** service performs a pre-check for uniqueness, but DB uniqueness is the true race-safe authority. Verify concurrent duplicate creates/updates return a controlled business error rather than 500.
3. **Stop sequence integrity:** verify duplicate sequence numbers, negative sequence protection, deterministic ordering, and update behavior.
4. **Stop type integrity:** `stop_type` appears length-validated but not strongly enumerated in Pydantic. Verify arbitrary values cannot undermine readiness/parser/UI assumptions.
5. **Country/state/date normalization:** make sure parser hydration and manual writes do not create semantically incompatible values.
6. **Create audit transaction boundary:** Load is committed before audit event; verify accepted best-effort behavior and failure semantics.
7. **Mark Ready race:** prove CAS prevents double/competing transition and produces a truthful conflict snapshot.
8. **Customs snapshot concurrency:** verify snapshot insert + Load CAS rollback does not leave an orphan/duplicate snapshot.
9. **References persistence:** verify `references` replace/clear semantics cannot silently lose broker/stop references during ordinary saves.
10. **Duplicate Load detection fields:** inspect `review_required` and `is_duplicate_of_load_id` writers/readers for stale or inconsistent behavior.
11. **Tenant boundaries:** re-run cross-tenant checks on load detail, notes, parser grounding, broker/contact/customs IDs, and trip references.
12. **Parser tenant-identity exclusion failure mode:** current code can continue with an empty exclusion if platform lookup fails. Verify whether that can cause the carrier's own identity to be incorrectly extracted as broker identity.
13. **OCR/mixed-PDF behavior:** mixed digital/scanned PDFs currently block semantic parse while image-only PDFs use OCR. Verify UI handles blocked state without accidentally keeping stale values from an earlier parse.
14. **Parser stale-state hydration:** because parsed fields are applied only when present, verify parsing document B after document A cannot leave old values from A in fields that B omits, causing a hybrid Load.
15. **Parser stop replacement:** parsing replaces draft stops when meaningful parsed stops exist. Verify human-entered stops are not silently destroyed without warning.
16. **Internal notes + customs broker line:** ensure customs broker parse hints do not duplicate or pollute user notes.
17. **Delete concurrency vs relationships:** controlled result under FK restriction/cascade conditions.
18. **Legacy board/search:** `trip_number` and legacy status mirrors must remain read-only compatibility, not regain authority.
19. **Frontend dispatch strip:** check whether driver/truck/trailer hints can silently mutate commercial form state even before explicit assignment.
20. **Unsaved-change/concurrency UX:** ensure conflict reload does not silently discard local reviewed parser values/stops.
21. **Load revenue immutability after downstream accounting begins:** determine current protection level; do not fix until Finance integration boundary is explicitly in scope.
22. **Rate Confirmation = commercial Load rule:** verify operational/trailer moves cannot accidentally create a commercial Load without real rate-con/commercial basis, except intentionally allowed draft/intake placeholders.

Cursor must try to prove the current code correct or incorrect with exact files/functions/tests rather than assuming this document is right.

---

# 5. Workflow — how we will work each issue

For each numbered issue:

```text
Step A — Cursor READ-ONLY audit of one issue
        ↓
Step B — Cursor returns exact evidence:
         files/functions/current behavior/tests/gaps
        ↓
Step C — ChatGPT independently checks the report
         against code + locked docs
        ↓
Step D — if uncertain, send Cursor back with focused questions
        ↓
Step E — owner approves exact repair plan
        ↓
Step F — Cursor implements only that issue
        ↓
Step G — targeted tests + regression tests
        ↓
Step H — ChatGPT reviews diff/report
        ↓
Step I — update this MD with:
         root cause
         accepted repair
         tests
         commit SHA
         remaining risk
        ↓
Step J — move to next issue
```

No multi-issue cleanup commits unless an issue is technically inseparable and that is explicitly documented before coding.

---

# 6. Audit/report format Cursor must use for every issue

```text
## Issue
## Locked Rule
## Current Behavior
## Exact Files / Functions
## Reproduction / Proof
## Data Integrity Risk
## Existing Tests
## Missing Tests
## Is the original audit correct?
## Anything the original audit missed?
## Smallest Safe Repair Options
## Recommended Repair
## Migration Required?
## Frontend Impact
## Backward Compatibility
## Rollback
## Files That Would Change
## STOP
```

Cursor must stop after the report unless implementation was explicitly authorized.

---

# 7. Final end-to-end Load acceptance scenario

After all numbered issues are closed, the module is not considered complete until an integrated business scenario proves the architecture rather than isolated functions.

Required scenario:

```text
real Rate Confirmation
→ RateCon evidence gate
→ parse
→ human review
→ commercial Load draft
→ references/rate/stops verified
→ Save Draft
→ edit/reorder commercial stops safely
→ Mark Ready through the authoritative gate
→ ready planning queue
→ create planned Trip
→ attach Load through TripLoad
→ assign driver/truck/trailer on Trip
→ begin execution
→ preserve custody/history
→ inbound Trip carries multiple Loads
→ yard/terminal handoff
→ Loads stage without being duplicated
→ split onto separate outbound Trips
→ complete Trips
→ final Load delivery/custody proof
→ original commercial Load/revenue remains one continuous truth
→ no stop/history/audit loss
→ no false Load execution statuses
→ downstream accounting/payroll can trace the correct Load/Trip evidence
```

Required many-to-many continuity example:

```text
2 commercial Loads
→ 1 inbound Trip
→ terminal/yard staging
→ 2 outbound Trips
→ same original Loads continue
→ no duplicate commercial revenue
→ per-Trip execution/pay trace remains distinct
```

---

# 8. Final independent review

When the numbered issues are closed and the integrated acceptance scenario passes:

1. ChatGPT performs a fresh repository audit against this document and the locked Load/Trip docs.
2. Cursor performs a final regression/report pass.
3. Antigravity performs an independent review focused on finding contradictions, hidden state writers, missing edge cases, and architectural drift.
4. Any disagreement becomes a new numbered issue in this document before the Load module is declared Gold.

---

# 9. Current issue order

Work in this order unless new evidence changes severity:

0. **Legacy Load/Dispatch footprint inventory and scrub gate**
1. **New-write Load.status boundary**
2. **Stop replacement / history destruction**
3. **Mark Ready bypass**
4. **Legacy Load assignment writer**
5. **Hard DELETE / cancellation policy**
6. **Rate Confirmation evidence gate**
7. **Raw PDF text vs Internal Notes**
8. **Decimal-safe Load money**
9. **Load audit completeness**
10. **Unknown status → Ready fallback**
11. **Parse context contract drift**
12+. **Any additional confirmed issue discovered by the adversarial audit**

**Do not start Issue 1 remediation until Issue 0 has an accepted legacy-footprint report and removal game plan. Do not start Issue 2 until Issue 1 has an accepted report and game plan.**

---

# 10. Current status

- Audit report preserved.
- Cross-check completed against the current Load/Trip/parser documentation spine.
- Issue register created.
- No Load code changed by this document.
- No migration.
- No deploy.
- No Load remediation commit.
- ISSUE 0A read-only audit received and independently reviewed. Next action: **implement ISSUE 0A only using §14 refined atomic freeze contract. No migration, no deploy, no 0B work yet.**


# 11. Cursor whole-module audit amendment — 2026-10-06

**Source:** Cursor report-only audit of the Load / Dispatch / Trip stack plus live `tenant_demo` inspection.  
**ChatGPT review status:** code claims below were independently cross-checked against current repository code where possible. Live tenant counts are recorded as **Cursor-reported live evidence** and must be re-run before any migration/data-fix commit.

## 11.1 Executive conclusion

Cursor's report materially **confirms and expands** this audit.

The most important correction to the previous plan is that the problem is broader than isolated Load bugs. The repository is still operating as **two overlapping operational products**:

```text
TARGET / NEW WORLD
Load = commercial/readiness
Trip = operational execution
TripLoad = membership
Custody = continuity

STILL-LIVE LEGACY WORLD
Load.status = operational lane
Load.driver/truck/trailer = assignment truth
dispatch_trips = dispatch identity/state
legacy /dispatch board = mature operator surface
```

The first job is therefore not merely to block one bad status. It is to **remove the executable legacy operational world in a controlled order while preserving historical read compatibility until data is migrated**.

## 11.2 Cursor-reported live tenant_demo evidence

These figures came from Cursor's live `tenant_demo` inspection and are preserved here as audit evidence. ChatGPT has **not independently rerun the tenant database query**.

Cursor reported:

| Evidence | Reported value | Meaning |
|---|---:|---|
| `Trip.status = active` | 75 | Illegal under current five-state Trip lifecycle; legacy `dispatch_trips` vocabulary leaked into canonical Trip rows |
| `Trip.status = open` | 1 | Also outside current five-state lifecycle |
| `Trip.status = in_progress` | 92 | Current legal execution state |
| in_progress trips with no open ACTIVE TripLoad | 92 / 92 | Execution can exist without active Load membership/custody |
| trips with no `trip_loads` at all | 214 | Container rows can exist disconnected from Load membership |
| assigned trips with no OPEN membership | 368 | Assignment does not imply usable Load membership |
| in_progress trips with no OPEN membership | 91 | Execution path is disconnected from membership |
| cancelled trips with `cancelled_at IS NULL` | 15 | Legacy cancellation history/state inconsistency |
| open planned memberships | 4 | Planned membership exists but Load read model does not surface it |
| open membership driver mismatches | 23 | Load-level and Trip-level assignment worlds disagree |
| email-linked Loads with zero stops | 4 / 4 | Inbox → Load handoff creates sparse stubs, not hydrated commercial Loads |

Cursor also reported that all 49 `Load.status = dispatched` rows point at Trips whose status is `active`.

**Rule:** before any data remediation is executed, Cursor must rerun and save the exact SQL/query results in the issue report. Do not write migration logic from these numbers alone.

## 11.3 Code findings independently verified after Cursor's report

### CONFIRMED — legacy dispatch mirror can write illegal Trip statuses

`app/services/dispatch_trips.py::_upsert_trip_and_membership()` currently copies:

```python
Trip.status = d_trip.status
```

and on updates:

```python
container.status = d_trip.status
```

`dispatch_trips` uses legacy values including `active` / `cancelled`; the canonical Trip lifecycle uses:

```text
planned
assigned
in_progress
completed
cancelled
```

Therefore the legacy mirror writer can create canonical Trip rows with an invalid `active` state. This is a confirmed code defect, not merely stale documentation.

### CONFIRMED — planned membership intentionally does not set `loads.active_trip_id`

`app/services/trips.py::_insert_trip_load_row()` only syncs `active_trip_id` for ACTIVE membership and explicitly leaves PLANNED membership without that pointer.

That backend rule is correct.

The UI/read model must therefore discover **open planned TripLoad membership**, not misuse `active_trip_id` as "any trip exists."

### CONFIRMED — Load page gating still depends on `active_trip_id`

Current LoadWorkspace logic still gates planned-trip affordances using `load.active_trip_id`. Existing docs also describe "Create Planned Trip when active_trip_id is null."

This is a UI/read-model mismatch with the correct membership model.

### CONFIRMED — backend Trip completion exists, but product wiring is incomplete

`complete_trip_container()` exists and correctly requires:

```text
Trip.status = in_progress
AND zero OPEN TripLoads
```

Custody transition APIs also exist in the backend architecture.

The product problem is therefore not "backend has no completion." The problem is **frontend/operator workflow incompleteness**: the current Trip surfaces do not provide the complete custody → close path operators need.

This distinction matters for remediation: do not rewrite backend completion before first proving the missing frontend/action wiring.

### CONFIRMED — assignment service is too permissive for in-progress Trip mutation

`update_trip_assignment()` blocks cancelled/completed Trips but does not block `in_progress`. It directly rewrites:

```text
trip.driver_id
trip.truck_id
trip.trailer_id
```

and only changes status when current state is planned/assigned.

Therefore an API client can silently swap assignment on an in-progress Trip even though the UI may hide that editor. This conflicts with the locked recovery/repower rule that an operational recovery requires auditable continuity rather than an invisible in-place swap.

### CONFIRMED — Decision 10 overlap guard is not present in assignment service

Current `update_trip_assignment()` validates target existence but does not perform the documented future-assignment overlap check against other in-progress Trips.

This should be tracked separately from the legacy Load assignment scrub because it is a defect in the new Trip path.

### CONFIRMED — TripLoad lookup is history-row unsafe

`_get_trip_load_row()` queries only:

```text
tenant_id
trip_id
load_id
```

without restricting to an OPEN membership or deterministically choosing the current row.

Because uniqueness is on OPEN rows, a remove + re-add history can produce multiple historical rows for the same Trip/Load pair. A scalar lookup may return a stale removed/completed row.

This is a real correctness bug for activation/completion/custody transitions.

### CONFIRMED — planned membership insert does not require Load.status = ready

`_insert_trip_load_row()` locks the Load but does not enforce commercial readiness.

This means the Trip API can attach a `draft` Load to a planned Trip unless another caller gate prevents it.

That contradicts the locked Decision 9 meaning of Ready as the planning queue boundary.

### CONFIRMED — legacy board is still runtime

`app/routers/dispatch.py` still exposes:

```text
GET /api/v1/dispatch/board
```

backed by `loads_service.list_loads_for_board()`, which groups by `Load.status`.

This is not documentation archaeology; it is a live runtime read model.

### CONFIRMED — legacy Load assignment is still runtime

The prior audit already identified the LoadWorkspace assignment path. Cursor's report reinforces that this dual assignment world is still visible to operators/read models.

### CONFIRMED — tenant identity exclusion fails open

RateCon parser exclusion lookup catches platform/exclusion lookup errors and returns an empty exclusion object.

That protects availability, but it can weaken broker-vs-carrier identity separation. It is now promoted from a challenge item to a confirmed parser integrity concern.

### CONFIRMED — old mirror catch-up has a tenant-join weakness

`app/services/trip_mirror_catchup.py::SQL_UPDATE_LOADS_ACTIVE_TRIP_ID` currently joins:

```sql
t.legacy_dispatch_trip_id = l.active_dispatch_trip_id
```

without also requiring:

```sql
t.tenant_id = l.tenant_id
```

Because tenant DBs also carry `tenant_id`, this is unsafe if contaminated/mixed-tenant rows exist.

This script must be classified as migration/backfill-only and must not be run again until tenant matching is corrected.

## 11.4 Cursor findings accepted but needing direct reproduction before repair

The following are plausible and consistent with code/docs, but each must be reproduced in its own issue before repair:

- Load page shows "Create Planned Trip" after a planned membership because it cannot see planned membership.
- header shows no trip number for planned Trip because Load read-model `trip_number` is legacy-oriented.
- current frontend cannot complete the real custody/Trip closure workflow.
- dashboard/driver stats/pay-run readers still trust legacy Load assignment/status or `active_dispatch_trip_id`.
- Inbox → draft Load preserves too little parsed commercial content, forcing operator re-upload/reparse.
- parser `stop_type="other"` falls through to DELIVERY in frontend hydration.
- parser values like country `USA` or over-length equipment strings can hydrate state that later fails persistence validation.
- name-only broker extraction may remain unlinked when MC/DOT is absent.
- mixed digital/scanned PDFs remain deliberately blocked while image-only PDFs use OCR; stale docs need correction.
- tenant_demo contains leftover rows for unexpected tenant IDs; cleanup must follow a verified tenant-isolation/data-provenance plan, not ad hoc deletion.

## 11.5 Corrections to Cursor's wording

Cursor's diagnosis is strong, but these distinctions are now locked into the plan:

1. **"A trip cannot be finished from the product"** means the **operator workflow is incomplete**, not that the backend lacks completion. Backend `POST /trips/{id}/complete` exists.
2. **92 in_progress trips with no active TripLoad** is live-data evidence of a workflow/data problem, but it does not by itself prove the Start Execution endpoint is wrong. We must trace how those rows were created before changing the endpoint.
3. **Tenant isolation** is mostly enforced at service/query level today, but schema-level composite tenant FKs are incomplete. This is architectural hardening plus contamination cleanup, not a proven cross-tenant HTTP exploit.
4. **Parser engine remains a separate concern from product handoff.** Do not reopen the gold parser core merely because downstream hydration/intake is wrong.
5. **Do not "scrub" historical migrations.** Alembic history and archived docs remain evidence. Remove or disable runtime legacy behavior, then migrate data, then remove compatibility reads only when proven safe.

---

# 12. Revised remediation order after Cursor audit

The earlier 0→11 list is retained as the issue register, but the execution order is refined below so the live dual-world split is dismantled safely.

## PHASE 0 — Legacy world containment and inventory

### ISSUE 0A — Freeze every executable legacy writer

Audit and then disable/remove all **new writes** through:

- load-status-driven dispatch mint
- `source="seed"` bypasses that can invoke old mint behavior
- legacy Load assignment writer
- any runtime writer to `dispatch_trips` used for new freight execution
- any writer that copies legacy `dispatch_trips.status` directly into canonical `trips.status`

**Goal:** stop creating more bad dual-world data before migrating existing rows.

### ISSUE 0B — Canonical Trip status contamination plan

Deal specifically with:

```text
Trip.status = active
Trip.status = open
legacy dispatch mirrors
cancelled rows missing cancelled_at
```

First audit exact source and state mapping. Then design deterministic conversion to the five-state Trip vocabulary.

No data migration until mapping rules are approved.

### ISSUE 0C — Legacy operator surface retirement map

Audit and remove/replace:

- `/dispatch` legacy board as operational authority
- `DeprecatedDispatchPage`
- `DispatchAssignmentStrip`
- `?dispatchAssign=1`
- broad Load operational status dropdowns
- dashboard/driver/pay readers that infer execution from Load status/assignment

Historical read support may remain separately.

### ISSUE 0D — Legacy mirror/backfill safety

Classify:

- `active_dispatch_trip_id`
- legacy `loads.trip_number`
- `legacy_dispatch_trip_id`
- `dispatch_trips`
- `trip_mirror_catchup.py`

Fix any backfill query that lacks tenant-safe joins before it can ever be run again.

Define when each mirror can become read-only and when it can later be removed.

**Only after 0A–0D are understood do we begin original Issue 1 remediation.**

---

## PHASE 1 — Correct commercial readiness and Load integrity

1. **Original Issue 1 — new-write Load.status boundary**
2. **Original Issue 3 — Mark Ready bypass**
3. **NEW Issue 12 — TripLoad readiness gate:** planned membership requires a truthful `Load.status = ready` unless an explicitly approved exception exists.
4. **Original Issue 2 — stop replacement / history destruction**
5. **Original Issue 5 — hard DELETE / cancellation policy**
6. **Original Issue 9 — Load audit completeness**
7. **Original Issue 10 — unknown status → Ready fallback**

Reason for moving readiness ahead of stop/parser cleanup: until Ready is authoritative, the new Trip world can still accept commercial drafts and recreate state drift.

---

## PHASE 2 — Make the Trip-first product actually operable

### NEW Issue 13 — Planned Trip discoverability from Load

The Load Page must discover current OPEN PLANNED membership from TripLoad/read API rather than `active_trip_id`.

Acceptance:

- after Create Planned Trip, Load page shows the planned Trip
- no second Create Planned Trip affordance
- correct Trip number visible from canonical Trip
- active_trip_id remains ACTIVE-only

### NEW Issue 14 — Complete custody → Trip close operator workflow

Audit existing backend transitions and wire the minimum correct product workflow for:

```text
planned membership
→ accept custody / ACTIVE membership
→ execution
→ yard/final handoff as applicable
→ no OPEN memberships
→ complete Trip
```

Do not create a fake "Complete" shortcut that bypasses custody.

### NEW Issue 15 — In-progress assignment immutability / recovery boundary

Block silent driver/truck/trailer replacement on `in_progress` Trips.

Recovery/repower must follow the locked exception model and preserve original Trip evidence.

### NEW Issue 16 — Decision 10 assignment overlap guard

Implement/test the documented future assignment conflict check separately from Issue 15.

### NEW Issue 17 — Current TripLoad row selection

Replace history-unsafe TripLoad scalar lookups with an explicit current/open-row contract where operational transitions require current membership.

Tests must cover:

```text
add
remove
re-add
activate
handoff/complete
```

and prove stale removed membership is never selected as current.

---

## PHASE 3 — Intake/parser-to-Load integrity

6. **Original Issue 6 — Rate Confirmation evidence/classification gate**
7. **Original Issue 7 — raw PDF evidence vs Internal Notes**
8. **Original Issue 11 — parse context contract drift**

Additional confirmed/new intake issues:

### NEW Issue 18 — Parser hydration stale/hybrid state

Parsing document B after document A must not leave omitted A-values mixed into B's Load draft.

### NEW Issue 19 — Parsed stop-type coercion

Unknown/`other` stop type must not silently become DELIVERY.

### NEW Issue 20 — Parser-to-persistence field-contract length/format safety

Hydrated values must already satisfy Load persistence contracts or surface field-level review errors before Save.

Examples to test:

- country code length
- equipment/trailer string lengths
- postal/state formatting
- date/time representation

### NEW Issue 21 — Tenant identity exclusion fail-open

Decide explicit behavior when tenant identity exclusion cannot be loaded.

Do not silently treat empty exclusion as equally trustworthy to a successful exclusion lookup.

### NEW Issue 22 — Inbox → Load commercial hydration

Email intake draft creation must be audited against the intended product flow.

Do not make email intake create operational Trip state. The question is only whether the commercial draft should carry the parsed RateCon fields/stops/evidence so the operator does not need to re-upload the same document.

---

## PHASE 4 — Money, isolation, and read-model hardening

8. **Original Issue 8 — Decimal-safe Load money**

### NEW Issue 23 — Tenant schema/foreign-key hardening

Audit the Load/Trip/Custody graph for tenant-safe composite uniqueness/FKs where required.

This is not permission for a broad schema rewrite. Produce the exact constraint map first.

### NEW Issue 24 — tenant_demo contamination cleanup

Only after Issue 23 and source provenance are understood:

- identify why rows for unexpected tenant IDs exist in this tenant DB
- classify test/seed/old migration contamination
- create reversible cleanup plan
- verify no legitimate rows are deleted

### NEW Issue 25 — Operational read models must become Trip-first

Dashboard, driver stats, dispatch planning views, and later pay tracing must stop treating:

```text
Load.status
Load.driver_id
active_dispatch_trip_id
```

as current execution authority.

This is separate from UI retirement because read-model consumers may remain even after old controls disappear.

---

# 13. Immediate next step

**Do not start coding the broad list.**

The next Cursor task is **ISSUE 0A only: executable legacy writer freeze audit**.

Cursor must return exact writers and dependencies before removing anything.

Required report sections:

```text
## ISSUE 0A
## Every executable legacy writer
## Every caller
## What new data each writer can still create
## Read-only dependencies
## Historical/migration dependencies
## What can be disabled immediately
## What requires data migration first
## Tests currently preserving the old writer
## Smallest safe freeze plan
## Files that would change
## STOP
```

No code, no migration, no deploy, no commit in that first pass.



# 14. ISSUE 0A audit result — accepted with implementation corrections

**Source:** Cursor ISSUE 0A read-only legacy-writer audit, reviewed against current repository code on 2026-10-06.  
**Status:** **AUDIT ACCEPTED. IMPLEMENTATION PLAN REFINED.**

## 14.1 What Cursor proved correctly

Cursor's writer inventory is materially correct.

### Production-reachable legacy writers confirmed

1. **`POST /loads` / `create_load`**
   - Can create a Load with legacy operational status because the create schema still accepts the broad status vocabulary.
   - Can accept Load-level driver/truck/trailer assignment.
   - Does **not** itself mint `dispatch_trips`.

2. **`PATCH /loads/{id}` / `update_load(source="ui")`**
   - Blocks only a **new** transition into `dispatched`.
   - Still allows other operational Load statuses such as `assigned`, `in_transit`, etc.
   - Still writes Load-level driver/truck/trailer assignment.

3. **LoadWorkspace general Save**
   - Uses `buildLoadPersistPayload`.
   - Current payload design includes status and assignment values, so ordinary commercial Save can participate in the legacy operational write model.

4. **Legacy dispatch assignment UI**
   - `DispatchAssignmentStrip`
   - `onDispatchAssign`
   - `?dispatchAssign=1`
   - `DeprecatedDispatchPage` Assign navigation
   are still live product paths into Load-level assignment.

5. **Legacy cancel-via-Load-status**
   - Existing legacy dispatched rows can still use the Load status path to cancel the old active dispatch trip/read model.
   - This still mutates legacy `dispatch_trips` and can propagate legacy status into canonical Trip state.

### Non-HTTP executable writers confirmed

- `app/scripts/seed_demo_operational_loads.py` explicitly calls `update_load(..., source="seed")`.
- `seed_dispatch.py` can seed operational Load states directly.
- Test helpers directly create legacy dispatch state.

### Read-only dependencies confirmed

Historical readers still consume:

- `Load.trip_number`
- `Load.active_dispatch_trip_id`
- Load assignment snapshots
- legacy board/status display
- pay-run tracing metadata
- some dashboard/driver/truck hints

These are **not a reason to keep producing new legacy writes**.

## 14.2 Important correction to Cursor's proposed freeze sequence

Cursor suggested:

```text
restrict LoadCreate/LoadUpdate status
then reject assignment
then hide UI
```

The direction is right, but implementation must be **coordinated**, because the current LoadWorkspace general Save still sends status and assignment fields.

If backend rejection is deployed before the frontend payload is narrowed, normal commercial Load edits can start failing even when the user did not intentionally perform an operational action.

Therefore ISSUE 0A must be implemented as **one atomic compatibility slice**:

```text
frontend stops sending legacy operational fields
        +
backend stops accepting new legacy operational writes
        +
seed bypass removed
        +
legacy cancel hook disconnected
```

Do not deploy only half of this slice.

## 14.3 Refined 0A write contract

### New Load create

Normal product Load creation should create **commercial draft state only**.

For ISSUE 0A:

```text
POST /loads
→ new Load.status = draft
→ no operational driver/truck/trailer assignment
```

Do not allow create to manufacture:

```text
unassigned
assigned
dispatched
arrived_pickup
in_transit
arrived_delivery
delivered
issue_hold
```

`ready` should also not be created by generic create because the explicit Mark Ready gate already exists and will be hardened in Original Issue 3.

### Generic Load update

General commercial Save must no longer be an execution-status writer.

For ordinary PATCH:

- do not permit transition into a legacy operational status
- do not permit new Load-level driver/truck/trailer assignment
- do not invoke legacy trip mint
- do not invoke legacy dispatch-trip cancellation

### Historical rows

Old rows must remain readable and commercially editable.

Important compatibility rule:

> A historical row whose stored status is `dispatched`, `assigned`, `in_transit`, etc. must still be able to save an unrelated commercial field **without requiring the client to rewrite or revalidate that legacy status**.

Therefore the general Save payload should **omit status when the user is not performing a dedicated status action**, rather than resubmitting the historical value on every edit.

Likewise, the general commercial Save should omit Load-level assignment fields once those fields become read-only compatibility snapshots.

This is safer than relying on "stay on same legacy status" as an ongoing generic write behavior.

## 14.4 Source=seed rule

The `source="seed"` exception must no longer bypass the product status guard.

After 0A:

```text
source metadata
!= permission to invoke obsolete business rules
```

Seed/demo scripts that need historical fixtures must use isolated test/demo fixture construction, not a production service backdoor.

Do not leave a callable production-domain service path where setting `source="seed"` changes authorization/business semantics.

## 14.5 Legacy mint helpers

After the seed bypass and Load-status hooks are removed:

- `ensure_active_trip_for_freight_load()`
- `_upsert_trip_and_membership()`
- `cancel_active_trip_for_load()`

must have **no normal product caller**.

For 0A:

- they may remain physically in the tree for tests/0B historical migration analysis
- mark/document them as legacy/internal if needed
- do not delete them yet
- prove with search/tests that product routers/UI cannot reach them

Deletion is deferred until Issue 0B/0D has rewritten historical migration tests and data conversion rules.

## 14.6 Legacy UI freeze

The following should stop creating new Load operational truth in the same 0A slice:

- LoadWorkspace operational assignment controls
- `DispatchAssignmentStrip`
- `?dispatchAssign=1`
- Assign action from `DeprecatedDispatchPage`
- broad operational `Load.status` editing

Historical values may remain visible as read-only text until 0C retires the legacy board/read model.

## 14.7 Tests required for 0A implementation

Minimum backend tests:

1. POST Load with `status=assigned` cannot create assigned Load.
2. POST Load with `status=dispatched` cannot create dispatched Load.
3. POST Load with `status=in_transit` cannot create in_transit Load.
4. POST Load with driver/truck/trailer operational assignment is rejected or stripped according to the chosen explicit API contract.
5. Generic PATCH draft → assigned is blocked.
6. Generic PATCH draft → in_transit is blocked.
7. Generic PATCH draft → dispatched remains blocked.
8. Generic PATCH cannot change Load driver/truck/trailer as operational assignment.
9. `source="seed"` cannot bypass dispatched/status guard.
10. Ordinary commercial edit of a historical `dispatched` Load succeeds when status/assignment are omitted.
11. Ordinary commercial edit does not call `ensure_active_trip_for_freight_load`.
12. Ordinary commercial edit does not call `cancel_active_trip_for_load`.
13. No new `dispatch_trips` row is created by Load POST/PATCH.
14. No new canonical `Trip.status=active` can be created through normal Load POST/PATCH.
15. Existing historical `trip_number` / `active_dispatch_trip_id` remain readable.
16. canonical `POST /trips` planned Trip creation remains unaffected.
17. Mark Ready endpoint is not accidentally removed; Issue 3 will separately make it authoritative.

Minimum frontend tests:

18. General Load Save payload omits operational Load status when not performing a dedicated action.
19. General Load Save payload omits driver/truck/trailer operational assignment.
20. Legacy assignment strip/action is no longer reachable for new work.
21. A historical Load with legacy status can still edit a commercial field without frontend attempting a legacy state rewrite.
22. Create Load submits commercial draft semantics only.

## 14.8 Do not fold other issues into 0A

0A does **not** fix:

- planned Trip visibility
- Trip status data migration
- 75 `active` / 1 `open` live rows
- TripLoad current-row lookup
- readiness requirement before Trip membership
- Mark Ready bypass in its final authoritative form
- stop history
- delete/cancel commercial policy
- dashboard/read-model migration
- pay-run migration
- parser issues
- tenant contamination
- composite tenant FKs

Those remain later numbered issues.

## 14.9 ISSUE 0A accepted implementation sequence

Implement as one narrow slice:

```text
A. Narrow frontend Load commercial Save payload
   - no operational status rewrite
   - no Load assignment write

B. Remove legacy assignment UI entry points
   - strip
   - dispatchAssign path
   - legacy Assign navigation

C. Harden backend create
   - commercial draft only
   - no Load operational assignment

D. Harden generic backend update
   - no new legacy operational status writes
   - no Load assignment writes

E. Remove source="seed" business bypass

F. Disconnect legacy mint/cancel hooks from generic Load update

G. Rewrite legacy-writer tests into freeze-regression tests

H. Prove canonical Trip APIs are unchanged
```

**No migration is required for 0A.**

## 14.10 Gate to proceed

ISSUE 0A audit is complete and accepted.

The next action may be **ISSUE 0A implementation only**, using the refined contract above.

After implementation:

- run targeted Load/Trip tests
- run frontend Load workspace tests
- run grep/call-site proof that no normal product caller reaches legacy mint/cancel helpers
- do not migrate live legacy rows
- do not deploy
- do not start 0B until ChatGPT reviews the implementation report/diff



# 15. ISSUE 0A implementation report — pending independent diff verification

**Source:** Cursor implementation report received 2026-10-06.  
**Repository state:** implementation is reported as present only in the working tree. **No commit, no deploy, no migration.**  
**Review status:** **REPORT REVIEWED; CODE DIFF NOT YET INDEPENDENTLY VERIFIED** because the changes are not committed/pushed to a ref visible to the independent reviewer.

## 15.1 Reported implementation

Cursor reports that ISSUE 0A was implemented as the required coordinated frontend + backend freeze:

- normal Load create is draft-only
- normal Load Save no longer sends operational status
- normal Load Save no longer sends `driver_id` / `truck_id` / `trailer_id`
- legacy assignment strip and `?dispatchAssign=1` path removed
- legacy board Assign navigation removed
- backend rejects operational Load create/update state
- `source="seed"` no longer changes business-state authority
- generic Load update no longer invokes legacy mint/cancel helpers
- historical legacy rows remain readable and commercially editable when status/assignment are omitted
- canonical Trip APIs were not intentionally changed

Reported touched files:

### Backend
- `app/services/loads.py`
- `app/constants/trip_dispatch.py`

### Scripts
- `app/scripts/seed_demo_operational_loads.py`
- `seed_dispatch.py`

### Frontend
- `apps/web/src/loadWorkspace/loadWorkspaceShared.ts`
- `apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx`
- `apps/web/src/pages/LoadWorkspacePage.tsx`
- `apps/web/src/pages/LoadLabPage.tsx`
- `apps/web/src/pages/DeprecatedDispatchPage.tsx`
- `apps/web/src/routes.ts`
- deleted `apps/web/src/loadWorkspace/DispatchAssignmentStrip.tsx`

### Tests
- new `tests/test_load_writer_freeze_issue0a.py`
- new `apps/web/src/loadWorkspace/loadWriterFreeze.test.ts`
- rewrites in legacy Load/dispatch tests to enforce the freeze

## 15.2 Reported verification

Cursor reports:

```text
Load/dispatch backend:
99 passed
0 skipped

loadWorkspace frontend:
72 passed

adjacent Trip/custody/intake/customs:
82 passed
50 skipped
5 failed
```

The five adjacent failures were reported to reproduce on an unmodified HEAD worktree and therefore are **not yet attributed to ISSUE 0A**.

Cursor also reports:

```text
full vitest:
367 passed
1 failed
```

with the one failure in `FuelRecentActivityInvoiceRow.test.tsx`, reproducible in isolation and unrelated to the Load changes.

Typecheck report:

```text
tsc:
128 existing errors
0 in touched files
```

A production frontend build into a temporary directory reportedly succeeded.

## 15.3 Implementation decisions accepted in principle

The following design choices are accepted **subject to diff verification**:

### Create contract

Rejecting rather than silently dropping legacy operational fields is the safer API behavior.

Reported behavior:

- operational create status → controlled 409
- `ready` on create → controlled 409
- any Load assignment field → controlled 409
- persisted create status → `draft`

### Historical edit compatibility

A historical Load may retain:

```text
assigned
dispatched
in_transit
...
```

and still accept unrelated commercial edits **when status and Load assignment are omitted**.

This matches the accepted 0A contract.

### Legacy state transitions frozen

Cursor reports that a legacy-status row cannot be moved back to draft/ready through generic PATCH.

That is acceptable for 0A because performing only the Load status change would leave legacy `dispatch_trips` / TripLoad state inconsistent.

The migration/transition policy belongs to Issue 0B.

### Legacy mint/cancel helpers retained but unreachable

Cursor reports:

- definitions remain
- normal Load service no longer imports/calls them
- remaining caller is isolated legacy test support

This is the intended 0A state.

## 15.4 Important newly discovered bug — promote to a numbered issue

Cursor reproduced an existing commercial money/audit defect:

> A PATCH that changes `rate` can commit the Load row and then fail in the audit writer because Decimal is not JSON serializable.

This is **not** a harmless test nuisance.

Potential behavior:

```text
client PATCHes rate
        ↓
Load row COMMIT succeeds
        ↓
audit serialization fails
        ↓
request returns error
        ↓
client believes update failed
        ↓
database value may already be changed
```

That creates an **ambiguous money mutation**: API failure after durable commercial revenue change.

This violates the TruckERP rule:

> no silent money edits / money changes must have truthful, atomic observable behavior.

### NEW ISSUE 26 — Money mutation commits before audit failure

**Severity:** HIGH

Audit before fixing:

1. Reproduce on unmodified HEAD with a controlled Load and exact rate change.
2. Record HTTP result, DB rate before/after, audit row before/after.
3. Find the exact transaction boundary in `update_load()` and audit writer.
4. Determine whether this affects only Decimal rate/customer_rate or any non-JSON-native values.
5. Check create, notes, customs snapshot, Mark Ready, and other Load audit calls for the same "commit then audit" pattern.
6. Decide whether Load money mutation + required audit event must be one transaction.
7. Do not broaden into the full accounting module.
8. Add regression proving a failed audit cannot leave an ambiguous committed money change.

**Ordering:** Issue 26 should be handled **before broad 0B data migration work**, because 0B should not proceed while normal commercial money edits can return failure after committing.

## 15.5 Remaining 0A verification requirements before commit

Before ISSUE 0A can be accepted as code-complete, independent review still needs the actual diff or a commit SHA.

Specifically verify:

1. `LoadCreate` / service guard does not accidentally reject legitimate non-operational commercial fields.
2. explicit `None` assignment fields return the intended controlled error and no first-party caller still sends them.
3. historical Load Save truly omits legacy status/assignment rather than sending unchanged values.
4. Mark Ready still functions through its explicit endpoint.
5. generic PATCH can still edit ordinary commercial fields on historical rows.
6. no normal runtime caller reaches `ensure_active_trip_for_freight_load`.
7. no normal runtime caller reaches `cancel_active_trip_for_load`.
8. `seed_demo_operational_loads.py` cannot recreate an equivalent hidden legacy path.
9. `seed_dispatch.py` no longer inserts operational statuses/equipment, while preserving any safe demo purpose.
10. removing `DispatchAssignmentStrip` did not leave dead imports/routes/query parsing.
11. `DeprecatedDispatchPage` no longer routes into Load assignment mutation.
12. canonical Trip create/assignment/execution services were not changed.
13. no Toll/Fuel/Auth changes are mixed into the Load slice.

## 15.6 Do not deploy yet

No deploy until:

```text
Cursor produces a reviewable diff / commit
→ independent code review
→ 0A tests rechecked
→ MD updated with accepted commit SHA
```

Running containers serving the old path is expected until deployment is explicitly authorized.

## 15.7 Current next action

**Do not begin Issue 0B yet.**

First produce a clean, reviewable ISSUE 0A commit only, without deployment.

Then independent review will inspect that exact commit and either:

- accept 0A and record the SHA, or
- send focused corrections back to Cursor.

