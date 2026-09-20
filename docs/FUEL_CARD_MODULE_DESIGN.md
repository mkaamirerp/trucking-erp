# TruckERP Fuel / Fuel-Card Module Design

**Status:** Architecture source of truth — provider-controlled ingestion foundation; not implementation-complete and not Gold.

**Current supported/test providers:** BVD and Nationwide only.

**Purpose:** Define the Fuel/Card architecture from provider source evidence through review, later canonicalization, reconciliation, ownership, O/O settlement and posting. Fuel/Card is a money-moving subsystem. Unsupported providers, unknown layouts and guessed financial data are not allowed to enter the posting path.

---

# 1. Non-negotiable principles

## 1.1 Supported-provider whitelist

TruckERP does **not** provide a generic “upload any fuel statement and let AI figure it out” path.

Every provider and layout/interface version must be explicitly registered and approved.

```text
Supported provider + approved profile/version
        -> process

Unsupported provider / unknown version / unknown structure
        -> reject or review
```

A provider/profile may remain referenced historically after retirement, but a retired profile must not be used for new ingestion.

## 1.2 API first when a usable authorized API exists

If a provider exposes a usable production API that the fleet can authorize TruckERP to access, use that API as the production source.

Do not maintain a PDF parser for that provider merely because a statement PDF exists.

If no usable authorized API exists, use an explicitly approved digital PDF / CSV / structured-export profile.

Current foundation:

```text
BVD        -> approved digital PDF path
Nationwide -> approved digital PDF path
```

Future provider onboarding decides the source method from the actual customer-facing vendor contract, not from assumptions about the underlying payment network.

## 1.3 Provider-native evidence comes before TruckERP canonical meaning

The parser's first job is to capture what the provider actually supplied.

Do **not** make extraction depend on later accounting interpretation.

```text
source PDF / API / CSV
        ↓
provider profile/version
        ↓
classify document structure
        ↓
hydrate exact provider-native fields
        ↓
store immutable native evidence
        ↓
review/correction overlay
        ↓
LATER: canonical mapping / financial rules
```

## 1.4 Classify structure before hydrating fields

Providers can place transactions, subtotals, card totals, invoice totals, client blocks, legends and other structures in the same document.

The safe order is always:

```text
identify provider/profile
-> identify block/group
-> identify row/structure type
-> apply that structure's field contract
-> hydrate exact native fields
-> attach inherited group context
-> save source evidence
```

This prevents a control row from being interpreted as a purchase transaction.

## 1.5 Provider source is immutable

The original file/payload and extracted provider-native evidence are not rewritten to make downstream math balance.

Human review creates an overlay/correction record. It never edits the native record in place.

Posted financial history is corrected through audited adjustment/reversal, never silent mutation.

## 1.6 Business logic is backend authoritative

The frontend may dynamically choose provider-specific columns, labels, grouping and display order.

Authoritative financial rules belong in backend/service code. The browser must not be the only place where classification, reconciliation, O/O pricing or settlement rules exist.

## 1.7 No generic AI financial authority

AI may assist extraction only inside an approved provider profile.

Bad contract:

```text
Read this fuel statement and figure it out.
```

Allowed contract:

```text
This is BVD profile v1.
Classify this block/row.
Hydrate these exact approved BVD fields.
Return evidence.
Do not invent missing values.
```

AI/parser output never decides truck ownership, payee, O/O pricing, financial responsibility, settlement eligibility or posting.

---

# 2. Architecture layers

TruckERP keeps the source-evidence layer separate from later financial meaning.

```text
SUPPORTED PROVIDER REGISTRY
        ↓
IMMUTABLE SOURCE DOCUMENT / API PAYLOAD
        ↓
VERSIONED PARSE RUN
        ↓
SOURCE BLOCKS / GROUPS
        ↓
PROVIDER-NATIVE RECORDS
        ↓
APPEND-ONLY REVIEW / CORRECTION OVERLAY
        ↓
-------------------------------
LATER CONTROLLED PHASES
-------------------------------
        ↓
TRUCKERP CANONICAL RECORDS
        ↓
RECONCILIATION + RESOLUTION GATES
        ↓
FINANCIAL RESPONSIBILITY / O-O PRICING
        ↓
SETTLEMENT / POSTING
```

## 2.1 Source document and parser interpretation are different things

The same immutable PDF may be parsed later by a corrected provider profile.

Therefore provider/profile/version must belong to a **parse run**, not to the identity of the source file itself.

```text
PDF SHA-256 = same immutable evidence
    ├─ parse run: BVD v1
    └─ parse run: BVD v2
```

A new parser version never silently rewrites finalized financial history.

## 2.2 Card brand, backend rail and integration contract are different

There may be many white-label fuel-card sellers sitting on a small number of large processing systems. That is useful market context but it does not define TruckERP's access path.

If a carrier contracts with an XYZ card company that happens to use EFS underneath, TruckERP normally integrates with **XYZ's exposed interface**, not by bypassing XYZ and requesting the carrier's transactions directly from EFS.

Model separately when known:

```text
program/vendor used by fleet
underlying processing rail      # informational lineage
vendor interface/profile        # actual integration contract
merchant/acceptance network
```

Two EFS-backed vendors may expose completely different REST schemas, exports and PDFs. Reuse an adapter only after the external contract is proven to be identical.

Corporate ownership also does not prove one transaction format. WEX-owned EFS, Fleet One, TCH and T-Chek must remain technically distinct until real feed/statement evidence proves otherwise.

---

# 3. Provider profile/version contract

Every approved provider profile defines at minimum:

- stable provider code;
- profile/version;
- approval state (`approved`, `retired`);
- accepted source method(s);
- accepted document/interface signature;
- data-bearing block/group types;
- exact native field labels for each structure;
- row/control types;
- group/inherited-context behavior;
- required vs optional source fields;
- source evidence requirements;
- version-change detection;
- tests/fixtures required to approve the profile.

“100% known field extraction” means 100% of the **data-bearing fields and structural labels in the approved profile/version** are inventoried and handled.

Static marketing copy, logos, legal prose and notices remain preserved in the immutable source file but are not automatically hydration targets unless explicitly promoted into the profile.

---

# 4. BVD — first production baseline

BVD is the first provider used to establish the provider framework for Canadian production.

The approved fixture baseline is invoice `972201`.

## 4.1 Verified invoice/header values

```text
Invoice Number      972201
Invoice Date        2026-07-29
Start Date          2026-07-22
End Date            2026-07-28
Due Date            2026-07-30
Customer name       FIRST BASE FREIGHT LTD.
```

The customer name appears as an **unlabeled line** inside the `Client info` block. Do not invent a native `Client` field label.

## 4.2 BVD document blocks

Current fixture structures include:

```text
Invoice/header
Client info
Transactions for card <card-number>
Transaction table
Transaction-level SUBTOTAL rows
Page-1 summary/control structure
Grand Totals
Legend
```

Each structure has a first-class home in native storage.

## 4.3 Client info block

Exact labels observed:

```text
Client info
[unlabeled customer-name line]
Address:
Phone:
Email:
```

## 4.4 Card group is inherited context, not a transaction column

The source contains:

```text
Transactions for card 4237111
```

`4237111` is group context. It is **not** a per-row `Card` column in this BVD fixture.

Every transaction in that group references/inherits the card-group context.

## 4.5 Exact BVD transaction columns — 21

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

Do not replace these labels with convenience names in the native manifest.

## 4.6 Verified BVD transaction 1

Group context:

```text
Transactions for card 4237111
```

Transaction values:

```text
Auth Code          A204040667-TA
Driver Name        JASPREET CHOKAR
Unit #             1100
Date/time          2026-07-23 02:17:56
Site #             54228
Site Name/City     BOWMANVILLE
Prov/ST            ON
Prod               TA
QTY                719.50
Retail             2.2390
Billed             2.2390
Pre Tax AMT        1425.63
HST                185.33
Final AMT          1610.96
CUR                CN
```

## 4.7 Verified BVD transaction 2

Same card-group context:

```text
Transactions for card 4237111
```

Transaction values:

```text
Auth Code          A208448597-TA
Driver Name        JASPREET CHOKAR
Unit #             1104
Date/time          2026-07-27 13:38:39
Site #             58073
Site Name          BVD NIAGARA
Site City          Niagara on the Lake
Prov/ST            ON
Prod               TA
QTY                754.50
Retail             2.3990
Billed             2.3990
Pre Tax AMT        1601.81
HST                208.24
Final AMT          1810.05
CUR                CN
```

A missing per-row Card value is not a defect here because card identity is inherited from the `Transactions for card` group.

## 4.8 BVD page-1 control structure — frozen for this fixture

Each transaction is followed by a transaction-level control row labeled exactly:

```text
SUBTOTAL
```

Observed post-transaction summary/control sequence:

```text
SUBTOTAL | TA
Card #   | TF
4237111  | Fuel Total
[blank]  | DF
[blank]  | Sub Total
```

This is the complete observed page-1 summary/control label sequence for the approved fixture.

Important relationship:

- `Transactions for card 4237111` is transaction-group context;
- `Card #` is a summary/control label;
- the following summary line carries `4237111` and `Fuel Total`;
- the summary card value must be related explicitly to the transaction-group key;
- none of these control structures creates a purchase transaction.

## 4.9 BVD Grand Totals — exact columns

Heading:

```text
Grand Totals
```

Columns:

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

Verified Grand Total values:

```text
QTY              1,474.00
PRE TAX AMT      3,027.44
HST              393.57
GST              0.00
PST              0.00
QST              0.00
DISC RATE        0.00
DISC AMT         0.00
FINAL AMOUNT     3,421.01
CUR              CN
```

Observed Grand Totals row-label set:

```text
TA
TF
DF
Manual
Express
Grand Total
```

`Manual` and `Express` are Grand Totals row labels in this fixture. They are **not** Legend-backed BVD product codes.

## 4.10 BVD Legend block

Exact labels:

```text
Legend
Code
Product Name
```

Observed code/value pairs:

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

The Legend is source evidence, not a transaction table.

## 4.11 BVD extraction order

```text
recognize BVD profile/version
-> classify block/group
-> classify row type
-> apply exact structure contract
-> hydrate exact native values
-> inherit card-group context where applicable
-> store immutable native evidence
-> create review overlay only if needed
```

Do not infer missing financial values during this phase.

---

# 5. Nationwide — second provider baseline

Nationwide proves the framework can support a materially different document without forcing BVD-shaped tables.

The current Nationwide fixture has been re-verified against the PDF.

## 5.1 Nationwide source blocks

Observed data-bearing structures:

```text
PROVIDER / CONTACT BLOCK
ACCOUNT INFORMATION
BILLING SUMMARY
TRANSACTION BREAKDOWN BY CARD
TRANSACTION
CARD_TOTAL
```

## 5.2 ACCOUNT INFORMATION — exact labels

```text
Customer Name
Account Code
Invoice Number
Invoice Start Date:
Invoice End Date:
Due Date:
Email 1
Email 2
Email 3
```

The fixture also contains:

```text
CAD Pmt Method: Banking; USD Pmt Method: Banking
```

Preserve this as source evidence. Do not invent native labels not printed by Nationwide.

## 5.3 BILLING SUMMARY — exact labels

```text
Total Volume
Total Ex-GST & PST
GST
PST
Subtotal
This Weeks Invoice
Total Outstanding Balance
```

The source presents Canadian and U.S. values in separate visual currency/UOM contexts.

## 5.4 TRANSACTION BREAKDOWN BY CARD — exact columns

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

Earlier convenience labels such as `Account`, `Card`, `Unit`, `Province`, `State` and `Unit Price` are not native-field labels for this approved fixture.

Unlike BVD, Nationwide `Account Code` and `Card Number` are actual per-transaction columns in this fixture.

## 5.5 Verified Nationwide Canadian transaction

```text
Account Code       20250522B
Card Number        XXXXX87195
Unit #             788
Date               2026-06-09
City               NIAGARA-ON-THE-LAKE
Pr/St              ON
Product            DIESEL
Volume             674.17
Ex-GST ($/U)       $1.659
Total              $1,263.85
Network            Esso
Currency           CAD
USA Discount       $0.00
Missed Disc        $0.00
OON Fees           $ -
```

Its following control row is separate:

```text
XXXXX87195 Total
GST $145.4
QST $0
Volume 674.17
Total $1,263.85
USA Discount $0.00
Missed Disc $0.00
```

## 5.6 Verified Nationwide U.S. transaction

```text
Account Code       20250522B
Card Number        XXXXX07588
Unit #             794
Date               2026-06-08
City               PAULSBORO
Pr/St              NJ
Product            DIESEL
Volume             154.27
Ex-GST ($/U)       $4.685
Total              $722.75
Network            TA-Petro
Currency           USD
USA Discount       $34.56
Missed Disc        $0.00
OON Fees           $ -
```

The corresponding control begins:

```text
XXXXX07588 Total
```

and is stored/classified as `CARD_TOTAL`, not as a transaction.

## 5.7 Nationwide control-row rule

Classify `CARD_TOTAL` before interpreting label/value positions.

Explicit control labels own their values:

```text
GST <value>
QST <value>
```

Never reinterpret those values as Date, City, Pr/St, Product, Volume or transaction Total because of x-position.

---

# 6. PostgreSQL / JSONB native-evidence storage model

Postgres + JSONB is the current storage foundation.

The exact migration may adapt to existing TruckERP naming conventions, but the structural rules below are locked.

## 6.1 Provider whitelist

```sql
CREATE TABLE fuel_provider_profile (
  provider         text NOT NULL,
  profile_version  text NOT NULL,
  status           text NOT NULL CHECK (status IN ('approved','retired')),
  PRIMARY KEY (provider, profile_version)
);
```

A foreign key proves a profile exists. New-ingestion code must additionally enforce `status='approved'` so retired profiles remain readable historically but cannot start new parses.

Maintain an allowed-structure registry per provider/profile so unknown structure types cannot be silently accepted.

## 6.2 Immutable source document

The original file/payload identity is separate from provider interpretation.

Conceptual table:

```sql
CREATE TABLE fuel_source_document (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL,
  source_type   text NOT NULL,
  file_sha256   bytea NOT NULL,
  storage_ref   text NOT NULL,
  original_name text,
  content_type  text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, file_sha256),
  CHECK (octet_length(file_sha256) = 32)
);
```

Store the document in object/file storage. Postgres stores the cryptographic hash and storage reference, not the PDF bytes.

## 6.3 Versioned parse run

A parse run identifies the interpretation applied to an immutable source document.

Conceptual fields:

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

A source document can therefore be reparsed by an explicitly selected newer profile without changing the original evidence.

## 6.4 Blocks/groups are first-class

A simple `label/raw_value` group table is too narrow because providers contain complex source blocks.

Conceptual structure:

```text
FuelNativeBlock
- id
- tenant_id
- parse_run_id
- parent_block_id nullable
- block_sequence
- block_type
- provider_native_fields JSONB
- inherited_context_fields JSONB
- raw_text / raw_source_evidence
- page / coordinates where practical
- confidence
- requires_review
```

Examples:

```text
BVD Client info
BVD Transactions for card 4237111
BVD page-1 controls
BVD Grand Totals
BVD Legend
Nationwide ACCOUNT INFORMATION
Nationwide BILLING SUMMARY
Nationwide TRANSACTION BREAKDOWN BY CARD
```

## 6.5 Provider-native records

Conceptual structure:

```text
FuelNativeRecord
- id
- tenant_id
- parse_run_id
- block_id
- seq
- page
- structure_type
- fields JSONB
- inherited_context_snapshot JSONB
- raw_text / raw_source_evidence
- confidence
- requires_review
```

`UNIQUE(parse_run_id, seq)` or the equivalent ordered identity must prevent duplicate record position inside the same parse run.

## 6.6 `fields` must be an ordered array

Do not store native source fields as a JSON object.

Use:

```json
[
  {"label":"QTY","raw":"719.50","evidence":{}},
  {"label":"Pre Tax AMT","raw":"1,425.63","evidence":{}},
  {"label":"HST","raw":"185.33","evidence":{}}
]
```

Reasons:

- JSON object key order is not the source-column contract;
- duplicate labels would collapse in an object;
- ordered arrays preserve source order;
- repeated labels can remain distinct.

Every provider-native `raw` value is stored as a **JSON string** at this layer.

That preserves source spelling/formatting such as:

```text
1,425.63
0.0000
CN
XXXXX87195
```

Numeric interpretation belongs to later controlled mapping/validation.

## 6.7 Native records are append-only

Application roles must not UPDATE or DELETE immutable native evidence after insert.

Use grants and/or database triggers to enforce this rule.

## 6.8 Review/correction is an append-only overlay

Review must support more than structure reclassification.

Conceptual actions include:

```text
CONFIRM
RECLASSIFY
FIELD_CORRECTION
REJECT
```

Example correction payload:

```json
{
  "field": "Unit #",
  "native_raw": "110A",
  "reviewed_raw": "1104",
  "reason": "PDF visual confirmation"
}
```

The native source remains untouched.

The review layer stores reviewer identity, reason and timestamp.

## 6.9 Tenant isolation

Repeat `tenant_id` where it keeps row-level-security policies clear.

Relationships among document, parse run, block, record and review must be tenant-safe through composite foreign keys and/or RLS/trigger checks. A programming error must not be able to attach Tenant A evidence to Tenant B structures.

## 6.10 Initial indexing

Do not add a GIN index on native JSONB fields yet.

The current access pattern is ordered document review, so initial indexes should focus on:

```text
tenant_id
(document_id / parse_run_id, sequence)
block_id
provider/profile/version
review state
```

Add JSON search indexes only when a real query pattern requires them.

## 6.11 Native evidence is not the settlement ledger

These native tables preserve evidence and review history. They do not become settlement/payroll entries directly.

Later canonical records are derived from approved/reviewed source evidence.

---

# 7. Dynamic provider review UI

The right-side review view is provider-specific by design.

BVD source-review mode should render the BVD group context and exact native labels.

Nationwide source-review mode should render its exact native transaction columns.

There is no requirement for both provider tables to have identical columns.

The frontend may later present friendly TruckERP labels in a separate canonical/operational view, but native-source review must not confuse presentation labels with provider labels.

For document sources:

```text
LEFT  -> immutable source PDF
RIGHT -> provider-native extracted structures/records
```

`Save & Next` means source review only. It does not post money.

---

# 8. Current phase boundary

The current implementation goal is **provider-native extraction control**, not price/tax/O-O arithmetic.

Current phase:

```text
1. Identify provider/profile
2. Classify exact source structures
3. Hydrate exact provider-native fields
4. Store immutable document/block/row evidence
5. Preserve group/inherited context
6. Review/correct through append-only overlays
7. Prove field + structural completeness with fixtures/tests
```

Do not claim that a price is tax-inclusive, ex-tax, settlement price, discount basis, etc. merely to complete extraction.

Those semantic and mathematical rules are a later phase after BVD and Nationwide native extraction are stable.

---

# 9. Later canonical and financial architecture

The existing Fuel/Card financial decisions remain valid but are downstream from native evidence.

## 9.1 Transaction classification is separate from financial responsibility

First decide what the provider transaction is; separately decide who owes/pays it.

A fuel card can carry Fuel, DEF, Scale, Cash Advance, product purchases, repair/service, parking, toll, lumper and other activity.

## 9.2 Transaction date/time is authoritative

Historical truck/unit ownership, O/O/payee relationship, pricing agreement and settlement eligibility use the transaction date/time, not invoice date, import time or current relationships.

## 9.3 Unit number is not permanent truck identity

Use permanent `truck_id` plus effective-dated unit-number history.

```text
provider unit snapshot + transaction date/time
        -> exactly one truck_id
```

Zero or multiple matches require review.

## 9.4 Truck ownership / O/O payee is effective-dated

When a truck is added, ownership must be explicit: company vs owner-operator (and which O/O/payee/business).

A truck can belong to an O/O even when a different driver operates it. Driver employment type does not override truck commercial responsibility.

## 9.5 O/O pricing agreement

Later supported modes include:

- pump price / no provider discount passed through;
- full provider/company discount;
- fixed cents per litre/gallon passed through;
- percentage of provider discount passed through.

Percentage means percentage of provider discount, not percentage of pump price.

Pricing belongs to the O/O/payee settlement relationship and is effective-dated.

## 9.6 Company vs O/O financial responsibility baseline

Company truck/company responsibility:

- fuel/DEF/company operating product -> company expense;
- coolant/oil/additive/product -> company expense, no driver deduction;
- cash advance -> driver receivable/deduction under policy.

O/O truck/O/O responsibility:

- fuel -> O/O charge under effective agreement;
- DEF/product/coolant/oil/additive -> O/O deduction under policy;
- cash advance -> O/O/payee unless explicitly driver-specific by policy.

Lumper and toll may originate in Fuel/Card evidence but route to their owning downstream modules/policies.

## 9.7 Strict reconciliation

Every provider transaction/control must be accounted for exactly once.

Currencies reconcile independently.

Never create a fake CAD+USD provider total.

A matching invoice grand total never excuses wrong unit/date/card/control assignment.

No provider row amount is changed to force equality.

## 9.8 Settlement/payroll handoff

Provider amount and contractual O/O charge are separate values.

Settlement includes only transactions that have passed all required source, reconciliation, truck/ownership, responsibility and pricing gates.

Multi-truck O/O settlement must support:

```text
O/O/payee
  -> unit
      -> provider transaction detail
  -> total Fuel/Card deduction
```

---

# 10. Confirmed implementation issues from archive audit

The uploaded Fuel code audit found real defects that remain blockers before final financial posting.

## 10.1 O/O responsibility gate conflicts with locked ownership design

`app/services/fuel_oo_pricing.py` can treat `is_company_driver=True` as a reason to suppress O/O charging.

Commercial truck/fuel responsibility must decide who pays; driver employment type must not override an O/O-owned truck agreement.

## 10.2 DATE_ONLY historical resolution can choose the wrong owner/payee

`app/services/fuel_historical_resolution.py` anchors date-only values in a way that can cross local-date boundaries.

Use provider/source timezone full-day resolution before financial use.

## 10.3 Reconciliation can incorrectly combine currencies

A control without currency can currently allow CAD and USD values to sum together and pass.

This must be impossible.

## 10.4 Unresolved control rows can authorize PASS

Control records marked review-required or reclassified away from a valid control role can still participate incorrectly in reconciliation.

Unresolved controls must block financial PASS.

## 10.5 Review role change does not truly reclassify financial use

Changing a reviewed structure/row role can leave the underlying reconciliation set unchanged.

The append-only review overlay must become authoritative for effective reviewed structure without mutating native evidence.

## 10.6 O/O calculator accepts impossible inputs/outcomes

Negative quantity, discount exceeding price and negative charge outcomes have been observed returning calculated status.

Hard numeric validation is required before settlement.

## 10.7 Credit/refund/reversal sign discipline is not enforced end-to-end

Positive credit/refund/reversal amounts can currently degrade to warning behavior rather than hard review/block logic.

## 10.8 Review readiness is too shallow

`READY_FOR_RECONCILIATION` must reflect all unresolved conditions, not only pending row counts.

## 10.9 Audit test snapshot

At the audit checkpoint, 102 tests passed. Three additional modules could not collect in that audit runtime because `asyncpg` was absent there while the repository requirements included `asyncpg==0.31.0`; that collection issue was treated as audit-environment related, not a confirmed repository defect.

---

# 11. Future provider onboarding

Do not onboard a provider because its card logo resembles an existing network.

For every future provider/program answer:

1. What exact vendor/program does the carrier contract with?
2. What interface can the carrier actually authorize TruckERP to access?
3. If an approved production API exists, use API as the preferred source.
4. Otherwise what PDF/CSV/export source is approved?
5. What are the exact document/API blocks/groups?
6. Which values are inherited group context versus per-record fields?
7. What are the exact native labels/keys?
8. What are the row/control types?
9. What source evidence is retained?
10. What profile/version-change detection is required?
11. What fixtures/tests prove field and structural completeness?

The underlying EFS/Comdata/WEX/etc. rail may be retained as metadata but does not grant access and does not define the vendor adapter boundary.

---

# 12. BVD foundation completion gate

BVD is not complete merely because two transaction rows parse.

Required before calling the BVD native-extraction foundation complete:

```text
[ ] Approved BVD profile/version exists
[ ] Every data-bearing block/group in approved fixtures is inventoried
[ ] Exact invoice-header labels are frozen
[ ] Client info block is represented without inventing source labels
[ ] Transactions for card is stored as group context
[ ] Child transactions inherit/reference that context
[ ] Exact 21 transaction columns are frozen
[ ] Transaction SUBTOTAL rows are classified as controls
[ ] Full observed page-1 control sequence is frozen
[ ] Card # summary relationship to card-group context is represented
[ ] Grand Totals exact 11 columns are frozen
[ ] Grand Totals row labels are inventoried
[ ] Manual / Express are not treated as Legend product codes
[ ] Legend block and observed code/product pairs are preserved
[ ] Native raw values are strings in ordered field arrays
[ ] Native evidence is append-only
[ ] Review/correction is append-only
[ ] Unknown fields/layout/structure changes go to review
[ ] Control rows cannot become transactions silently
[ ] Source-review UI renders BVD structure/context correctly
[ ] Field-completeness tests exist
[ ] Structural-completeness tests exist
[ ] Document-level regression fixtures exist
[ ] Unsupported/generic fallback cannot silently post money
```

Only after the BVD foundation is stable does Nationwide validate framework reuse. Only after both native profiles are stable do semantic/canonical math and financial posting become the next implementation focus.

---

# 13. Architecture lock summary

1. Supported providers only; no generic fuel-statement posting.
2. BVD first, Nationwide second.
3. API first when a usable authorized production API exists.
4. Classify source structure before hydrating fields.
5. Store provider-native evidence before interpreting financial meaning.
6. Source document, parse run, block/group, record and review are separate concepts.
7. Native raw values stay strings in ordered JSONB field arrays.
8. Native evidence and review history are append-only.
9. Provider-specific review UI is expected; source columns do not need to match across vendors.
10. Backend processing rail is metadata, not an access shortcut.
11. Canonical mapping, math, reconciliation and settlement are later controlled layers.
12. Financial business logic is backend authoritative.
13. Every money path remains blocked until required gates pass.
14. Posted history is never silently rewritten.
