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

# 1. Locked implementation sequence

The implementation sequence is now:

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
THEN
K. canonical semantic mapping
L. reconciliation / financial gates
M. historical truck/ownership resolution
N. O/O pricing / financial responsibility
O. settlement / posting / cross-module routing
```

Do not pull later semantic/math work forward merely because the source contains prices, taxes or totals.

---

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
