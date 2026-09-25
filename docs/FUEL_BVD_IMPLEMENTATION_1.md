# Fuel / BVD — Implementation 1

**Status:** LOCKED  
**Scope:** BVD extraction fidelity only.  
**Goal:** upload the verified BVD PDF, extract every known BVD field, save the extracted values in PostgreSQL, and show the original PDF beside the saved database values for human comparison.  
**No migration/deployment is authorized by this document alone.**

---

# 1. First milestone

Implementation 1 does only this:

```text
BVD PDF
   ↓
backend extraction engine
   ↓
exact BVD fields saved to fuel_bvd
   ↓
side-by-side review

LEFT  = original BVD PDF
RIGHT = values actually saved in PostgreSQL
```

The test question is only:

> Did TruckERP extract and save exactly what the BVD PDF contains?

Implementation 1 does **not** perform:

```text
truck matching
driver matching
company / owner-operator lookup
fuel responsibility
fuel discount calculation
reconciliation
settlement
payroll deduction
posting
```

Those are later backend workflows after extraction fidelity is proven.

---

# 2. One-table decision

Implementation 1 uses **one table**:

```text
fuel_bvd
```

Do not create separate BVD invoice, import, transaction, control, Grand Total, or Legend tables for this milestone.

One `fuel_bvd` row represents one extracted BVD source row/record.

Rows from the same uploaded PDF share the same `import_id`.

`row_type` identifies the BVD source structure represented by the row.

Initial structural values:

```text
HEADER
TRANSACTION
TRANSACTION_SUBTOTAL
PAGE1_SUMMARY
GRAND_TOTAL
LEGEND
```

This structural classification is only for preserving/displaying the BVD document. It is not financial business logic.

---

# 3. Source-fidelity rule

BVD source fields are stored as **TEXT** in Implementation 1.

Reason: the first milestone is exact extraction fidelity, not financial typing or normalization.

Examples:

```text
PDF:  1,425.63
DB:   "1,425.63"

PDF:  0.0000
DB:   "0.0000"

PDF:  2026-07-29 00:00:00
DB:   "2026-07-29 00:00:00"
```

Do not remove commas, trailing zeros, date/time text, provider abbreviations, or other source formatting before it is saved in `fuel_bvd`.

Typed amounts, dates, currencies, truck identities, ownership, pricing, and financial meaning come later in backend processing.

---

# 4. BVD invoice/header fields

Verified BVD invoice/header information:

```text
Invoice Number
Invoice Date
Start Date
End Date
Due Date

Client info
    [unlabeled customer-name line]
    Address:
    Phone:
    Email:

Transactions for card
    [card value]

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

Notes:

- `client_name` stores the customer-name value even though the source line is unlabeled.
- `card_number` stores the value belonging to `Transactions for card`.
- These are BVD source values, not TruckERP business decisions.

---

# 5. Exact BVD transaction fields — 21

The BVD transaction contract is exactly these source columns, in this order:

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

SQL-safe database columns:

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

The source meaning is unchanged.

Example:

```text
BVD PDF: Unit # = 1104
DB:      unit_number = "1104"
```

Implementation 1 stops there. It does not resolve `1104` to any TruckERP truck record.

---

# 6. BVD page-1 controls / summary

Known source/control labels in the verified fixture include:

```text
SUBTOTAL
Card #
Fuel Total
DF
Sub Total
```

The observed post-transaction sequence is preserved by `source_row_number` and the source values stored on the row.

Additional source columns used where applicable:

```text
row_label
product
```

Shared BVD source fields are reused when the control row contains them:

```text
qty
pre_tax_amt
hst
gst
pst
qst
disc_rate
disc_amt
final_amt
cur
card_number
```

No reconciliation meaning is applied in Implementation 1.

---

# 7. BVD Grand Totals

Exact Grand Totals columns:

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

Database support:

```text
product
qty
pre_tax_amt
hst
gst
pst
qst
disc_rate
disc_amt
final_amount
cur
```

`final_amount` is separate from transaction `final_amt` because BVD uses different source labels: `FINAL AMOUNT` vs `Final AMT`.

`Manual` and `Express` are preserved exactly as BVD Grand Totals row values. No additional meaning is assigned in Implementation 1.

---

# 8. BVD Legend

The BVD Legend uses:

```text
Code
Product Name
```

Verified pairs:

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

Database columns:

```text
legend_code
legend_product_name
```

Legend rows use:

```text
row_type = LEGEND
```

---

# 9. TruckERP-owned metadata fields

These fields do not come from BVD. They exist only to identify the source, measure processing, and support the side-by-side extraction review.

## Identity / grouping

```text
id
tenant_id
import_id
row_type
```

`import_id` is the same for every row extracted from one uploaded BVD PDF.

## Source traceability

```text
source_file_name
source_file_sha256
source_storage_ref
source_page
source_row_number
```

## Upload / processing audit

```text
uploaded_at
uploaded_by
processing_started_at
processing_completed_at
processing_duration_ms
processed_by
parser_version
parse_status
```

Initial `parse_status` values:

```text
SUCCESS
REVIEW
FAILED
```

## Extraction review metadata

```text
review_status
reviewed_at
reviewed_by
review_reason
extraction_warnings
```

These fields describe extraction review only. They do not authorize money movement.

## Database audit

```text
created_at
updated_at
```

---

# 10. Fields explicitly NOT allowed in fuel_bvd Implementation 1

Do not add any of the following to this source-extraction table:

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

The BVD database has one job in Implementation 1:

> Preserve exactly what was extracted from BVD, plus TruckERP source/processing/review audit metadata.

---

# 11. Locked table shape

```sql
CREATE TABLE fuel_bvd (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id               BIGINT NOT NULL,
    import_id               UUID NOT NULL,
    row_type                TEXT NOT NULL,

    -- BVD invoice/header source values: exact source text
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

    -- Exact BVD transaction fields: exact source text
    auth_code               TEXT, -- Auth Code
    driver_name             TEXT, -- Driver Name
    unit_number             TEXT, -- Unit #
    transaction_date        TEXT, -- Date
    site_number             TEXT, -- Site #
    site_name               TEXT, -- Site Name
    site_city               TEXT, -- Site City
    prov_st                 TEXT, -- Prov/ST
    prod                    TEXT, -- Prod
    qty                     TEXT, -- QTY
    retail                  TEXT, -- Retail
    billed                  TEXT, -- Billed
    pre_tax_amt             TEXT, -- Pre Tax AMT
    hst                     TEXT, -- HST
    gst                     TEXT, -- GST
    pst                     TEXT, -- PST
    qst                     TEXT, -- QST
    disc_rate               TEXT, -- Disc Rate
    disc_amt                TEXT, -- Disc AMT
    final_amt               TEXT, -- Final AMT
    cur                     TEXT, -- CUR

    -- BVD control / Grand Totals / Legend source values
    row_label               TEXT,
    product                 TEXT, -- PRODUCT
    final_amount            TEXT, -- FINAL AMOUNT
    legend_code             TEXT, -- Code
    legend_product_name     TEXT, -- Product Name

    -- TruckERP source traceability
    source_file_name        TEXT,
    source_file_sha256      TEXT,
    source_storage_ref      TEXT,
    source_page             INTEGER,
    source_row_number       INTEGER,

    -- TruckERP processing audit
    uploaded_at             TIMESTAMPTZ,
    uploaded_by             TEXT,
    processing_started_at   TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    processing_duration_ms  BIGINT,
    processed_by            TEXT,
    parser_version          TEXT,
    parse_status            TEXT,

    -- Extraction-review audit only
    review_status           TEXT,
    reviewed_at             TIMESTAMPTZ,
    reviewed_by             TEXT,
    review_reason           TEXT,
    extraction_warnings     JSONB,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

This is the Implementation 1 design shape. Migration code must follow existing TruckERP tenant conventions, but it must not change the locked BVD source-field contract above.

---

# 12. Backend / browser boundary for Implementation 1

Backend responsibilities:

```text
receive PDF
store original PDF
recognize approved BVD layout
extract known BVD source structures
save exact source values in fuel_bvd
return saved rows for review
stream original PDF for review
```

Browser responsibilities:

```text
upload BVD PDF
show original PDF on the left
show values read back from fuel_bvd on the right
```

For the first fidelity test, the right side must display the values **read back from PostgreSQL**, not temporary parser output held in browser memory.

No calculation or business decision belongs in the browser.

---

# 13. Implementation 1 acceptance test

Using the verified BVD invoice fixture, prove:

```text
1. PDF uploads successfully.
2. Original PDF remains available for the left-side viewer.
3. Backend extracts the known BVD structures.
4. Every extracted BVD value is inserted into fuel_bvd.
5. Source formatting is preserved as text.
6. Review page reads the saved values back from PostgreSQL.
7. PDF and database values can be compared side-by-side.
8. No fuel_transactions, reconciliation, truck, driver, O/O, pricing, settlement, or posting logic runs.
```

Examples that must remain exact:

```text
"1,425.63"
"0.0000"
"CN"
"1104"
"2026-07-27 13:38:39"
```

Implementation 1 passes only when the verified BVD fixture is reproduced field-for-field from the database for human review.

---

# 14. Next step after Implementation 1 passes

Only after BVD extraction fidelity is proven do we design the next backend step that publishes accepted fuel transactions into TruckERP operational fuel history for the applicable unit.

That later step is separate from `fuel_bvd` source evidence.
