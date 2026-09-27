# Fuel / BVD — Implementation 1

**Status:** LOCKED — amended 2026-09-27  
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
SAVE EXACT BVD SOURCE DATA
      ↓
RUN SOURCE MONEY VALIDATIONS
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
```

The review page is **results-first**. It is not required to show the PDF side-by-side.

The original BVD PDF must remain available from an icon/button for spot-checking.

Before Process, TruckERP must answer three questions:

1. Did TruckERP parse the source correctly?
2. Does every penny reconcile through transaction, unit, product, and BVD provider totals?
3. Is every non-zero source unit resolved either to a real TruckERP asset or to a Fuel-only external-use record?

---

# 2. Immutable BVD source evidence

The provider source evidence remains in:

```text
fuel_bvd
```

One `fuel_bvd` row represents one extracted BVD source row/record.

Rows from the same source file share the same `import_id`.

Known structural values:

```text
HEADER
TRANSACTION
TRANSACTION_SUBTOTAL
PAGE1_SUMMARY
GRAND_TOTAL
LEGEND
```

The source table is provider-faithful and immutable after capture/review correction overlay rules.

TruckERP operational decisions must never replace the BVD source value.

Example:

```text
BVD source Unit # = 7788
fuel_bvd.unit_number = "7788"
```

If TruckERP later decides that `7788` maps to Asset 1105, or that it belongs to an external card-loan record, the original BVD value remains `7788`.

Operational resolution is stored separately.

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
