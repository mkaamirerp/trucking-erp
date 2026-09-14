# TruckERP Fuel / Fuel-Card Implementation Plan

**Status:** Execution plan for Cursor. This is a companion to `docs/FUEL_CARD_MODULE_DESIGN.md` and does not replace it.

**Source of truth:** `docs/FUEL_CARD_MODULE_DESIGN.md`

**Current execution scope:** PDF + manual entry + reconciliation + ownership/O-O pricing + settlement/audit + UI.

**Explicitly deferred:** Provider API implementation and API tests. The architecture may retain API as a future intake path, but Cursor must not build provider API code in this execution plan.

---

## 0. Cursor operating contract — read before touching code

This work is a financial subsystem. Do not treat it as a normal CRUD feature.

### 0.1 One segment at a time

Cursor must complete **one segment only**, run its required tests, update this file with the result, and stop.

Do not begin the next segment until the current segment has:

1. code complete,
2. tests complete,
3. results recorded in this file,
4. known failures/risks recorded,
5. user/ChatGPT review allowed to happen.

### 0.2 No hidden scope expansion

Do not redesign unrelated modules. Reuse existing TruckERP patterns for tenancy, people/payees, trucks, audit, document parsing, storage, and permissions.

Do not create a second end-to-end document parser. Fuel/Card must use the existing shared document platform and provider-specific profiles/adapters.

### 0.3 No API work now

Do **not** implement:

- BVD API adapter,
- Nationwide API adapter,
- sync scheduler,
- API credential flows,
- provider polling,
- API webhooks,
- API tests.

If existing Admin UI mentions API, it may remain as future architecture, but no API behavior is part of these segments.

### 0.4 Preserve provider evidence

Never mutate source facts to make reconciliation pass.

Keep source values and TruckERP decisions separate.

Parser/AI output is evidence only. Parser/AI must not decide:

- `truck_id`,
- owner/payee,
- O/O pricing,
- financial responsibility,
- settlement eligibility,
- posting.

### 0.5 Money rules

No transaction may post while a required gate is `FAIL` or `REVIEW`.

Grand-total equality alone is not enough. Row identity, transaction date, unit/card relationship, currency controls, historical truck/ownership resolution, and financial destination must also pass.

### 0.6 Transaction date is authoritative

Historical truck, unit-number history, ownership/payee, O/O pricing, and settlement eligibility must use the **transaction date/time**, not invoice date, import time, or current relationships.

### 0.7 Branch discipline

Do not create a new branch just because a segment starts. Use the current agreed working branch unless the user explicitly asks for a new branch.

### 0.8 Documentation discipline

At the end of every segment, append/update that segment's **Execution Record** in this file with:

```text
Status: NOT STARTED | IN PROGRESS | PASS | PASS WITH NOTES | BLOCKED | FAIL
Commit(s):
Files changed:
Migrations:
Tests run:
Test result:
Manual checks:
Known risks / TODO:
Architecture deviations: NONE or exact explanation
Date:
```

Do not mark `PASS` if required tests were skipped.

---

# Segment 0 — Repository archaeology and implementation map

## Goal

Before schema/code changes, prove where the Fuel/Card work belongs in the existing TruckERP architecture.

## Cursor tasks

- Inspect existing tenant DB patterns and migration conventions.
- Inspect truck model, unit number, ownership types, and any existing assignment/history tables.
- Inspect payee/compensation models, including existing fuel-program participation field.
- Inspect existing shared document parsing architecture and Load parser integration points.
- Inspect audit-events usage and existing financial/audit conventions.
- Inspect `/admin/integrations/fuel`, navigation, permissions, and relevant frontend patterns.
- Inspect existing upload/storage patterns for tenant documents.
- Inspect existing settlement/payroll models without changing them yet.
- Identify existing reusable services rather than duplicating logic.
- Record exact files/classes/tables/endpoints likely to be reused.

## Must not do

- No migrations.
- No Fuel/Card application behavior.
- No provider API work.
- No speculative new framework.

## Tests/checks

- Existing backend test suite relevant to touched/inspected areas must still pass unchanged.
- Existing frontend typecheck/build/tests relevant to inspected routes must pass unchanged.
- Confirm no dirty generated files were introduced.

## Exit criteria

Cursor adds a short `Repository Fit` subsection to this file documenting exactly what will be reused and any conflict between the design MD and current code.

### Execution Record — Segment 0

Status: NOT STARTED

---

# Segment 1 — Canonical Fuel/Card data model

## Goal

Create the provider-independent financial foundation before any BVD/Nationwide parser implementation.

## Required concepts

### Import batch

One uploaded provider statement/file is one batch/source record.

Batch must be able to preserve at least:

- tenant scope,
- provider code,
- account/customer reference when present,
- source type (`PDF`, later `MANUAL` where appropriate; API reserved for future),
- invoice/statement number,
- invoice date,
- statement start/end,
- due date,
- original source document reference,
- file/source hash,
- imported/uploaded timestamp,
- parse/review/process status,
- review actor/time,
- finalized actor/time,
- source totals/control references by currency.

### Canonical transaction

One real provider purchase/charge = one transaction row.

Canonical fields must support the architecture MD, including:

- provider/account,
- card number snapshot,
- auth/provider transaction code,
- driver name snapshot,
- unit number snapshot,
- transaction datetime,
- site number/name,
- city,
- province/state,
- country,
- provider product code/description,
- quantity,
- quantity unit,
- provider unit price,
- retail price,
- billed price,
- pre-tax amount,
- HST/GST/PST/QST,
- provider discount rate/amount,
- missed discount,
- out-of-network fee,
- transaction/final amount,
- currency,
- network,
- source row/order identity,
- raw/provider evidence linkage.

Provider-specific missing fields remain null. Do not make BVD and Nationwide separate core transaction tables.

### TruckERP resolution fields

Keep separate from provider facts:

- `truck_id`,
- `driver_id`,
- `owner_operator_payee_id`,
- classification,
- financial responsibility,
- pricing agreement/rule reference,
- settlement/payroll reference,
- gate/readiness statuses.

## Invariants

- Provider amount fields cannot be overwritten by TruckERP settlement calculations.
- One batch may contain many transactions.
- Currency must be stored per transaction.
- Source row identity/order must survive review.
- Posted/finalized provider facts cannot be silently rewritten.

## Automated tests

1. Create one batch with multiple transactions.
2. Verify nullable provider-specific fields work without separate schemas.
3. Verify CAD and USD transactions can coexist under one batch without being summed into a single currency amount.
4. Verify provider facts and resolution fields are separate.
5. Verify transaction datetime is stored independently from invoice/import timestamps.
6. Verify tenant isolation.
7. Verify deleting/altering a referenced parent cannot orphan financial rows contrary to repo conventions.
8. Verify migration upgrade on a clean tenant DB.
9. Verify migration against representative existing tenant schema if test harness supports it.
10. Verify downgrade only if project migration policy requires/uses downgrade testing.

## Exit criteria

Schema exists, migrations pass, tests prove one canonical transaction model.

### Execution Record — Segment 1

Status: NOT STARTED

---

# Segment 2 — Provider control totals and row/control separation

## Goal

Represent provider totals as reconciliation evidence, never as purchase transactions.

## Required concepts

Support provider controls such as:

- card subtotal,
- unit/group subtotal,
- product subtotal where provided,
- currency subtotal,
- invoice/grand total,
- tax control total,
- discount control total,
- provider-declared total,
- calculated detail-row total,
- variance.

A control row must never become a normal expense transaction.

## Automated tests

1. Create a batch with 5 transactions + 1 card total; assert transaction count remains 5.
2. Create multiple card totals; assert they link to the same batch without financial double counting.
3. Assert control totals can exist per currency.
4. Assert provider total and calculated transaction sum are stored separately.
5. Assert variance is calculated/reported, not "fixed" by mutating transaction values.
6. Assert duplicate control rows do not create duplicate transactions.
7. Assert control row source order/evidence can be traced back to the source document.

## Exit criteria

Data model cleanly distinguishes source transactions from controls.

### Execution Record — Segment 2

Status: NOT STARTED

---

# Segment 3 — Truck identity, effective-dated unit-number history, ownership/payee history

## Goal

Make historical financial resolution safe before routing provider transactions.

## Required behavior

### Unit number

`truck_id` is permanent physical-truck identity. `unit_number` is operational and changeable.

Need effective-dated history concept:

```text
truck_id
unit_number
effective_from
effective_to
reason
changed_by
```

Historical match:

```text
unit_number_snapshot + transaction_datetime -> exactly one truck_id
```

If zero or multiple candidates: `REVIEW`, never guess.

### Ownership/payee

Ownership/payee resolution must also be effective-dated.

A transaction must resolve to the owner/payee valid at transaction time, not current owner.

### Renumber vs replacement

- Same physical truck renumbered -> same `truck_id`, new history interval.
- Different physical truck -> new `truck_id`.

## Automated tests

1. Unit 1100 belongs to Truck A from Jan-Jun, then Truck A becomes 2100 in July; May transaction on 1100 resolves Truck A.
2. July transaction on 2100 resolves same Truck A.
3. If Unit 1100 is later reused by Truck B, old May transaction still resolves Truck A.
4. Overlapping unit-number history must be rejected or surface review according to implementation.
5. Missing historical match -> REVIEW, not current-truck fallback.
6. Ownership changes on July 1: June 30 transaction routes old owner, July 1+ routes new owner according to timestamp semantics.
7. Multi-truck O/O: several truck IDs resolve to same payee.
8. Company-owned truck resolves company responsibility, not O/O.
9. Changing unit number does not rewrite old transaction snapshots.
10. Verify tenant isolation for histories.

## Manual checks

Confirm unit-number change path considers existing driver/trip/fuel-card/ELD/maintenance/IFTA/document dependencies rather than silently overwriting the identifier.

## Exit criteria

Historical unit and owner/payee resolution is deterministic or explicitly review-required.

### Execution Record — Segment 3

Status: NOT STARTED

---

# Segment 4 — O/O fuel pricing agreement and onboarding/permission boundary

## Goal

Represent how an owner-operator is charged without confusing provider cost with settlement charge.

## Required pricing modes

- Pump price / no provider discount passed through.
- Full provider/company discount.
- Fixed cents per litre/gallon passed through.
- Percentage of provider discount passed through.

Percentage means percentage **of provider discount**, not percentage of pump price.

Agreement is effective-dated and belongs to O/O/payee compensation/settlement relationship.

Company driver/company truck path must not use O/O fuel-charge rules.

If relationship changes from O/O to company, old O/O charge agreement must stop applying after its effective period.

## Core pricing test example

```text
Pump price             3.00
Provider discount      0.25
Company/provider cost  2.75
O/O allowed discount   0.05
Expected O/O price     2.95
```

For percentage mode, 20% of a $0.25 provider discount = $0.05 O/O discount -> $2.95 O/O price.

## Automated tests

1. Pump-price mode.
2. Full-discount mode.
3. Fixed-discount mode.
4. Percentage-of-provider-discount mode.
5. Percentage mode explicitly proves it is not percentage of pump price.
6. Effective-date change between two pricing rules.
7. No active rule -> REVIEW/not settlement eligible where rule is required.
8. Company truck does not apply O/O pricing.
9. O/O discount cannot exceed provider discount unless an explicit future subsidy policy is added; current behavior should block/review rather than invent subsidy.
10. Provider source amount remains unchanged after O/O pricing calculation.
11. Settlement charge stored separately from provider amount.
12. Permission test: unauthorized hiring-only role/capability cannot edit monetary O/O fuel rule in segmented mode.
13. Authorized compensation/admin capability can edit according to existing permission framework.

## Exit criteria

Pricing service is deterministic, effective-dated, auditable, and separated from provider facts.

### Execution Record — Segment 4

Status: NOT STARTED

---

# Segment 5 — Shared document-platform Fuel profile contract

## Goal

Attach Fuel/Card to the existing shared document platform without creating a second parser stack.

## Rules

- Calling Fuel module chooses provider/profile.
- Shared document layer handles safe acquisition/digital-vs-scanned gate/shared transport.
- Provider profile owns field schema, row rules, control-row rules, and normalization.
- Digital PDF with usable embedded text: use digital content first.
- Scanned/image-only: OCR fallback.
- AI/mini-model, if used, returns strict schema only.
- AI cannot resolve ownership, financial responsibility, settlement, or posting.

## Automated tests

1. Digital PDF path does not invoke OCR when usable digital content exists.
2. Scanned fixture selects OCR fallback.
3. Provider profile is explicit; shared platform does not guess financial meaning.
4. Strict schema rejects malformed/extra relationship decisions if schema policy requires strictness.
5. Missing critical extraction field becomes parse/review failure, not fabricated data.
6. Row order is preserved.
7. Original source document reference/hash remains attached to batch.
8. Tenant identity/business data does not leak into provider facts unless explicitly part of source.

## Exit criteria

Fuel provider profiles plug into shared document infrastructure cleanly with no separate end-to-end parser framework.

### Execution Record — Segment 5

Status: NOT STARTED

---

# Segment 6 — BVD digital-PDF provider profile

## Goal

Implement the first production provider PDF contract.

## Verified BVD fixture expectations

Use the real/sanitized BVD fixture corresponding to the reviewed example. Expected source facts include:

### Batch/header

- Invoice: `972201`
- Invoice date: `2026-07-29`
- Statement start: `2026-07-22`
- Statement end: `2026-07-28`
- Due date: `2026-07-30`
- Client: `FIRST BASE FREIGHT LTD.`

### Transaction 1

- Card: `4237111`
- Auth: `A204040667-TA`
- Driver: `JASPREET CHOKAR`
- Unit: `1100`
- Transaction datetime: `2026-07-23 02:17:56`
- Site: `54228`
- Site name/city: `BOWMANVILLE` / `BOWMANVILLE`
- Province: `ON`
- Product: `TA`
- Quantity: `719.50`
- Retail: `2.2390`
- Billed: `2.2390`
- Pre-tax: `1425.63`
- HST: `185.33`
- Final: `1610.96`
- Currency: `CN` as provider source value; normalize currency only according to explicit mapping while preserving raw value.

### Transaction 2

- Auth: `A208448597-TA`
- Driver: `JASPREET CHOKAR`
- Unit: `1104`
- Transaction datetime: `2026-07-27 13:38:39`
- Site: `58073`
- Site name: `BVD NIAGARA`
- City: `Niagara on the Lake`
- Province: `ON`
- Product: `TA`
- Quantity: `754.50`
- Retail: `2.3990`
- Billed: `2.3990`
- Pre-tax: `1601.81`
- HST: `208.24`
- Final: `1810.05`
- Currency: `CN` source value.

### Controls

- Quantity total: `1474.00`
- Pre-tax total: `3027.44`
- HST total: `393.57`
- Final total: `3421.01`

### Product-code evidence

Preserve provider codes separately from TruckERP classification. Known BVD legend includes `TF`, `TA`, `DF`, `S`, `C`, `AD`, `O`, `L`.

Do not collapse raw `TA` into only `FUEL`; keep both raw provider code and classification.

## Automated tests

1. Exact header extraction.
2. Exact transaction count = 2 for fixture.
3. Exact field mapping for both rows.
4. Transaction datetimes remain tied to correct unit/auth row.
5. BVD control rows do not create transactions.
6. Control totals match expected values.
7. Product code raw value preserved.
8. Unknown BVD product code remains source-preserved and routes to review/classification policy rather than being dropped.
9. Missing/garbled critical row field -> REVIEW_REQUIRED.
10. Duplicate upload/source hash behavior does not silently double-post.
11. Admin grouping by Unit # does not change underlying card/source relationships.
12. No OCR called for verified digital fixture.

## Manual checks

Open the source PDF beside parsed review data and visually verify every row and control total.

## Exit criteria

BVD fixture parses reproducibly and reconciles source facts without human correction.

### Execution Record — Segment 6

Status: NOT STARTED

---

# Segment 7 — Nationwide digital-PDF provider profile

## Goal

Prove the canonical model supports a materially different provider layout.

## Critical parsing rule

**Determine row type before interpreting cell positions.**

Required row types:

- `TRANSACTION`
- `CARD_TOTAL`
- `INVOICE_SUMMARY`

A yellow/`XXXXX... Total` row is a control row, never another transaction.

Canadian total rows can place `GST`/`QST` visually under positions normally used by Date/City, so fixed transaction-column interpretation is unsafe.

## Verified Nationwide fixture expectations

### Canadian row

- Account: `20250522B`
- Card: `XXXXX87195`
- Unit: `788`
- Date: `2026-06-09`
- City: `NIAGARA-ON-THE-LAKE`
- Province: `ON`
- Product: `DIESEL`
- Volume: `674.17`
- Provider unit price: `1.659`
- Total: `1263.85`
- Network: `Esso`
- Currency: `CAD`
- USA Discount: `0.00`
- Missed Disc: `0.00`

Invoice summary evidence:

- Canadian volume: `674.17 Litres`
- Total Ex-GST & PST: `1118.45`
- GST: `145.40`
- PST: `0.00`
- CAD subtotal: `1263.85`

### U.S. row

- Card: `XXXXX07588`
- Unit: `794`
- Date: `2026-06-08`
- City: `PAULSBORO`
- State: `NJ`
- Product: `DIESEL`
- Volume: `154.27`
- Provider unit price: `4.685`
- Total: `722.75`
- Network: `TA-Petro`
- Currency: `USD`
- USA Discount: `34.56`

Nationwide note: for U.S. transactions this unit-price column is final gallon price; no GST/HST on U.S. fuel.

### Multi-row card group

Card `XXXXX87115`, Unit `789`:

- London OH DIESEL 126.01 @ 4.623 -> 582.54
- Troy IL DIESEL 109.30 @ 4.724 -> 516.33
- Napoleon OH DIESEL 74.01 @ 4.829 -> 357.39
- Card control total -> volume `309.32`, amount `1456.27`, USA Discount `169.19`

### Mixed product group

Card `XXXXX87195`, Unit `788` includes:

- SCALE 1.00 -> 15.25
- DIESEL 141.27 -> 677.95
- DIESEL 174.79 -> 891.25
- control total -> volume `317.06`, amount `1584.46`, discount `15.79`

### Invoice currency controls

- CAD: `1263.85`
- USD: `5197.69`

Reconcile independently.

## Automated tests

1. Transaction vs CARD_TOTAL classification.
2. GST/QST on Canadian total row never parsed as Date/City transaction data.
3. Canadian price semantics handled as provider source fact without renaming/mutating source.
4. U.S. unit price treated as final gallon price; no fake GST/HST added.
5. CAD and USD totals reconciled independently.
6. Mixed products (DIESEL/SCALE/REEFER/DEF PUMP) remain separate transaction rows.
7. Card/unit pairing preserved.
8. Card control row does not increment transaction count.
9. `XXXXX87115 Total` validates its card group controls.
10. Provider invoice controls validate per currency.
11. Missing card total does not cause invented control; surface according to policy.
12. Row boundary test: card/unit/date/product/amount cannot cross-contaminate neighboring rows.
13. Duplicate card numbers across different units/accounts do not collapse incorrectly.
14. No OCR on digital fixture.

### Rounding variance test — mandatory

Use the reviewed Nationwide example where visible detail rows sum to `1779.57` but provider card/invoice control prints `1779.59`.

Expected current behavior:

- preserve detail-row values,
- preserve provider control `1779.59`,
- calculate variance `0.02`,
- **do not change any row amount**,
- mark review/variance state unless/until a provider-specific accepted rounding policy is explicitly approved.

## Exit criteria

Nationwide proves provider-independent canonical model and safe row-type handling.

### Execution Record — Segment 7

Status: NOT STARTED

---

# Segment 8 — PDF review queue backend + left-PDF/right-data UI

## Goal

Implement the reviewed workflow exactly, without allowing review to bypass financial controls.

## Required flow

```text
Upload one or many PDFs
-> parse
-> review queue
-> LEFT original PDF / RIGHT parsed data
-> admin checks/corrects
-> Save & Next
-> next PDF auto-loads
-> after queue: Process
-> backend gates
-> Summary
-> Finalize/OK only when allowed
-> close/done
```

## Required statuses

Use exact repo-compatible names, but preserve architectural distinctions equivalent to:

- uploaded,
- parsed,
- review required,
- reviewed,
- processing,
- reconciliation failed,
- reconciled,
- ready to finalize,
- finalized.

`Save & Next` = human source review only. It is not posting.

## Automated backend tests

1. Multi-file queue order is stable.
2. Save & Next marks only current source reviewed.
3. Save & Next does not set posted/finalized.
4. Corrected value retains parsed value + reviewed value + actor/time/reason where required.
5. Unreviewed file blocks Process/Finalize according to workflow.
6. Failed reconciliation blocks Finalize even after human review.
7. Finalize requires all mandatory gates.
8. Tenant cannot access another tenant's batch/document.
9. Reopening a finalized batch does not permit silent financial rewrite.

## Frontend tests/manual checks

1. PDF visible on left, matching parsed form on right.
2. Save & Next advances automatically.
3. Back/forward review does not lose corrections.
4. Error/review states visibly identify the exact transaction/control problem.
5. Process waits/shows status and then displays summary.
6. Finalize button disabled/hidden when blocking gates exist.
7. Summary shows per-currency provider vs validated total and difference.
8. Mobile layout need not mimic desktop split exactly, but must remain reviewable and safe.

## Exit criteria

Admin can review multiple PDFs efficiently while system gates remain authoritative.

### Execution Record — Segment 8

Status: NOT STARTED

---

# Segment 9 — Reconciliation engine and financial gates

## Goal

Prove every provider dollar/line is accounted for exactly once before financial eligibility.

## Required invariant

Per currency/provider controls:

```text
all validated transaction amounts
+ explicitly understood provider control adjustment/rounding only if policy allows
= provider declared control total
= validated total
```

And:

```text
missing source transactions = 0
unintended duplicate transactions = 0
unresolved financial destinations = 0
unexplained variance = 0
```

## Gate families

- source/document valid,
- provider/profile correct,
- parse complete,
- row type correct,
- row boundary/source integrity,
- required fields complete,
- date/unit integrity,
- card/unit/group controls,
- currency/invoice controls,
- duplicate status,
- human review complete,
- truck resolved,
- ownership/payee resolved,
- financial responsibility resolved,
- pricing validated when applicable,
- settlement eligibility.

## Automated tests

1. Perfect BVD fixture -> reconciled.
2. Missing one transaction -> fail/review.
3. Duplicate one transaction -> fail/review.
4. Swap amounts between units while keeping grand total identical -> must fail row/group integrity or control logic where evidence allows.
5. Swap transaction dates while grand total remains identical -> historical resolution/gate must reveal changed financial result; no grand-total-only pass.
6. CAD balances but USD fails -> whole affected batch not finalizable; currencies reported separately.
7. Unknown financial destination -> block finalization.
8. Unmatched truck -> block settlement eligibility.
9. Ambiguous ownership -> block settlement eligibility.
10. Missing O/O pricing rule where required -> block settlement eligibility.
11. Company transaction does not require O/O pricing.
12. Nationwide 0.02 unexplained variance -> REVIEW under current policy.
13. Control row accidentally inserted as transaction -> reconciliation test catches double count.
14. Finalization is idempotent: repeated request cannot double-post.

## Exit criteria

No path exists from parsed data directly to posting without all mandatory gates.

### Execution Record — Segment 9

Status: NOT STARTED

---

# Segment 10 — Classification and financial-responsibility routing

## Goal

Separate `what is this transaction?` from `who pays/owes it?`.

## Required transaction classes

At minimum architecture must tolerate:

- FUEL/DIESEL,
- REEFER_FUEL,
- DEF,
- SCALE,
- CASH_ADVANCE,
- PRODUCT_PURCHASE (coolant/oil/additive/etc.),
- REPAIR_SERVICE,
- PARKING,
- TOLL,
- LUMPER,
- OTHER/REVIEW.

Provider raw product code remains preserved separately.

## Baseline responsibility rules

### Company truck/company driver

- Fuel -> company expense.
- DEF -> company expense.
- Coolant/oil/additive/product -> company expense; no driver deduction.
- Repair/service -> company unless explicit policy says otherwise.
- Cash advance -> driver receivable/deduction under policy.

### O/O truck

- Fuel -> O/O fuel charge under agreement.
- DEF -> O/O deduction.
- Coolant/oil/additive/product -> O/O deduction.
- Repair/service -> normally O/O deduction subject to contract/rule.
- Cash advance -> O/O/payee unless explicitly driver-specific policy.

### Cross-module

- LUMPER -> Fuel/Card preserves source/classification; Dispatch/Load owns load matching/reimbursement.
- TOLL -> Toll module/policy owns toll-specific processing.

Do not auto-link lumper to active trip merely because a driver had one.

## Automated tests

1. Company truck coolant -> company, driver deduction = 0.
2. O/O truck coolant -> O/O payee deduction with unit/driver/source context preserved.
3. Company cash advance -> driver responsibility according to configured baseline.
4. O/O cash advance -> O/O/payee baseline.
5. Lumper never auto-attaches to a load only from active-trip presence.
6. Toll routes to cross-module destination without disappearing from provider reconciliation.
7. Unknown product -> OTHER/REVIEW, not silently FUEL.
8. Raw provider code remains unchanged after classification.
9. Every finalized transaction has exactly one allowed financial destination.

## Exit criteria

Classification and financial responsibility are independent, testable decisions.

### Execution Record — Segment 10

Status: NOT STARTED

---

# Segment 11 — Manual driver entry and duplicate matching against PDF

## Goal

Add the third active intake path without building a separate accounting path.

## Driver input

Keep practical:

- assigned truck/unit default when reliable,
- transaction date/time,
- location/station,
- product/fuel type,
- quantity,
- unit (L/gal/etc.),
- amount,
- currency,
- receipt/photo where available.

Driver identity should come from authenticated context where possible.

Manual entry enters the same canonical model and financial gates.

## Automated tests

1. Manual entry creates canonical transaction with `MANUAL_DRIVER` source.
2. Driver identity cannot be spoofed by arbitrary body field if authenticated identity should own it.
3. Assigned truck default does not override explicit historical mismatch silently.
4. Missing required amount/date/currency validation.
5. Manual company fuel transaction does not auto-post without required review/policy.
6. Later BVD/Nationwide PDF matching the same purchase flags candidate duplicate, does not create second financial charge.
7. Strong duplicate on provider auth/transaction ID if later source supplies it.
8. Fuzzy/ambiguous match remains review-required rather than auto-merged.
9. Receipt/source attachment is tenant scoped.
10. Manual transaction retained in audit even after matched to provider evidence.

## Exit criteria

Manual entry can later reconcile to provider PDF without duplicate financial posting.

### Execution Record — Segment 11

Status: NOT STARTED

---

# Segment 12 — Settlement/payroll handoff and multi-truck O/O breakdown

## Goal

Send only financially eligible transactions to settlement/payroll, preserving drill-down.

## Rules

Provider invoice total is not an O/O settlement deduction.

Settlement uses only transactions matching:

- correct O/O/payee,
- correct truck(s),
- transaction date within settlement period,
- pricing agreement effective at transaction time,
- correct financial-responsibility path,
- all mandatory gates passed.

Keep separate:

- provider amount,
- O/O calculated charge/deduction.

O/O settlement must drill:

```text
O/O/payee
 -> Unit 1100
    -> transaction rows
 -> Unit 1104
    -> transaction rows
 -> total Fuel/Card deduction
```

TruckERP settles the O/O/payee/business. It does not decide how that O/O pays its own employee drivers.

## Automated tests

1. One O/O / one truck / multiple eligible transactions -> exact sum.
2. One O/O / multiple trucks -> unit subtotals + exact overall sum.
3. O/O with employee drivers -> settlement still belongs to O/O payee, driver preserved as context.
4. Transaction outside settlement period excluded based on transaction datetime, not invoice date.
5. Pricing rule change mid-period applies by transaction date.
6. Unresolved transaction excluded/blocks according to financial policy; never silently included.
7. Company expense never appears as O/O deduction.
8. Provider amount and O/O charge can differ and both remain visible/auditable.
9. Settlement deduction equals exact sum of selected eligible O/O charges.
10. Re-running handoff is idempotent; no duplicate settlement line.

## Exit criteria

O/O settlement total can always be traced to unit and exact provider transaction.

### Execution Record — Segment 12

Status: NOT STARTED

---

# Segment 13 — Fuel/Card Operations workspace

## Goal

Give operations a usable view of transactions, imports, exceptions, and readiness.

## Minimum useful filters

- date/period,
- provider,
- card,
- unit/truck,
- driver,
- O/O/payee,
- product/category,
- source (`PDF`, `MANUAL_DRIVER`),
- currency,
- company vs O/O responsibility,
- matched/unmatched,
- reconciled/unreconciled,
- posted/unposted.

## Required behavior

- Unit/truck is a primary operational grouping.
- Exception states lead to the exact source transaction/batch.
- Admin config and operations workspace remain separate concepts.
- O/O-facing view is a reduced projection of the same canonical data, not a second model.

## Tests/manual checks

1. Filters return correct tenant-scoped results.
2. CAD/USD filtering is correct.
3. Unit grouping totals are currency-safe.
4. O/O filter includes all owned trucks for that payee.
5. Unmatched/review filters expose blocked items.
6. Posted/unposted status reflects financial state, not only review state.
7. Drill-down reaches source batch/PDF evidence.
8. O/O portal does not expose internal parser/control noise by default but preserves traceability.

## Exit criteria

Operations can understand what is ready, blocked, matched, and posted without opening database/admin internals.

### Execution Record — Segment 13

Status: NOT STARTED

---

# Segment 14 — Audit, correction, reversal, and immutability

## Goal

Financial history must be explainable after review and after posting.

## Audit evidence

Preserve:

- original source PDF/reference/hash,
- parser output,
- parsed value,
- reviewed/corrected value,
- reviewer,
- timestamp,
- reason,
- truck/card/unit match decision,
- ownership/payee decision,
- financial responsibility,
- pricing rule used,
- settlement posting,
- adjustment/reversal.

Use existing `audit_events` foundation where appropriate instead of inventing isolated logging.

## Rules

- Before final posting, reviewed correction may update reviewed value while retaining parser/source evidence.
- After posting, no silent mutation of financial history.
- Correction after posting requires adjustment/reversal workflow and audit trail.

## Automated tests

1. Human correction retains original parsed/source value.
2. Reviewer and timestamp recorded.
3. Posted transaction source facts cannot be silently edited through normal update endpoint/service.
4. Reversal creates auditable relationship to original posting.
5. Adjustment does not erase original transaction.
6. Audit events are tenant isolated.
7. O/O pricing rule ID/version/effective agreement used is traceable after later rule changes.
8. Historical owner/payee decision remains traceable after current ownership changes.

## Exit criteria

A future auditor can explain exactly what source said, what was corrected, why, who approved it, and what money moved.

### Execution Record — Segment 14

Status: NOT STARTED

---

# Segment 15 — End-to-end financial hardening and Gold-readiness review

## Goal

Run the module as a complete PDF/manual workflow before considering Fuel Gold.

## Mandatory end-to-end scenarios

### Scenario A — BVD company trucks

Upload BVD fixture -> parse -> review -> process -> resolve trucks -> company responsibility -> reconcile exact provider controls -> finalize -> no O/O deduction.

### Scenario B — BVD O/O multi-truck

Two units owned by same O/O -> apply effective pricing -> reconcile source -> settlement shows each unit separately -> O/O total equals exact eligible charge sum.

### Scenario C — Nationwide mixed CAD/USD

One statement with CAD and USD -> parse row types correctly -> reconcile each currency independently -> no cross-currency fake total.

### Scenario D — Nationwide control-row trap

Canadian yellow total row with GST/QST visually under transaction columns -> no fake transaction/date/city -> correct control extraction.

### Scenario E — Nationwide rounding variance

`1779.57` visible row sum vs `1779.59` provider control -> preserve both -> variance `0.02` -> REVIEW under current policy -> no source mutation.

### Scenario F — Manual then PDF duplicate

Driver manually enters purchase -> provider PDF later contains same purchase -> candidate match -> only one financial charge after resolution.

### Scenario G — Historical renumber

Truck renumbered after transaction -> old source unit still resolves correct permanent truck by transaction date.

### Scenario H — Ownership change

Truck changes O/O/company ownership -> transaction before/after date routes correct historical party.

### Scenario I — Lumper

Fuel-card lumper source reconciles in Fuel/Card but does not auto-attach to arbitrary active load/trip.

### Scenario J — Posted correction

Posted transaction needs correction -> normal edit blocked -> reversal/adjustment path audited.

## Global regression tests

- Full backend test suite.
- Relevant frontend tests/typecheck/build.
- Tenant-isolation/security tests.
- Migration tests.
- No API tests required because API implementation is explicitly deferred.
- Verify existing Load shared-document parser remains green; Fuel work must not regress Load parsing.
- Verify existing People/Payee/Truck flows remain green where reused.

## Performance/safety checks

- Multi-PDF review queue with representative batch size.
- No N+1 explosion in unit/payee/transaction list paths if practical to test.
- File upload rejects unsafe/non-PDF source according to existing shared acquisition rules.
- No secret/provider credential exposure added in frontend payloads.

## Gold rule

Do **not** establish/update Fuel Gold merely because code compiles.

Gold readiness requires:

- Segments 0-15 complete or explicitly accepted/deferred,
- mandatory tests green,
- real BVD PDF verified,
- real Nationwide PDF verified,
- no unexplained reconciliation variance accepted as PASS,
- architecture MD and this execution plan updated with final implementation evidence,
- user/ChatGPT review of final state.

### Execution Record — Segment 15

Status: NOT STARTED

---

# Segment completion protocol for Cursor

After finishing **each** segment:

1. Stop coding.
2. Run every required test listed for that segment.
3. Run targeted regressions for reused modules.
4. Update that segment's Execution Record in this file.
5. Add exact test commands and counts, for example `123 passed, 0 failed`.
6. List every migration and changed file.
7. State any test not run and why.
8. State any deviation from `FUEL_CARD_MODULE_DESIGN.md`.
9. State whether the segment is safe to review: `YES` or `NO`.
10. Do not start the next segment until reviewed/authorized.

Cursor must not replace test evidence with statements such as "looks good", "should work", or "implemented successfully".

---

# Review protocol for ChatGPT/user after Cursor work

When a segment is returned for review, the reviewer should check:

- Does implementation match the architecture rather than only the happy path?
- Did Cursor reuse existing TruckERP services instead of duplicating them?
- Are provider facts immutable/separate from TruckERP decisions?
- Is transaction datetime driving historical decisions?
- Are control rows excluded from transaction counts?
- Is every currency reconciled independently?
- Are unresolved/ambiguous relationships blocked rather than guessed?
- Can any UI action bypass required backend gates?
- Are company vs O/O rules correct?
- Can the exact financial result be traced back to source evidence?
- Did all required tests actually run?

If any answer is no, the segment remains open.

---

# Explicitly deferred after this implementation plan

The following remain future work unless user explicitly reopens them:

- Provider API adapters and synchronization.
- API credentials/test-connection behavior beyond placeholder/config architecture already present.
- Nationwide CSV companion ingestion.
- Additional providers beyond BVD/Nationwide.
- Automatic provider-specific rounding tolerance until proven by real provider rules.
- Automatic lumper-to-load matching beyond an explicitly safe future rule.
- Any new O/O subsidy rule that permits passing more discount than the provider actually gave.

These deferrals must not be silently implemented during another segment.
