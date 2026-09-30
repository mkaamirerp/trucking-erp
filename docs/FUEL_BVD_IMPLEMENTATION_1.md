# Fuel / BVD — Implementation 1

**Status:** LOCKED — amended 2026-09-29 (staged lifecycle + legacy compatibility)
**Scope:** BVD source extraction, source reconciliation, unit resolution, human review, and Process gate.  
**Goal:** upload an approved BVD PDF/CSV, preserve every BVD source value exactly, prove all parsed money reconciles to the provider totals, flag unresolved unit numbers immediately, resolve those units without corrupting source evidence, then allow the user to Process.  

This document does **not** authorize payroll, HR, dispatch, settlement, or accounting-posting behavior.

---

# 1. Locked workflow

The BVD workflow is intentionally simple:

```text
UPLOAD PDF / CSV
      ↓
PARSE
      ↓
fuel_bvd_import_stage  (temporary staging — not permanent fuel_bvd)
      ↓
review / corrections / effective accepted values
      ↓
RUN SOURCE MONEY VALIDATIONS (reconciliation)
      ↓
FLAG UNRESOLVED UNIT NUMBERS
      ↓
SHOW PARSED RESULT + VALIDATIONS
      ↓
HUMAN CHECK
      ↓
OPEN ORIGINAL PDF ONLY IF NEEDED
      ↓
RESOLVE UNIT EXCEPTIONS
      ↓
PROCESS
      ↓
permanent fuel_bvd  (accepted values)
      ↓
fuel_source_batch  →  fuel_transactions / fuel_source_controls
      ↓
classification (may continue after Process commit)
```

**Current PDF path (locked):** upload does **not** write permanent `fuel_bvd` or `fuel_source_batches` until the user successfully **Process**es from staging.

The review page is **results-first**. It is not required to show the PDF side-by-side.

The original BVD PDF must remain available from an icon/button for spot-checking.

Before Process, TruckERP must answer three questions:

1. Did TruckERP parse the source correctly?
2. Does every penny reconcile through transaction, unit, product, and BVD provider totals?
3. Is every non-zero source unit resolved either to a real TruckERP asset or to a Fuel-only external-use record?

---

# 1A. Current staged BVD source lifecycle (authoritative)

This section describes the **current** BVD implementation on `feat/fuel-card`, not pre-staging behavior.

## Upload and pre-Process authority

1. **Current BVD upload does NOT immediately create permanent `fuel_bvd`.**

2. **Current BVD upload does NOT create `fuel_source_batches`.**

3. **Before Process**, authority for in-flight BVD imports is:

   - `fuel_bvd_import_stage` (`status = ACTIVE`, not expired)
   - `fuel_bvd_stage_row` (parsed source rows)
   - `fuel_bvd_stage_field_correction` (append-only review corrections)
   - **effective / accepted review values** (`build_effective_bvd_rows` + reconciliation)

4. **Discard** and **expired-stage purge** remove staging rows (hard delete). They are not a separate long-lived “cancelled import” status.

## Successful Process (staged path)

At successful **Process** (`process_stage_to_permanent`), in one transaction:

1. Reconcile **effective** stage rows (money gate).
2. Run duplicate gate (`permanent_only`).
3. Persist immutable source evidence (permanent PDF storage).
4. Create permanent **`fuel_bvd`** rows using **accepted** field values (`review_status = SOURCE_REVIEWED`).
5. Create **`fuel_source_batch`** and project **`fuel_transactions`** / **`fuel_source_controls`**.
6. Run canonical money gate.
7. **Finalize** the canonical batch (`status = FINALIZED`, `finalized_at` set).
8. **Commit**.
9. Remove staging rows/files.
10. **Classification** may run afterward (post-commit backfill); it is not required to complete Process.

## Process timestamps (staged path)

5. Current staged Process creates:

   - `fuel_source_batches.status = FINALIZED`
   - `fuel_source_batches.finalized_at` (UTC)

6. **`fuel_source_batches.finalized_at`** is the strongest current timestamp meaning:

   > this staged Fuel import successfully completed Process (canonical batch committed).

7. **`fuel_bvd.reviewed_at`** remains **source-review metadata** on permanent rows. It must **not** be treated silently as the authoritative **Process** timestamp for new staged imports (dashboard metrics, operational “processed” counts, or settlement handoff).

**Implementation reference:** `app/services/fuel_bvd_stage.py` (`process_stage_to_permanent`), `app/services/fuel_bvd_canonical_projection.py` (`finalize_batch`).

---

# 1B. Legacy BVD compatibility

Older tenant data may exist where permanent **`fuel_bvd`** rows were created **without** the staging path, or where Process completed **without** a canonical batch.

## Legacy signals

- Open imports: `fuel_bvd` **HEADER** with `review_status` **`PENDING`** or **`IN_REVIEW`** (no active stage).
- Processed history: `fuel_bvd.review_status = SOURCE_REVIEWED` with **no** matching `fuel_source_batches` row (`source_import_ref` = import id).

## Locked rules

- Legacy rows remain **readable**; do not rewrite historical source evidence.
- Do **not** manufacture `fuel_source_batches` retroactively for legacy imports.
- Do **not** invent `finalized_at` values for legacy imports.
- Legacy open **`PENDING` / `IN_REVIEW`** imports may remain **actionable** (review + Process via legacy path where applicable).
- Legacy **`SOURCE_REVIEWED`** imports remain **history**.
- Legacy processed imports **without** authoritative batch `finalized_at` must **not** be silently counted as newly Processed using `MAX(fuel_bvd.reviewed_at)` (operational dashboard uses `finalized_at` for staged canonical Process only).

## Current vs legacy Process

| Path | When | Permanent `fuel_bvd` | Canonical batch |
|------|------|----------------------|-----------------|
| **Current staged** | Active `fuel_bvd_import_stage` | Created at Process with accepted values | Created and **FINALIZED** in same transaction |
| **Legacy** | No active stage; rows already in `fuel_bvd` | Updated to `SOURCE_REVIEWED` at Process | **Not** created by legacy `process_bvd_import_review` |

New development should assume the **staged** path. CSV intake (when resumed) must use the **same** staging / review / Process architecture as PDF.

---

# 2. Provider evidence vs accepted structured source (Fuel module)

BVD is one **provider adapter** into the shared Fuel module. The business contract matches
`docs/FUEL_CARD_MODULE_DESIGN.md` (immutable file/payload evidence; structured operational rows):

| Layer | Role |
|--------|------|
| **Original PDF / payload** | Immutable provider evidence (storage ref + hash). Never rewritten by review. |
| **Stage parser output** | Temporary machine interpretation (`fuel_bvd_stage_row` + optional `fuel_bvd_stage_field_correction`). |
| **Human-reviewed effective stage** | Accepted structured representation while in review (`build_effective_bvd_rows`). |
| **Process** | Commits that accepted representation to permanent `fuel_bvd`, `fuel_source_batch`, `fuel_transactions`, and controls. |

After **Process**, each `fuel_bvd` row holds the **accepted** field values (what reconciled and was approved), not a
parallel “parser column + permanent overlay” split. Parser mistakes are not promoted as provider facts.

`fuel_bvd_field_correction` remains for **post-Process** authorized amendments only (not for replaying stage parser
review onto permanent rows).

Rows from the same source file share the same `import_id`.

Known structural row types:

```text
HEADER
TRANSACTION
EXPRESS_TRANSACTION
TRANSACTION_SUBTOTAL
PAGE1_SUMMARY
GRAND_TOTAL
LEGEND
```

Operational asset/unit resolution and charge classification are separate Fuel concerns and do not rewrite accepted
source money or the stored PDF evidence.

---

# 3. Source-fidelity rule

BVD source fields are stored as **TEXT**.

Examples:

```text
PDF:  1,425.63
DB:   "1,425.63"

PDF:  0.0000
DB:   "0.0000"

PDF:  2026-07-29 00:00:00
DB:   "2026-07-29 00:00:00"

PDF:  Unit # = 1104
DB:   unit_number = "1104"
```

Do not remove commas, trailing zeros, provider abbreviations, product codes, unit numbers, or source formatting before saving.

Typed/normalized values used for validation are derived in backend services only and must never rewrite the source strings.

---

# 4. BVD invoice/header fields

Verified BVD invoice/header source values:

```text
Invoice Number
Invoice Date
Start Date
End Date
Due Date
Client Name
Address
Phone
Email
Transactions for card
HST #
QST #
```

Database columns:

```text
invoice_number
invoice_date
start_date
end_date
due_date
client_name
client_address
client_phone
client_email
card_number
hst_number
qst_number
```

`card_number` stores the BVD value belonging to `Transactions for card`.

---

# 5. Exact BVD transaction fields — 21

The source contract is exactly:

```text
1.  Auth Code
2.  Driver Name
3.  Unit #
4.  Date
5.  Site #
6.  Site Name
7.  Site City
8.  Prov/ST
9.  Prod
10. QTY
11. Retail
12. Billed
13. Pre Tax AMT
14. HST
15. GST
16. PST
17. QST
18. Disc Rate
19. Disc AMT
20. Final AMT
21. CUR
```

SQL-safe columns:

```text
auth_code
driver_name
unit_number
transaction_date
site_number
site_name
site_city
prov_st
prod
qty
retail
billed
pre_tax_amt
hst
gst
pst
qst
disc_rate
disc_amt
final_amt
cur
```

`Driver Name` is source evidence only. BVD does not know TruckERP's Driver/People database.

`Unit #` is also source evidence only. A BVD unit number is **not proof that a TruckERP Asset already exists**.

---

# 6. BVD controls / summary rows

Known BVD control labels include:

```text
SUBTOTAL
Card #
Fuel Total
DF
Sub Total
```

Control rows are provider checks, not transaction detail.

Do not double-count them as purchases.

Where a control row has an unambiguous meaning, TruckERP may compare it against computed transaction totals.

If a control row is absent, the check is:

```text
N/A
```

not `FAIL`.

---

# 7. BVD Grand Totals

Exact Grand Total columns:

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

`final_amount` is separate from transaction `final_amt` because BVD uses different source labels.

Zero-value `Manual` and `Express` rows are neutral.

A future non-zero `Manual` or `Express` amount must never be silently discarded. Preserve it and block Process until its provider meaning/allocation is verified.

---

# 8. BVD Legend

Verified BVD legend:

```text
TF = Trailer
TA = Tractor
DF = DEF
S  = Scale
C  = Cash
AD = Additive
O  = Oil
L  = Lubricant
```

Legend rows use:

```text
row_type = LEGEND
```

During source reconciliation, product codes remain exactly as BVD provides them.

Do not convert these source codes into payroll/accounting categories during this step.

Unknown future product codes must be preserved and included in reconciliation rather than dropped.

---

# 9. TruckERP-owned source metadata

Allowed source/audit metadata includes:

```text
id
tenant_id
import_id
row_type
source_file_name
source_file_sha256
source_storage_ref
source_page
source_row_number
uploaded_at
uploaded_by
processing_started_at
processing_completed_at
processing_duration_ms
processed_by
parser_version
parse_status
review_status
reviewed_at
reviewed_by
review_reason
extraction_warnings
created_at
updated_at
```

These fields describe source processing/review only.

---

# 10. Operational fields must NOT be written into fuel_bvd

Do not put operational linkage/financial-decision fields directly into the immutable source table, including:

```text
truck_id
driver_id
owner_operator_id
payee_id
truck_match_status
driver_match_status
ownership_resolved_at
matched_at
company / O/O ownership flag
fuel responsibility
fuel discount rule
calculated discount
O/O fuel charge
payroll deduction
settlement amount
reconciliation result
posting result
functional / FX-converted accounting amount
```

Those decisions belong outside the source evidence.

---

# 11. Locked fuel_bvd source table shape

```sql
CREATE TABLE fuel_bvd (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id               BIGINT NOT NULL,
    import_id               UUID NOT NULL,
    row_type                TEXT NOT NULL,

    invoice_number          TEXT,
    invoice_date            TEXT,
    start_date              TEXT,
    end_date                TEXT,
    due_date                TEXT,
    client_name             TEXT,
    client_address          TEXT,
    client_phone            TEXT,
    client_email            TEXT,
    card_number             TEXT,
    hst_number              TEXT,
    qst_number              TEXT,

    auth_code               TEXT,
    driver_name             TEXT,
    unit_number             TEXT,
    transaction_date        TEXT,
    site_number             TEXT,
    site_name               TEXT,
    site_city               TEXT,
    prov_st                 TEXT,
    prod                    TEXT,
    qty                     TEXT,
    retail                  TEXT,
    billed                  TEXT,
    pre_tax_amt             TEXT,
    hst                     TEXT,
    gst                     TEXT,
    pst                     TEXT,
    qst                     TEXT,
    disc_rate               TEXT,
    disc_amt                TEXT,
    final_amt               TEXT,
    cur                     TEXT,

    row_label               TEXT,
    product                 TEXT,
    final_amount            TEXT,
    legend_code             TEXT,
    legend_product_name     TEXT,

    source_file_name        TEXT,
    source_file_sha256      TEXT,
    source_storage_ref      TEXT,
    source_page             INTEGER,
    source_row_number       INTEGER,

    uploaded_at             TIMESTAMPTZ,
    uploaded_by             TEXT,
    processing_started_at   TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    processing_duration_ms  BIGINT,
    processed_by            TEXT,
    parser_version          TEXT,
    parse_status            TEXT,

    review_status           TEXT,
    reviewed_at             TIMESTAMPTZ,
    reviewed_by             TEXT,
    review_reason           TEXT,
    extraction_warnings     JSONB,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Any operational-resolution table must be separate and follow existing TruckERP tenant conventions.

---

# 12. Authoritative source reconciliation

Source validation runs on the backend and is required before Process.

Use `Decimal`, never binary float.

Source TEXT is parsed to Decimal only for calculations.

## Additive transaction fields

For `row_type = TRANSACTION`, additive fields are:

```text
qty
pre_tax_amt
hst
gst
pst
qst
disc_amt
final_amt
```

Primary transaction charge:

```text
final_amt
```

Do **not** sum:

```text
retail
billed
disc_rate
```

## Per-unit math

For every exact BVD `unit_number`:

```text
unit_product_total = SUM(transaction.final_amt for unit + product)
unit_total         = SUM(transaction.final_amt for unit)
```

All product totals inside that unit must equal the same unit total.

## All-unit math

```text
all_unit_total = SUM(all unit totals)
```

This must equal:

```text
SUM(all transaction.final_amt)
```

## Product math

Independently group all transactions by exact BVD `prod` and sum:

```text
qty
pre_tax_amt
hst
gst
pst
qst
disc_amt
final_amt
```

Compare the computed product values to matching BVD provider Grand Total product rows.

## Provider Grand Total

Compare transaction sums against the provider `Grand Total` row for:

```text
qty
pre_tax_amt
hst
gst
pst
qst
disc_amt
final_amount
```

Core final-amount equation:

```text
SUM(transaction.final_amt)
        ==
SUM(unit totals)
        ==
SUM(product totals)
        ==
BVD Grand Total final_amount
        ==
provider invoice total where explicitly available
```

Every required path must agree exactly.

## Exact-cent rule

No float tolerance.

```text
difference = 0.00  -> PASS
difference = 0.01  -> FAIL
```

## Currency

Preserve provider currency exactly, including values such as `CN`.

Do not convert it to CAD during source reconciliation.

Do not add incompatible source currencies together unless provider totals explicitly support separated reconciliation.

---

# 13. Fixture 972201 reconciliation

Known fixture:

```text
Unit 1100 Final      1,610.96
Unit 1104 Final      1,810.05
                     --------
All Units            3,421.01
```

TA totals:

```text
QTY                  1,474.00
PRE TAX              3,027.44
HST                    393.57
GST                      0.00
PST                      0.00
QST                      0.00
DISC AMT                 0.00
FINAL                  3,421.01
```

Provider Grand Total:

```text
3,421.01
```

All required paths must PASS.

---

# 14. Source Unit # and Fleet matching are separate concepts

A BVD Unit # is whatever was entered/assigned in the BVD card environment.

BVD does **not** know TruckERP's Asset, Driver, HR, Payroll, or Dispatch databases.

Therefore:

```text
BVD source unit exists
```

and

```text
TruckERP fleet asset exists
```

are separate facts.

A source unit that is present in BVD but is not found in TruckERP Fleet does **not** make the source reconciliation mathematically wrong.

It creates an **UNRESOLVED UNIT** operational flag.

---

# 15. Unit-resolution flag after PDF/CSV upload

After parsing any BVD PDF/CSV, TruckERP must check every distinct non-zero transaction `unit_number` against the tenant's Assets.

If the unit resolves to an Asset:

```text
MATCHED ASSET ✓
```

If the unit does not resolve:

```text
ACTION REQUIRED — UNIT NOT FOUND
```

The owner/admin must be able to see this immediately on the Fuel review/import result.

The source money remains in all reconciliation totals even while the unit is unresolved.

An unresolved fleet match must never cause the transaction amount to disappear.

---

# 16. Clicking an unresolved unit — required decision flow

When the user clicks an unresolved BVD unit, ask:

```text
What is this unit?

A. This truck belongs in our operation / works under our authority
B. This is an outside unit using a lent/borrowed fuel card
```

## A. Truck belongs in our operation

If the truck belongs to the company or an owner-operator working under the tenant's authority, it is a real fleet asset and should be added properly.

Flow:

```text
Unresolved BVD Unit
      ↓
Add to Assets
      ↓
open Asset page
      ↓
prefill source Unit # when appropriate
      ↓
user completes required Asset information
      ↓
Save Asset
      ↓
return to the same Fuel import/review
      ↓
rerun unit resolution
      ↓
flag clears automatically when matched
```

Do not create a partial/fake asset merely to make Fuel pass.

Normal Asset onboarding rules still apply, including Company vs O/O ownership where applicable.

## B. Outside unit / card loan

If the card was lent to another company, outside owner-operator, person, or other outside party, **do not create a Fleet Asset**.

Create a small **Fuel-only external unit/use record**.

This record exists solely to explain where that BVD fuel transaction belongs.

It must never appear in:

```text
HR
People
Drivers
Payroll
Dispatch
Fleet Assets
Maintenance
```

It must not silently create a Person, Driver, O/O, or Asset.

---

# 17. Fuel-only external unit/use record

The exact schema may follow TruckERP conventions, but the record must support at least:

```text
tenant_id
provider                 = BVD
source_unit_number
card_number
external_party_type      = COMPANY | PERSON_OR_OO
external_name
source_import_id
source_amount
source_discount
amount_before_discount
amount_after_discount
discount_treatment
note
resolved_by
resolved_at
created_at
updated_at
```

Money shown in this record should be derived from parsed BVD source data whenever possible.

Do not ask the user to manually retype money already parsed from the provider statement.

If the business needs a choice about whether a provider discount is passed through, store the choice and calculate the resulting amount from source values.

The source `fuel_bvd` values remain unchanged.

---

# 18. Missing source unit vs unmatched fleet unit

These are different conditions.

## Missing source unit

If BVD has a non-zero transaction with a blank/missing source Unit #:

```text
SOURCE UNIT MISSING
```

Put the money into an explicit unresolved/unassigned bucket and block Process until resolved according to an approved rule.

## Source unit present, but not found in Fleet

Example:

```text
BVD Unit # = 7788
Final AMT = 650.00
```

The source transaction is valid evidence and remains in the math.

TruckERP creates:

```text
UNRESOLVED UNIT 7788
```

The user then resolves it as either:

```text
REAL ASSET
```

or:

```text
FUEL-ONLY EXTERNAL UNIT/USE
```

Only the unresolved operational status blocks Process; the source reconciliation itself may still PASS.

---

# 19. Process gate

Process is allowed only when **both** conditions are true:

```text
A. SOURCE_RECONCILIATION = PASS
B. UNIT_RESOLUTION       = COMPLETE
```

Required source failures include, where applicable:

```text
unparseable money
transaction/product mismatch
transaction/unit mismatch
provider product-total mismatch
provider Grand Total mismatch
invoice-total mismatch
incompatible currency reconciliation
unresolved non-zero Manual/Express provider amount
missing source unit with non-zero money and no approved resolution
```

Required unit-resolution failures include:

```text
source Unit # exists but no Asset match and no Fuel-only external resolution
```

Important distinction:

```text
UNMATCHED FLEET UNIT != BAD BVD PARSE
```

It means the source was parsed, but TruckERP still needs the owner/admin to classify where that unit belongs.

---

# 20. Human review

Passing validations does not automatically Process the import.

The human still reviews the parsed result.

The user may open the original BVD PDF from the review page to verify any questionable value.

Only an authorized user explicitly triggers Process.

---

# 21. What Process does NOT mean yet

This milestone does not by itself authorize:

```text
payroll deduction
O/O settlement
company expense posting
GL posting
bank posting
factoring
AR
HR/People creation
Driver creation
Dispatch assignment
```

Those workflows consume accepted Fuel data later under their own rules.

---

# 22. Acceptance tests

At minimum prove:

```text
1. BVD PDF/CSV parses and exact source text is preserved.
2. Fixture 972201 reconciles to 3,421.01 exactly.
3. One-cent mismatch fails.
4. Unit/product rollups equal transaction totals.
5. Unknown BVD product code is preserved and not dropped.
6. Zero Manual/Express is neutral.
7. Non-zero unresolved Manual/Express blocks Process.
8. Blank source Unit # with non-zero money is explicitly unresolved.
9. Source Unit # not found in Fleet raises ACTION REQUIRED but remains in source math.
10. User can resolve the unit by adding a real Asset and return to the same Fuel review.
11. User can instead resolve the unit as a Fuel-only external card-loan/use record.
12. Fuel-only external records never appear in HR, People, Driver, Payroll, Dispatch, Fleet Assets, or Maintenance.
13. Source `fuel_bvd.unit_number` never changes because of operational resolution.
14. Process remains blocked until both money reconciliation and unit resolution are complete.
```

---

# 23. Locked principle

The BVD pipeline has four responsibilities:

```text
PARSE IT
SHOW IT
CHECK IT
PROCESS IT
```

`CHECK IT` includes two independent checks:

```text
MONEY CHECK
    Every provider amount reconciles exactly.

UNIT CHECK
    Every non-zero transaction is attributed either to a real Asset
    or to a Fuel-only external-use record.
```

The provider source evidence remains immutable throughout.

---

# 24. Fuel Process → Payroll handoff modes

Fuel `Process` finalizes the Fuel-side import/review. It does **not** by itself mean that a driver or owner-operator deduction has already been applied to a payroll statement.

TruckERP must support both small one-person fleets and companies where Fuel and Payroll are separate roles.

## Tenant-level backend setting

Use a tenant/company setting:

```text
fuel_payroll_handoff_mode
```

Locked values:

```text
PAYROLL_STAGED   = default
IMMEDIATE        = one-man-show automatic handoff
```

This is a tenant-level operating policy, not an invoice-by-invoice choice.

It must not be stored in immutable `fuel_bvd` source rows.

## PAYROLL_STAGED — default

This is the default because the person parsing Fuel may not have Payroll authority.

Flow:

```text
Fuel user clicks Process
      ↓
Fuel import becomes accepted/final on the Fuel side
      ↓
eligible operational Fuel items become READY_FOR_PAYROLL
      ↓
NO payroll deduction is applied yet
      ↓
Payroll user later generates the applicable payroll/settlement cycle
      ↓
Payroll backend consumes the eligible READY_FOR_PAYROLL items
      ↓
those items are included exactly once
```

The Fuel user's job ends at successful Fuel Process.

Fuel Process must not require the Fuel user to have Payroll permissions.

## IMMEDIATE — one-man-show mode

For a tenant where the same owner/person handles Fuel and Payroll, `IMMEDIATE` removes the second manual handoff step.

Flow:

```text
Fuel user clicks Process
      ↓
Fuel import becomes accepted/final on the Fuel side
      ↓
eligible operational Fuel items are handed off immediately
      ↓
they become visible/available to the downstream payroll/settlement workflow
      ↓
actual payroll calculation, statement finalization, payment, and closed-cycle rules still belong to Payroll
```

`IMMEDIATE` does **not** mean Fuel Process may directly change a closed or paid payroll, create a payment, or bypass payroll-cycle controls.

It means only that a separate person does not need to manually approve the Fuel-to-Payroll handoff.

## Eligibility boundary

Only Fuel operational items that are actually eligible under the applicable ownership/pay policy may enter the Payroll handoff.

Do not infer payroll responsibility from BVD source text alone.

In particular:

```text
Fuel-only external card-loan/use records
```

must remain entirely outside Payroll, HR, People, Drivers, and Dispatch.

Company-paid/non-deductible Fuel items must not become driver deductions merely because the Fuel import was Processed.

## Idempotency / no duplicate deduction

A processed Fuel item must never be handed to Payroll twice.

The operational handoff layer must support an idempotent lifecycle equivalent to:

```text
NOT_APPLICABLE
READY_FOR_PAYROLL
HANDED_OFF
INCLUDED_IN_PAYROLL
```

Operational records should retain enough linkage to prove which Fuel source transaction produced which payroll/settlement item, for example:

```text
fuel_transaction_id
payroll_handoff_status
payroll_item_id          nullable
handed_off_at
handed_off_by
```

Exact field/table names may follow TruckERP conventions, but the one-source-item / one-payroll-consumption rule is locked.

## Payroll cycle remains authoritative

Even in `IMMEDIATE` mode, Payroll remains authoritative for:

```text
which pay cycle receives the item
cutoff rules
payee eligibility
statement calculation
approval
partial payment
final payment
closed/paid-cycle protection
```

Fuel Process publishes accepted operational Fuel data; Payroll decides how and when eligible items affect a payroll/settlement statement.

## Required tests for this rule

At minimum prove:

```text
1. New tenant defaults to PAYROLL_STAGED.
2. In PAYROLL_STAGED, Fuel Process succeeds without creating an applied payroll deduction.
3. Eligible item becomes READY_FOR_PAYROLL and is consumed when Payroll generates the applicable cycle.
4. In IMMEDIATE mode, eligible item is handed off automatically after Fuel Process.
5. IMMEDIATE mode still does not modify closed/paid payroll.
6. The same Fuel item cannot be included twice.
7. Fuel-only external card-loan/use records never enter Payroll in either mode.
8. Company-paid/non-deductible items do not become driver deductions.
```

---

# 25. DUPLICATE SOURCE INGESTION GATE (LOCKED)

Every Fuel source upload is checked **before** a new import is created. Checks are **tenant-scoped** and **provider-scoped** (BVD today).

## Authoritative identity (PDF)

Invoice number, invoice date, charge period start/end, and due date come from **parsed PDF HEADER fields** — never from the upload filename.

Filename (e.g. `BVD_invoice_972201.pdf`) is a **signal only** (`matched_on: FILE_NAME`). Filename alone does **not** hard-block.

## PDF layers

| Layer | Field / input | Hard block? |
|-------|----------------|-------------|
| A | `source_file_name` | Signal only |
| B | provider `BVD` + `invoice_number` + `invoice_date` + `start_date` + `end_date` | Yes when full identity matches |
| C | raw file SHA-256 (upload bytes) | Yes — exact duplicate |

## PDF decision matrix

- **Same SHA-256** → `FUEL_DUPLICATE_EXACT` (409) — no new import, no storage, no rows.
- **Same document identity, different hash** → `FUEL_DUPLICATE_DOCUMENT` (409).
- **Same invoice number, different date/period** → `FUEL_POSSIBLE_REVISION` (409) — admin must inspect; no silent accept.
- **Same filename only** → allow if identity + hash differ.
- **New identity + new hash** → accept.

## CSV (hook)

CSV uses layers A–C plus **normalized transaction fingerprint** (order-independent SHA-256 over stable parsed txn fields). Regenerated exports with different raw bytes but identical transactions must fingerprint-match. Partial txn ID overlap → `FUEL_TRANSACTION_OVERLAP` (no silent import).

## Queue / Process

- Duplicate upload must **not** create another Fuel/BVD queue import row.
- **Process** on the same `import_id` is idempotent: already `SOURCE_REVIEWED` returns existing summary without re-publishing downstream (when publication exists).

## Implementation

- Service: `app/services/fuel_source_duplicate_gate.py`
- BVD ingestion boundary: `import_bvd_digital_pdf` in `app/services/fuel_bvd_import.py` (hash → extract → duplicate check → advisory lock → re-check → store).
- No DB uniqueness migration on historical demo duplicates; future constraint requires separate backfill design.

## Concurrency (PostgreSQL advisory lock)

**Lock key (business document):** `tenant_id` + `provider_code` + `invoice_number` (e.g. BVD `972201`). **Not** raw SHA-256.

After the lock is acquired, **re-check** before insert:

- `invoice_number`, `invoice_date`, `start_date`, `end_date`
- `source_file_sha256`

This prevents two simultaneous uploads of different byte streams (different hashes) for the same BVD invoice from creating two imports.

Helper: `business_document_advisory_lock_key(tenant_id, provider_code, invoice_number)`.

## CSV concurrency (future ingestion)

Provider CSV ingestion is **not** complete — only the **normalized transaction fingerprint** and `evaluate_csv_duplicate_layers` hook exist today.

When CSV ingestion is implemented, concurrency must use the **strongest available** key:

1. Provider document identity (when header/statement identity exists), else
2. Normalized transaction fingerprint

Advisory locks must align with that business key (not raw file bytes alone). Same post-lock re-check pattern as PDF: identity fields + raw SHA + fingerprint.

---

# 26. COMPLETED FUEL PRESENTATION MODEL (LOCKED)

One processed BVD `import_id` — **three views**, same underlying `fuel_bvd` rows. No second copy of provider evidence.

## PROCESSING REVIEW (full detail)

Route: `/fuel/bvd/{import_id}/review`

Purpose: verify extraction, compare PDF, correct mistakes, reconciliation, **Process**.

Keeps **all** provider fields, tax columns, product rows, grand totals, PDF, correction overlay, and reconciliation checks. **Do not** simplify this screen into the operational history summary.

## COMPLETED BASIC REVIEW (Fuel history)

Route: `/fuel/history` (BVD today; provider-neutral later)

After `review_status = SOURCE_REVIEWED`, the invoice appears in **Fuel history** as a **clean operational card**:

- Provider, invoice number (linkable), process date, status, charge period, card, unit count, total + currency
- **Non-zero only** category and tax lines (dynamic — never hardcode “show HST / hide GST”)
- **Read-only** — no silent edits from history cards/tables

Zero-value provider fields (e.g. `GST = 0.00`) remain **stored**; the BASIC view simply **omits** them from rendering.

## FULL STORED DETAIL (read-only evidence)

Route: `/fuel/bvd/{import_id}/detail`

Opened from invoice number / “Full stored detail”. Shows **every** stored BVD field (including zero taxes), all transaction columns, legend, corrections, reconciliation, source metadata, and **original PDF** link. Read-only after Process except where an explicit audited correction workflow already allows changes — **never** rewrite immutable extracted source values.

## Data principle

| View | Projection |
|------|------------|
| Processing review | Full editable-review projection |
| Completed basic | TruckERP operational projection |
| Full stored detail | Complete auditable provider projection |

## Linkable fields (operational drill-down)

Structure BASIC UI so these can become links later: invoice → full detail; unit → unit transactions; category/tax → filtered transaction lists. Destinations may be stubbed until built.

## History / queue dedupe key (LOCKED)

Completed history and BVD source-review lists dedupe legacy uploads by **full document identity**:

```text
tenant_id + provider BVD + invoice_number + invoice_date + start_date + end_date
```

**Not** invoice number alone (e.g. 972201 Jul 2026 vs Jul 2027 remain two records).

When multiple legacy rows share the same identity, the canonical representative is:

1. `SOURCE_REVIEWED` over `IN_REVIEW` over `PENDING`/null
2. Newest upload within the same status

Other imports are **not** deleted.

## RECENT ACTIVITY — EXPANDED TRANSACTION DISPLAY CONTRACT (LOCKED)

**Surface:** Fuel dashboard → Recent activity → expand a completed BVD invoice → compact transaction table (`BvdTransactionRowsTable`).

**Authority:** Accepted / effective BVD transaction fields only (`operationalCell` on permanent `fuel_bvd` rows returned by `GET /fuel/bvd/imports/{import_id}/rows`). No recalculation, allocation, FX, or inference.

### Discount column (always on)

| Source field | Display |
|--------------|---------|
| `disc_amt` | Always show a **Discount** column |

- Non-zero provider discount → display the accepted amount (formatted; commas allowed).
- Known zero (`0`, `0.00`, etc.) → **`0.00`** (not `—`).
- `—` only when the source value is genuinely missing/unknown under the BVD row contract.

### Tax columns (dynamic per expanded invoice)

Supported source fields: `hst`, `gst`, `pst`, `qst`.

For the **currently displayed transaction set** (all `TRANSACTION` rows for that import in the table):

- Show a tax column **only if** at least one row has a **non-zero** accepted amount for that tax type.
- Do **not** show tax columns that are zero across the entire invoice.

When a tax column is active, **every row** shows that field:

- Non-zero → formatted accepted amount.
- Zero → **`0.00`** (not `—`).

### Column order (compact table)

```text
expand | Date/Time | Unit | Source driver | Location | Product | Qty | Discount | [HST] | [GST] | [PST] | [QST] | Final amount | Currency
```

Bracketed tax columns appear only when applicable.

### Sorting (view-only)

- Default row order = provider/source order (unchanged until the user sorts).
- **Discount** and each **visible** tax column are sortable as numeric money (`parseBvdMoneyString`), not formatted strings.

### Full evidence view

The **full processed / stored BVD detail** view (`BvdParsedStatementView`, `/fuel/bvd/{import_id}/detail`) remains the complete provider projection. This contract applies only to the **compact** Recent Activity transaction table.

### Processed record local search (separate from Global Fuel History)

Full processed/read-only statement (`FuelBvdProcessedRecordView`, `presentation=full-stored-detail`): **Search this statement** + **Date period** filters are view-only, client-side, one import at a time. Locked in `docs/FUEL_REVIEW_HISTORY_SEARCH_ARCHITECTURE_LOCK.md`.

### Implementation hooks (compact table)

- `apps/web/src/pages/fuelBvdReview/fuelBvdTxnMoneyColumns.ts`
- `apps/web/src/pages/fuelBvdReview/BvdTransactionRowsTable.tsx`
- `apps/web/src/pages/fuelBvdReview/fuelBvdTxnTableSort.ts`

---

## Implementation hooks

- BASIC projection: `app/services/fuel_bvd_completed_basic.py`, `apps/web/src/pages/fuelBvdReview/bvdCompletedBasicProjection.ts`
- API: `GET /fuel/bvd/history`, `GET /fuel/bvd/imports/{id}/completed-basic`
- UI: `FuelBvdHistoryPage`, `FuelBvdFullDetailPage`, `BvdCompletedBasicCard`
