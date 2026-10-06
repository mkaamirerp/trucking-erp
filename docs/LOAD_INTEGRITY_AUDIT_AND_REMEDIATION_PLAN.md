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

**Do not start Issue 2 until Issue 1 has an accepted report and game plan.**

---

# 10. Current status

- Audit report preserved.
- Cross-check completed against the current Load/Trip/parser documentation spine.
- Issue register created.
- No Load code changed by this document.
- No migration.
- No deploy.
- No Load remediation commit.
- Next action: **Cursor read-only audit of ISSUE 1 only.**
