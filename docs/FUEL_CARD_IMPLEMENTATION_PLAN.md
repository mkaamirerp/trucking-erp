# TruckERP Fuel / Fuel-Card Implementation Plan

**Status:** Execution plan for Cursor. Companion to `docs/FUEL_CARD_MODULE_DESIGN.md`; does not replace the architecture source of truth.

**Source of truth:** `docs/FUEL_CARD_MODULE_DESIGN.md`

**Current execution focus:** BVD provider-native extraction foundation first; Nationwide second. Canonical financial semantics, reconciliation math and settlement work come after source/structure completeness is proven.

**Important:** Existing Fuel code already contains partial implementations. This document does not infer completion from file presence. A segment is complete only after code + required tests + recorded evidence pass the gates below.

---

# 0. Operating contract

Fuel/Card is a money-moving subsystem. Do not treat it as ordinary CRUD.

## 0.1 One segment at a time

For each segment:

1. inspect current implementation before editing;
2. change only the segment scope;
3. run required tests;
4. record exact results;
5. record known risks/TODO;
6. stop for review before moving to the next segment.

Execution record template:

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

Do not mark PASS when required tests were skipped.

## 0.2 Branch discipline

Do not create a new branch merely because a segment starts. Use the agreed working branch unless explicitly asked otherwise.

## 0.3 No second document stack

Reuse existing TruckERP tenancy, storage, audit, permissions, document-processing, people/payee, truck and settlement patterns where they fit.

Do not create a separate generic PDF/OCR/OpenAI platform just for Fuel.

## 0.4 No generic provider fallback

Unsupported provider/profile/layout must not silently enter financial staging.

```text
approved provider/profile -> process
unknown provider/profile  -> reject or review
```

## 0.5 API-first provider rule

For a provider with a usable authorized production API:

```text
API ONLY by default
```

Do not build a parallel PDF parser merely because PDFs exist.

If no usable authorized API exists, use the specifically approved PDF/CSV/export contract.

Current foundation:

```text
BVD        -> approved digital PDF path
Nationwide -> approved digital PDF path
```

## 0.6 Parser output cannot move money

Parser/AI/native extraction never decides:

- `truck_id`;
- `driver_id`;
- owner/payee;
- financial responsibility;
- O/O pricing;
- settlement eligibility;
- posting.

Those are later backend decisions after source evidence and review.

---

# 1. Current execution sequence (locked precedence)

**BVD contract for the current milestone:** `docs/FUEL_BVD_IMPLEMENTATION_1.md` — not superseded by the segment letters below.

The **active** execution order is:

## PHASE 1 — BVD IMPLEMENTATION 1

- exact BVD digital-PDF extraction
- one `fuel_bvd` table
- exact TEXT source values
- PostgreSQL round-trip
- side-by-side review (PDF left / PostgreSQL values right)
- no truck matching, driver matching, O/O logic, reconciliation, settlement, or posting

**Status:** CODE/TEST ACCEPTANCE PASSED. Live application migration/browser acceptance still pending.

## PHASE 2 — BVD LIVE ACCEPTANCE

- controlled tenant migration
- upload verified BVD PDF through the application
- PDF left / PostgreSQL values right
- visually confirm extraction fidelity
- no downstream financial processing

## PHASE 3 — BVD HARDENING

- additional real BVD invoices/layout cases
- no fixture-specific assumptions
- ambiguous source structure → REVIEW, never guess

## PHASE 4 — NATIONWIDE SOURCE-FIDELITY PROOF

- reuse generic digital PDF capability/profile framework where appropriate
- exact Nationwide source contract
- do not force BVD columns/structure onto Nationwide

## PHASE 5 — LATER ARCHITECTURE / OPERATIONALIZATION

Only after source fidelity is proven for the supported providers:

- generalized provider-native framework (`fuel_source_document`, parse runs, blocks/records) if still needed
- canonical semantic mapping
- truck/driver/history resolution
- reconciliation
- financial responsibility
- O/O pricing
- settlement/posting

Do not pull Phase 5 semantic/math work forward merely because the source contains prices, taxes or totals.

---

# 1A. Reference segment map (architecture decomposition — not current execution authority)

The letters **A–O** below decompose the **future** provider-native and financial layers from `docs/FUEL_CARD_MODULE_DESIGN.md`. They are **not** the current execution order while BVD Implementation 1 is in flight.

```text
A. provider registry / profile whitelist
B. immutable source document
C. versioned parse run
D. block/group classification
E. provider-native field hydration
F. append-only native storage
G. append-only review/correction overlay
H. provider-native review UI
I. BVD field/structure completeness tests
J. Nationwide framework proof
-------------------------------
THEN (Phase 5)
K. canonical semantic mapping
L. reconciliation / financial gates
M. historical truck/ownership resolution
N. O/O pricing / financial responsibility
O. settlement / posting / cross-module routing
```

# 2. Segment A — provider profile whitelist

Implement or reconcile the provider-profile registry.

Required behavior:

- provider + profile version is unique;
- profile state supports at least `approved` and `retired`;
- retired profiles remain readable historically;
- only approved profiles may start new ingestion;
- allowed block/structure types are registered per profile/version;
- unknown structure types are rejected/reviewed rather than accepted silently;
- tenant configuration can use only supported provider profiles.

Current supported/test provider profiles:

```text
BVD
NATIONWIDE
```

Do not add a third production provider during this foundation phase.

### Segment A tests

- unsupported provider cannot start ingestion;
- unknown profile version cannot start ingestion;
- retired profile remains readable but cannot start a new parse;
- unknown structure type cannot be silently stored as valid;
- Tenant A cannot use Tenant B provider configuration.

---

# 3. Segment B — immutable source document + parse run separation

The source file/payload and its parser interpretation are separate concepts.

## 3.1 Source document

Store at minimum:

```text
id
tenant_id
source_type
file_sha256
storage_ref
original_name
content_type
created_at
```

Rules:

- source bytes live in object/file storage;
- Postgres stores the storage reference and SHA-256;
- same tenant + same file hash is idempotent at source-document level;
- source document is immutable after insert;
- `file_sha256` is 32 bytes when stored as binary SHA-256.

## 3.2 Parse run

Store separately:

```text
id
tenant_id
document_id
provider
profile_version
parse_status
review_status
created_at
```

The same immutable source document may have multiple explicit parse runs under different profile versions.

A newer profile never silently rewrites finalized history.

### Segment B tests

- duplicate source file for same tenant does not create a second source document;
- same document can have explicit v1 and v2 parse runs;
- changing parse rules does not mutate original source hash/reference;
- Tenant A parse cannot reference Tenant B document.

---

# 4. Segment C — source blocks/groups

Implement first-class source structures rather than forcing every source element into a row.

Conceptual block fields:

```text
id
tenant_id
parse_run_id
parent_block_id nullable
block_sequence
block_type
provider_native_fields jsonb
inherited_context_fields jsonb
raw_text / raw_source_evidence
page / source coordinates
confidence
requires_review
```

Required examples:

```text
BVD Client info
BVD Transactions for card 4237111
BVD transaction table
BVD page-1 controls
BVD Grand Totals
BVD Legend
Nationwide ACCOUNT INFORMATION
Nationwide BILLING SUMMARY
Nationwide TRANSACTION BREAKDOWN BY CARD
```

### Segment C tests

- BVD card group has a persistent block id;
- BVD child transactions can reference/inherit that group context;
- Client info and Legend have a home without pretending they are transactions;
- nested/child blocks cannot cross tenant/parse-run boundaries.

---

# 5. Segment D — provider-native record storage

Implement provider-native rows/records under a block.

Conceptual fields:

```text
id
tenant_id
parse_run_id
block_id
seq
page
structure_type
fields jsonb
inherited_context_snapshot jsonb
raw_text / raw_source_evidence
confidence
requires_review
```

Use an ordered JSONB **array**, not an object:

```json
[
  {"label":"QTY","raw":"719.50","evidence":{}},
  {"label":"Pre Tax AMT","raw":"1,425.63","evidence":{}},
  {"label":"HST","raw":"185.33","evidence":{}}
]
```

Rules:

- source field order is preserved;
- duplicate labels are allowed/preserved;
- every provider-native raw value is stored as a JSON string;
- native records are append-only;
- application role cannot UPDATE/DELETE native evidence after insert;
- ordered identity is unique within a parse run.

Do not add a GIN index on native JSONB fields during this phase unless a real query requires it.

### Segment D tests

- `1,425.63` remains exactly `1,425.63`;
- `0.0000` keeps trailing zeros as source text;
- repeated labels remain distinct array entries;
- record sequence is stable;
- native UPDATE/DELETE is blocked;
- confidence/page checks work if implemented in schema.

---

# 6. Segment E — append-only review/correction overlay

Review never mutates the native record.

Support at least:

```text
CONFIRM
RECLASSIFY
FIELD_CORRECTION
REJECT
```

Example:

```json
{
  "field": "Unit #",
  "native_raw": "110A",
  "reviewed_raw": "1104",
  "reason": "PDF visual confirmation"
}
```

Store reviewer identity, reason and timestamp.

The effective reviewed structure/value must be what later mapping/reconciliation consumes, while original native evidence remains intact.

### Segment E tests

- field correction leaves native JSON unchanged;
- structure reclassification leaves native structure unchanged but changes effective reviewed classification;
- review history is append-only;
- unresolved review prevents later financial PASS;
- Tenant A reviewer cannot modify Tenant B evidence.

---

# 7. Segment F — BVD profile v1 structure contract

BVD is the first production provider contract.

Use the approved BVD fixture(s). Freeze **source labels**, not convenience names.

## 7.1 Header / Client info

Exact invoice/header labels:

```text
Invoice Number
Invoice Date
Start Date
End Date
Due Date
```

Client block:

```text
Client info
[unlabeled customer-name line]
Address:
Phone:
Email:
```

Do not invent a source `Client` label for the unlabeled customer name.

## 7.2 Card-group context

```text
Transactions for card
```

The value `4237111` in the approved fixture is **group context**, not a per-row Card column.

Child transaction records inherit/reference the card-group value.

## 7.3 Exact BVD transaction columns — 21

```text
Auth Code
Driver Name
Unit #
Date
Site #
Site Name
Site City
Prov/ST
Prod
QTY
Retail
Billed
Pre Tax AMT
HST
GST
PST
QST
Disc Rate
Disc AMT
Final AMT
CUR
```

## 7.4 Page-1 control inventory — exact current fixture

Transaction-level control label:

```text
SUBTOTAL
```

Observed post-transaction control sequence:

```text
SUBTOTAL | TA
Card #   | TF
4237111  | Fuel Total
[blank]  | DF
[blank]  | Sub Total
```

Do not write “including ...” and leave the inventory open-ended for an approved profile. Unknown new structure causes review/profile-version work.

The summary `Card #` / `4237111 Fuel Total` relationship must be linked to the `Transactions for card 4237111` group explicitly.

## 7.5 Grand Totals exact columns — 11

```text
PRODUCT
QTY
PRE TAX AMT
HST
GST
PST
QST
DISC RATE
DISC AMT
FINAL AMOUNT
CUR
```

Observed row labels:

```text
TA
TF
DF
Manual
Express
Grand Total
```

`Manual` and `Express` are Grand Totals labels, not Legend product codes.

## 7.6 Legend block

```text
Legend
Code
Product Name
```

Observed pairs:

```text
TF  Trailer
TA  Tractor
DF  DEF
S   Scale
C   Cash
AD  Additive
O   Oil
L   Lubricant
```

### Segment F tests

- exact 21 transaction labels match fixture;
- `Pre Tax AMT` and `Disc Rate` cannot disappear from manifest;
- transaction 2 correctly inherits card group even without a row Card column;
- SUBTOTAL never becomes a purchase;
- full page-1 control sequence is recognized;
- exact 11 Grand Totals columns match fixture;
- `Manual`/`Express` do not enter Legend code mapping;
- Legend rows never become purchases;
- unknown BVD layout/field/structure is review/reject, not silent acceptance.

---

# 8. Segment G — BVD digital-PDF extraction

Extraction order is locked:

```text
recognize BVD profile/version
-> classify block/group
-> classify row/structure type
-> hydrate exact structure fields
-> attach inherited group context
-> store native evidence
-> review overlay if required
```

For a digital PDF, use embedded digital content first. OCR is fallback only when the source is actually scanned/unusable.

The parser may use deterministic extraction and constrained AI assistance, but it must return only the approved provider structures/fields.

Do **not** perform semantic price/tax/O/O calculations in this segment.

### Segment G tests

- approved fixture parses all expected structures;
- no data-bearing field/label is omitted;
- source record order is preserved;
- evidence links to page/row/source position where available;
- missing required source field causes review;
- provider control rows never increment transaction count;
- native raw values remain exact strings.

---

# 9. Segment H — BVD provider-native review UI

For BVD source review:

```text
LEFT  -> original BVD PDF
RIGHT -> BVD-native blocks/records
```

Right side should show the exact BVD field labels and card-group context.

Frontend may group for usability, but it must not hide structural evidence required to audit the extraction.

`Save & Next` confirms source review only. It never posts money.

### Segment H tests/manual checks

- card-group context visible;
- 21 BVD columns display correctly;
- Client info / controls / Grand Totals / Legend are inspectable;
- field corrections create review records rather than editing native data;
- structure corrections affect effective reviewed classification;
- backend rejects unauthorized review actions.

---

# 10. Segment I — BVD foundation gate

BVD foundation is complete only when all are true:

```text
[ ] approved profile/version exists
[ ] every data-bearing block/group in approved fixtures inventoried
[ ] exact invoice-header labels frozen
[ ] Client info represented correctly
[ ] Transactions for card stored as group context
[ ] child transactions inherit/reference group context
[ ] exact 21 transaction columns frozen
[ ] transaction SUBTOTAL rows classified as controls
[ ] full page-1 control sequence frozen
[ ] Card # summary relationship represented
[ ] exact 11 Grand Totals columns frozen
[ ] Grand Totals row labels inventoried
[ ] Manual/Express kept out of Legend product-code set
[ ] Legend block preserved
[ ] native raw values stored as strings in ordered arrays
[ ] native evidence append-only
[ ] review overlay append-only
[ ] unknown structure/layout requires review
[ ] field-completeness tests PASS
[ ] structural-completeness tests PASS
[ ] document-level regression fixture PASS
[ ] generic fallback cannot silently post money
```

Do not claim “100% known field extraction” before this gate is satisfied for the approved profile/version.

---

# 11. Segment J — Nationwide profile/framework proof

Nationwide validates that the framework is reusable without copying BVD's fields.

## 11.1 Exact data-bearing blocks

```text
PROVIDER / CONTACT BLOCK
ACCOUNT INFORMATION
BILLING SUMMARY
TRANSACTION BREAKDOWN BY CARD
TRANSACTION
CARD_TOTAL
```

## 11.2 Exact transaction columns

```text
Account Code
Card Number
Unit #
Date
City
Pr/St
Product
Volume
Ex-GST ($/U)
Total
Network
Currency
USA Discount
Missed Disc
OON Fees
```

Unlike BVD, `Account Code` and `Card Number` are per-transaction columns in the current fixture.

`XXXXX... Total` rows are `CARD_TOTAL` controls.

Explicit `GST`/`QST` labels in Canadian control rows own those values; visual x-position does not convert them into transaction fields.

### Segment J tests

- exact source labels, not convenience labels;
- transaction vs CARD_TOTAL classification happens before hydration;
- Canadian card-total GST/QST stays control data;
- Account Code and Card Number remain row fields;
- currencies/values remain raw source strings at native layer;
- unknown Nationwide layout/structure causes review;
- no BVD-shaped assumptions leak into Nationwide.

---

# 12. Segment K — canonical semantic mapping (later)

Do not begin until BVD native foundation and Nationwide framework proof are stable.

This segment decides what provider-native fields mean to TruckERP.

Work includes:

- canonical transaction fields;
- provider-specific semantic mapping;
- quantity/UOM semantics;
- price basis;
- tax meaning;
- discount meaning;
- transaction/control semantic mapping;
- raw provider values retained alongside canonical values.

This is where questions such as tax-inclusive vs ex-tax pricing belong.

Do not back-port these interpretations into native extraction.

---

# 13. Segment L — reconciliation and financial-control fixes

Before financial posting, fix and test the confirmed audit issues.

Required fixes:

1. CAD and USD can never be summed into one fake control total.
2. Review-required/invalid controls cannot authorize reconciliation PASS.
3. Effective reviewed structure/classification must drive reconciliation without mutating native evidence.
4. Every source row/control is accounted for exactly once.
5. Provider totals reconcile independently by currency.
6. Grand-total equality alone does not excuse wrong row/date/unit/card assignment.
7. Source amounts are never edited to force balance.
8. Credit/refund/reversal sign rules become hard gates where applicable.
9. `READY_FOR_RECONCILIATION` reflects all unresolved conditions, not only pending counts.

### Segment L tests

Include explicit regressions for:

```text
CAD 100 + USD 100 + control 200/no currency -> MUST NOT PASS
requires_review control matching amount       -> MUST NOT PASS
reviewed role UNKNOWN/TRANSACTION             -> MUST NOT act as valid control
```

---

# 14. Segment M — historical truck/ownership resolution

Use transaction date/time, not invoice/import/current date.

Required concepts:

```text
permanent truck_id
unit_number_snapshot
unit-number history
effective-dated ownership/payee
provider/source timezone for date-only evidence
```

Fix the confirmed DATE_ONLY timezone-boundary bug before financial use.

Zero or multiple historical matches -> review.

---

# 15. Segment N — O/O pricing and financial responsibility

Commercial truck/fuel responsibility decides who pays. Driver employment type must not suppress an O/O charge merely because the person driving is a company employee.

Supported later O/O fuel-pricing modes:

- pump price / no provider discount passed through;
- full provider/company discount;
- fixed cents per litre/gallon;
- percentage of provider discount.

Add hard validation for:

- negative quantity where invalid;
- discount greater than applicable price/basis where invalid;
- negative charge price;
- negative settlement charge unless explicitly represented as a valid credit/reversal.

Classification and financial responsibility remain separate decisions.

---

# 16. Segment O — settlement/payroll and cross-module routing

Only transactions with all required gates passed may enter settlement/posting.

Provider amount and contractual O/O charge remain separate.

Multi-truck O/O drilldown:

```text
O/O/payee
  -> Unit 1100
      -> transaction detail
  -> Unit 1104
      -> transaction detail
  -> Fuel/Card deduction total
```

Cross-module boundaries remain:

- Lumper -> Dispatch/Load workflow after Fuel/Card source/classification;
- Toll -> Toll module/policy;
- Cash advance -> driver/O/O receivable/deduction policy.

Posted corrections use audited adjustment/reversal.

---

# 17. Provider onboarding after BVD/Nationwide

For every future provider/program:

1. identify the actual vendor/program the carrier contracts with;
2. identify the interface the carrier can authorize TruckERP to use;
3. if usable production API exists, prefer API;
4. otherwise approve a specific PDF/CSV/export contract;
5. inventory exact source blocks/groups;
6. inventory exact native labels/keys;
7. define inherited-context behavior;
8. define row/control types;
9. freeze fixtures;
10. prove field + structural completeness;
11. version the profile;
12. only then enable the provider.

Underlying EFS/Comdata/WEX/etc. network is informational lineage and does not grant access to white-label customer data.

---

# 18. Core regression families

At minimum maintain tests for:

1. tenant isolation for provider/document/parse/block/record/review;
2. provider/profile whitelist;
3. retired-profile ingestion block;
4. immutable source hash/reference;
5. repeat source-file idempotency;
6. multiple parse runs on same source;
7. native raw string preservation;
8. ordered/repeated JSONB field preservation;
9. append-only native evidence;
10. append-only review overlay;
11. BVD exact header/client/card-group structures;
12. BVD exact 21 transaction fields;
13. BVD page-1 control inventory;
14. BVD exact 11 Grand Totals columns;
15. BVD Legend and Manual/Express separation;
16. Nationwide exact 15 transaction columns;
17. Nationwide CARD_TOTAL classification;
18. unknown provider/layout/structure review/reject;
19. CAD/USD independent reconciliation;
20. reviewed control cannot bypass gates;
21. historical date-only timezone resolution;
22. O/O ownership responsibility independent of driver employment type;
23. O/O numeric sanity gates;
24. credit/refund/reversal sign gates;
25. finalization idempotency;
26. posted adjustment/reversal audit;
27. existing Load/People/Truck regressions remain green.

---

# 19. Current confirmed audit checkpoint

From the uploaded Fuel archive review:

```text
102 tests passed
```

Three additional test modules did not collect in that audit runtime because `asyncpg` was not installed there while repository requirements included `asyncpg==0.31.0`. Treat that as an audit-environment issue unless reproduced in the real project environment.

Confirmed code issues still requiring remediation before financial posting:

```text
- O/O responsibility incorrectly influenced by is_company_driver
- DATE_ONLY historical timezone boundary error
- mixed CAD/USD reconciliation can pass
- unresolved control can authorize PASS
- review role change can fail to affect effective reconciliation role
- impossible negative O/O pricing can return CALCULATED
- credit/refund/reversal sign rule not enforced end-to-end
- review readiness too shallow
```

Do not establish Fuel Gold while any required financial blocker remains open.

---

# 20. Review protocol for every segment

Before accepting a segment, verify:

- provider/profile support is explicit;
- exact source structure is classified before hydration;
- source labels are provider labels, not invented convenience labels;
- group/inherited context is represented;
- source order and raw formatting are preserved;
- source evidence is immutable;
- review is an overlay, not mutation;
- tenant isolation is backend/database enforced;
- UI cannot bypass backend money gates;
- no premature semantic/math rule leaked into native extraction;
- tests actually ran and counts are recorded.

Any failed answer leaves the segment open.

---

# 21. Gold readiness boundary

Fuel Gold is a later milestone. It requires at minimum:

- BVD native foundation complete;
- Nationwide framework proof complete;
- immutable storage/review model verified;
- unsupported providers/layouts blocked;
- required semantic/reconciliation layers verified;
- all confirmed financial audit bugs closed;
- end-to-end company/O-O/settlement scenarios green;
- audit/reversal behavior green;
- deployment artifact/commit frozen and documented in `FUEL_GOLD_MANIFEST.md`.

---

# 22. Historical Fuel implementation checkpoints

**Not current execution-order authority.** The checkpoints below record factual commit/test evidence from prior `feat/fuel-card` segment work (Segments 0A–15 narrative). The **current** execution sequence is **§1 Current execution sequence** (Phases 1–5) and `docs/FUEL_BVD_IMPLEMENTATION_1.md`.

## Segment 0A — Provider catalog + tenant connection backend

Implement:

- provider registry/catalog,
- tenant provider connection model,
- connection-method metadata,
- dynamic field schema,
- secure secret reference,
- RBAC-protected endpoints,
- test-connection adapter hook,
- same records exposed from Admin and Fuel page,
- multiple accounts/provider per tenant.

`tenant_id` on `fuel_provider_connections` follows existing tenant data-plane composite isolation `(tenant_id, id)` (same as `people` / `loads` / `tenant_email_mailboxes`). It does not move this table to the platform DB.

Do not implement fake connectivity for providers without real specs. Do not advertise unverified SFTP/API methods as configurable. Do not rewrite Fuel architecture chapters when recording this segment.

**Execution Record:**
```text
Status: PASS WITH NOTES
Commit(s): none (not committed; awaiting review)
Files changed: see Segment 0A review-fix stop report
Migrations: alembic_tenant/versions/f0a1c2d3e4f5_fuel_provider_connections.py (revises u4v5w6x7y8z9; not applied on this host)
Tests run: tests/test_fuel_segment_0a.py + Load parser / document-parse / audit writer regressions
Test result: Segment 0A 26 passed; Load parser / document-parse / audit writer regressions 150 passed, 3 skipped
Manual checks: not deployed; UI not browser-verified on this host
Known risks / TODO:
  - Live adapters remain unimplemented by design; Test/Sync persist connection_method_not_implemented with success=false attempted=false
  - Unverified provider methods stay listed but not configurable until captured evidence exists
  - Platform+tenant secret write uses two commits (same pattern as other integrations); orphan platform secret possible if tenant commit fails
  - HTTP tests use a mini FastAPI app (fuel router only) because TenantContextMiddleware DNS-fails pytest.truckerp.me on this host
Architecture deviations: adapter hook named attempt_test_connection (not test_connection) so pytest does not collect it; MANUAL_DRIVER is a known method constant but no catalog vendor lists it yet. Fuel architecture chapters in this file and FUEL_CARD_MODULE_DESIGN.md were not rewritten for Segment 0A.
Date: 2026-09-17
```

## Segment 1 — Canonical Fuel/Card schema

Implement source batches, canonical transactions, raw sidecar, source identity/order, optional network/merchant fields and separate resolution fields.

Architecture locks that Segment 1 must follow: Module Design §1.5 decimal/`NUMERIC` scales, §1.6 three identities, §1.7 / §9.2 event type raw vs canonical, §1.8 currency raw vs canonical, §1.9 owner-operator charge provenance, §14.1 timezone provenance and source-local `transaction_date`. Do not use `float` columns or treat provider auth numbers as the canonical PK. Do not populate `owner_operator_charge_amount`. Do not start Segment 2 or later workflows.

**Execution Record:**
```text
Status: PASS WITH NOTES
Commit(s): none (not committed; awaiting review)
Files changed: see Segment 1 source-truth correction stop report
Migrations: alembic_tenant/versions/f1b2c3d4e5f6_fuel_source_batches_transactions.py (revises f0a1c2d3e4f5; not applied on this host)
Tests run: tests/test_fuel_segment_1.py + tests/test_fuel_segment_0a.py + Load parser / document-parse / audit writer regressions
Test result: Segment 1 13 passed; Segment 0A 26 passed; Load parser / document-parse / audit writer regressions 150 passed, 3 skipped
Manual checks: not migrated; not deployed
Known risks / TODO:
  - Canonical batch/transaction tables are `fuel_source_batches` / `fuel_transactions` only (no parallel import-batch table concept)
  - Control-row tables remain Segment 2
  - Resolution columns are nullable placeholders without FKs or resolver logic
  - owner_operator_charge_amount remains nullable on the canonical row as derived pricing/settlement; Segment 1 does not populate it
  - Architecture locks for finalization SoD, layout fingerprinting, bulk review, downstream ack scheduler, and reporting-currency conversion records are documentation-only (not implemented)
Architecture deviations: table names as above; no transaction CRUD API in Segment 1 (schema foundation only)
Date: 2026-09-17
```

## Segment 2 — Provider controls

Implement control records and transaction/control separation. Controls never increment purchase count.

**Execution Record:**
```text
Status: PASS WITH NOTES
Commit(s): none (not committed; awaiting review)
Files changed: see Segment 2 stop report
Migrations: alembic_tenant/versions/f2c3d4e5f6a7_fuel_source_controls.py (revises f1b2c3d4e5f6; not applied on this host)
Tests run: tests/test_fuel_segment_2.py + tests/test_fuel_segment_1.py + tests/test_fuel_segment_0a.py + Load parser / document-parse / audit writer regressions
Test result: Segment 2 14 passed; Segment 1 13 passed; Segment 0A 26 passed; Load parser / document-parse / audit writer regressions 150 passed, 3 skipped
Manual checks: not migrated; not deployed
Known risks / TODO:
  - Physical table name is `fuel_source_controls` (control rows vs `fuel_transactions` purchase/event rows)
  - `fuel_source_batches.provider_control_totals_json` removed; `fuel_source_controls` is the sole normalized control source of truth
  - Cross-table source_row_order uniqueness (transaction vs control) is enforced by app.services.fuel_ingestion, not a DB constraint spanning both tables
  - Reconciliation engine is not implemented
Architecture deviations: table name as above; no parser/reconciliation/workflow in Segment 2
Date: 2026-09-17
```

## Segment 3 — Historical truck/ownership resolution

Effective-dated unit and ownership/payee history; ambiguous/missing match -> review.

Also required when this segment runs: effective-dated card/account assignment at transaction datetime (Module Design §15.3).

Resolution uses documented transaction time (`transaction_datetime` when known, else source-local `transaction_date` as a date-level probe). Never fall back to current `trucks.unit_number`, current ownership, or current card assignment.

**Execution Record:**
```text
Status: PASS WITH NOTES
Commit(s): none (not committed; awaiting review)
Files changed: see Segment 3 stop report
Migrations: alembic_tenant/versions/f3d4e5f6a7b8_fuel_historical_resolution.py (revises f2c3d4e5f6a7; not applied on this host)
Tests run: tests/test_fuel_segment_3.py + tests/test_fuel_segment_2.py + tests/test_fuel_segment_1.py + tests/test_fuel_segment_0a.py + Load parser / document-parse / audit writer regressions
Test result: Segment 3 7 passed; Segment 2 14 passed; Segment 1 13 passed; Segment 0A 26 passed; Load parser / document-parse / audit writer regressions 150 passed, 3 skipped (combined Fuel+parser 210 passed, 3 skipped)
Manual checks: not migrated; not deployed
Known risks / TODO:
  - History tables are schema + pure resolver only; no Admin UI to edit unit renumbers/ownership/card moves yet
  - Date-only transactions use UTC midnight date probe for interval matching (not a timezone claim)
  - trucks gains uq_trucks_tenant_id_id so composite history FKs are valid
  - No automatic write-back of resolved truck_id/driver_id/payee onto fuel_transactions in this segment
  - Overlapping effective periods: no btree_gist exclusion constraints; write-path service validation
    (assert_history_rows_have_no_overlap / assert_proposed_history_row_no_overlap) plus resolver
    REVIEW_MULTIPLE_MATCH if overlaps exist. Half-open [effective_from, effective_to).
  - tests/test_trucks_trailers.py still DNS-fails pytest.truckerp.me on this host (pre-existing TenantContextMiddleware issue; unrelated to Segment 3 UniqueConstraint)
Architecture deviations: physical names truck_unit_number_history / truck_ownership_history / fuel_card_account_assignments
Date: 2026-09-17
```

## Segment 4 — O/O fuel pricing

Implement four pricing modes, effective dates, permissions, provider amount vs settlement charge separation.

**Execution Record:**
```text
Status: PASS WITH NOTES
Commit(s): none (not committed; awaiting review)
Files changed: see Segment 4 stop report
Migrations: alembic_tenant/versions/f4e5f6a7b8c9_fuel_oo_pricing_rules.py (revises f3d4e5f6a7b8; not applied on this host)
Tests run: tests/test_fuel_segment_{0a,1,2,3,4}.py + Load parser / document-parse / audit writer regressions
Test result: Fuel 0A–4: 76 passed; with Load parser/document-parse/audit_events_writer regressions: 230 passed, 3 skipped
Manual checks: not migrated; not deployed; no settlement posting
Known risks / TODO:
  - Pricing calculator + effective-dated rules only; no Admin UI / RBAC permission surface yet (permissions deferred to Fuel Ops / review UI)
  - No settlement/payroll posting in this segment
  - Overlapping pricing-rule periods: service validation (assert_oo_pricing_rules_have_no_overlap) + REVIEW_MULTIPLE_RULES; no btree_gist
  - percent_of_provider_discount stored as fraction in [0,1] (0.20 = 20% of provider discount)
  - Provider discount never inferred when source evidence absent
  - DATE_ONLY correction: never invent UTC midnight; requires provider_timezone and
    unambiguous full local-day rule coverage; otherwise REVIEW_AMBIGUOUS_DATE_ONLY
Architecture deviations: physical table fuel_oo_pricing_rules; provenance columns on fuel_transactions
Date: 2026-09-17
```

## Segment 5 — Fuel AI handoff contract + validator

Implement versioned JSON contract, provider rules, field rules, strict output schema, mechanical validator and parser-version persistence.

**Execution Record:**
```text
Status: PASS WITH NOTES
Commit(s): none (not committed; awaiting review)
Files changed: see Segment 5 stop report
Migrations: none (Segment 5)
Tests run: tests/test_fuel_segment_{0a,1,2,3,4,5}.py + test_fuel_models_metadata.py + Load parser/document-parse/audit regressions
Test result: Fuel 0A–5 + metadata: see stop report; combined with Load parser regressions: 247 passed, 3 skipped
Manual checks: not migrated; not deployed; no OpenAI live call; no BVD/Nationwide parsers
Known risks / TODO:
  - Contract + handoff builder + mechanical validator only; no production OpenAI wiring yet
  - Digital PDF path requires caller-supplied pdf_bytes_ref; RateCon acquisition classifier thresholds not copied into Fuel
  - Shared OCR/OpenAI transport reuse is architectural (available); Fuel does not call them in this segment
  - Provider-specific field rules for BVD/Nationwide deferred to Segments 6–7
Architecture deviations: none material
Date: 2026-09-18
```

## Segment 6 — Prove generic Fuel parser with BVD provider profile

**Interpretation (locked):** Segment 6 is **not** “build a BVD parser.”

It proves and extends the **one generic Fuel parser** using BVD as the first evidence-backed **provider profile/rules** (same principle as Load/Rate Confirmation: shared engine + profile/rules/schema → canonical output).

```text
PDF → shared acquisition/OCR → generic Fuel AI handoff + Fuel contract
    → BVD provider profile/rules → generic mechanical validator
    → fuel_transactions + fuel_source_controls
```

Structured BVD/T-Chek export: thin adapter only when an evidenced sample exists; otherwise **BLOCKED_BY_SOURCE_EVIDENCE** (do not invent the file layout).

Nationwide (Segment 7) must reuse this same engine with a Nationwide profile — not a second parser.

**Execution Record:**
```text
Status: PASS WITH NOTES
Commit(s): none (not committed; awaiting review)
Files changed: see Segment 6 stop report
Migrations: none
Tests run: test_fuel_segment_6.py + Fuel 0A–5 + Load parser regressions
Test result: Segment 6 12 passed; Fuel 0A–6 + metadata 105 passed; with Load parser regressions 259 passed, 3 skipped
Manual checks: not migrated; not deployed; no live OpenAI; structured T-Chek blocked by missing sample
Known risks / TODO:
  - BVD digital table row-splitting still AI/extraction-owned; Segment 6 proves profile mapping + layout anchors on evidenced fixture
  - No T-Chek/DAT sample in worktree → structured path BLOCKED_BY_SOURCE_EVIDENCE
  - Quantity UOM not printed on BVD 972201 sample → left null (no invention)
Architecture deviations: none — one Fuel parser + bvd_statement_v1 profile JSON
Date: 2026-09-18
```

## Segment 7 — Nationwide provider profile on the same Fuel parser

Add Nationwide **provider profile/rules** (row-type indicators, Canadian GST control evidence, CAD/USD/UOM quirks) to the **same** generic Fuel parser/handoff/validator. Do not create a Nationwide parser engine.

**Execution Record:**
```text
Status: PASS WITH NOTES
Commit(s): none (not committed; awaiting review)
Files changed: see Segment 7 stop report
Migrations: none
Tests run: test_fuel_segment_7.py + Fuel 0A–6 + Load parser regressions
Test result: Segment 7 11 passed; Fuel 0A–7 + metadata 116 passed; with Load parser regressions 270 passed, 3 skipped
Manual checks: not migrated; not deployed; no live OpenAI; Nationwide CSV companion BLOCKED_BY_SOURCE_EVIDENCE
Known risks / TODO:
  - PDF visual column collision (GST under txn columns on CARD_TOTAL) handled by row-type-first profile rules; full PDF table AI extraction still deferred
  - Per-row UOM not printed; litres/gallons applied only as evidenced currency fallback from statement footnotes/summary
  - Network mapped to merchant_network (not merchant_site) per evidence/design caution
Architecture deviations: none — nationwide_statement_v1 consumed by same fuel_provider_profile.py as BVD
Date: 2026-09-18
```

## Pre–Segment 8 hardening — generic profile layer (A–L)

Before Segment 8: deterministic `control_match_rules` (no whole-row substring CONTROL steal); amount-only → `INSUFFICIENT_TRANSACTION_EVIDENCE_AMOUNT_ONLY`; provider raw labels only in profile JSON; versioned `resolve_provider_profile_for_document` (0/1/many); layout-anchor presentation normalize; architecture guard executed in tests; Nationwide UOM/price-basis fallbacks profile-scoped + evidence-backed only. Segment 8 not started.

**Execution Record:**
```text
Status: PASS
Commit(s): none (not committed)
Tests: test_fuel_profile_hardening.py + Fuel 0A–7 + Load parser regressions → 281 passed, 3 skipped
Date: 2026-09-18
```

## Master provider-profiles JSON consolidation

Consolidate BVD + Nationwide into **one** master file `app/contracts/fuel_provider_profiles.json` with top-level keys exactly `BVD` and `NATIONWIDE` (one current evidenced profile section each; identity = `provider_code` + `profile_version` stamp, no `profile_code` / `statement_v1`). Generic `fuel_provider_profile.py` selects the provider section directly; layout anchors still gate recognition. No per-provider parser engines. Separate per-provider JSON files under `fuel_provider_profiles/` removed.

**Execution Record:**
```text
Status: PASS
Commit(s): none (not committed)
Date: 2026-09-18
```

## Segment 8 — Review queue UI/backend

Left source / right TruckERP presentation, Save & Next, Process → `READY_FOR_RECONCILIATION` only (Segment 9 reconciliation not implemented here). Append-only extraction corrections; `provider_raw` immutable; optimistic `review_version`; provider-neutral UI.

**Execution Record:**
```text
Status: PASS WITH NOTES
Commit(s): none (not committed; awaiting review)
Migrations: f5a6b7c8d9e0_fuel_review_corrections.py created, NOT applied
Tests: test_fuel_segment_8.py + Fuel 0A–7 + hardening + Load regressions + frontend vitest
Manual checks: not migrated; not deployed
Known risks / TODO:
  - Nationwide XXXXX… Total regex in fuel_controls.py remains Segment 9 follow-up
  - Document streaming currently resolves repo-relative source_storage_ref (fixtures/storage); production S3 keys via existing storage module can be extended later without changing review semantics
  - Summary/Finalize UI deferred with Segment 9–12
Architecture deviations: none — same review path for BVD and Nationwide
Date: 2026-09-18
```

## Segment 9 — Reconciliation engine

Every source transaction accounted exactly once; provider controls/currency totals validated; unresolved relationships block.

**Execution Record:**
```text
Status: CODED + CORRECTNESS PASS VERIFIED (worktree; not committed / not migrated / not deployed)
Files:
  - app/services/fuel_reconciliation.py (new)
  - app/routers/fuel.py (GET/POST /fuel/reconciliation/batches/{id})
  - app/schemas/fuel.py (FuelReconciliationOut/RunIn)
  - app/deps/fuel_rbac.py (fuel.reconciliation.view|run)
  - tests/test_fuel_segment_9.py (new)
Authority: fuel_transactions totals vs fuel_source_controls declared amounts only
  (Decimal; AI authority=false; no provider_control_totals_json; provider_raw immutable)
Outcomes: RECONCILED | RECONCILIATION_FAILED | BLOCKED
  Report stored on batch.problem_summary_json["reconciliation"]
  No finalization / financial-responsibility / settlement (Segment 10+)
Correctness pass (2026-09-19): VARIANCE is provider evidence only and never
  forces PASS on nonzero declared−calculated difference; invoice/statement/
  provider-declared totals require deterministic control_scope; GROUP_SUBTOTAL
  requires scope=GROUP + provider_control_identity + txn group membership;
  unresolved money-bearing UNKNOWN/OTHER transaction events / row roles block PASS
Architecture deviations: none — currencies reconcile independently; nonzero
  declared−calculated difference is FAIL until a proven provider rounding policy
  exists; provider VARIANCE rows are evidence only and never force PASS
Date: 2026-09-19
```

## Segment 10 — Classification and financial responsibility

Separate transaction category from who owes/pays it; cross-module routing for Toll/Lumper.

**Execution Record:** NOT STARTED

## Segment 11 — Manual driver entry + duplicate matching

Same canonical path; later provider source does not double-charge.

**Execution Record:** NOT STARTED

## Segment 12 — Settlement/payroll handoff

Only eligible resolved rows, multi-truck O/O drilldown, exact sum/idempotency.

**Execution Record:** NOT STARTED

## Segment 13 — Fuel Operations workspace

Transactions/imports/exceptions/provider connections under RBAC, dynamic per-row unit/currency display.

**Planned (not implemented by this docs update):**

- Multi-file provider upload UX (each file → independent `fuel_source_batches`).
- Streamed validation / SHA256 / shared document-safety before parse.
- Exact-file hard-stop duplicate modal/drawer (preserve current workspace focus).
- Same-provider invoice identity hard-stop / identity-conflict REVIEW UX.
- `View Existing Batch`, side-by-side `Compare`, `Skip Duplicate` / Cancel — no `Process Anyway`.
- Status / downstream financial-chain trace for the existing source.
- Provider identification against all evidenced master profiles, independent of enabled tenant connections.

Do **not** move these concerns into Segment 9 reconciliation or Segment 10 financial responsibility.

**Execution Record:** NOT STARTED

## Segment 14 — Audit/reversal/immutability

Full trace from provider source to money movement; no silent post-finalization mutation.

**Planned (not implemented by this docs update):**

- Transaction flagging (any Fuel transaction may be flagged without mutating source).
- Dispute / investigation case with append-only timeline.
- Evidence attachments linked to case + original transaction / source (never overwrite provider PDF).
- Provider credit / reversal / adjustment as **new linked** financial events.
- Immutable confirmed source facts after source review.
- Year-end traceability: original invoices ± credits/reversals/adjustments = net provider activity; settlement adjustments separate from provider source.

Do **not** move these concerns into Segment 9 or Segment 10.

**Execution Record:** NOT STARTED

## Segment 15 — End-to-end hardening / Gold readiness

Do not establish Fuel Gold merely because code compiles.

**Planned hardening requirements (not implemented by this docs update):**

- Concurrent duplicate upload race test (`tenant + SHA256` → one financial source only).
- DB source-hash uniqueness as second line of defense.
- Same file exact hard stop before parsing.
- Same provider + invoice matching hard duplicate.
- Same invoice with conflicting facts → `INVOICE_IDENTITY_CONFLICT` → REVIEW.
- No cross-provider duplicate suppression.
- Downstream posting idempotency.
- Crash / retry safety for async work **if** async is implemented (durable worker only).

Do **not** move these concerns into Segment 9 or Segment 10.

**Execution Record:** NOT STARTED

