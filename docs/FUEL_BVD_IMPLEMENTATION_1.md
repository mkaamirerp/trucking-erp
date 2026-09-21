# Fuel / BVD — Implementation 1

**Status:** LOCKED BVD schema design checkpoint  
**Scope:** one BVD source table + TruckERP-owned operational/resolution fields.  
**Backend authority:** all matching, validation, reconciliation, pricing, settlement, and posting logic stays in the backend.  
**No migration/deployment is authorized by this document alone.**

---

# 1. Core decision

Implementation 1 uses **one BVD table**.

```text
BVD PDF
   ↓
extract known BVD fields
   ↓
fuel_bvd
   ↓
backend resolves TruckERP identities / status
   ↓
later financial logic
```

The table stores two clearly separated kinds of data:

```text
A. BVD source fields
B. TruckERP-owned fields
```

BVD source values must never be overwritten by TruckERP resolution.

Example:

```text
BVD Unit #        = 1104
TruckERP truck_id = 87
```

Both are retained.

`unit_number` is BVD source truth.  
`truck_id` is TruckERP's resolved internal identity.

Do **not** make BVD `Unit #` a foreign key to TruckERP `truck_number`.

---

# 2. One-row model

One `fuel_bvd` row represents one source row/record from the BVD PDF.

`row_type` identifies what kind of BVD record it represents.

Initial allowed values:

```text
TRANSACTION
TRANSACTION_SUBTOTAL
PAGE1_SUMMARY
GRAND_TOTAL
LEGEND
```

Invoice/header information and import-level processing metadata may repeat across rows from the same PDF. This is intentional in Implementation 1 to keep the BVD model simple and in one table.

Rows from the same uploaded/processed PDF share the same `import_id`.

```text
same PDF
    ↓
same import_id on every row
```

`parse_status` is an **import/PDF processing status** and therefore normally has the same value on every row for the same `import_id`.

`review_status` is a **row-level review status** and may differ from one row to another.

Example:

```text
import_id = 8f24...same UUID...

row 1  parse_status = SUCCESS  review_status = APPROVED
row 2  parse_status = SUCCESS  review_status = REVIEW
row 3  parse_status = SUCCESS  review_status = APPROVED
```

---

# 3. BVD invoice/header source fields

Verified BVD invoice/header information:

```text
Invoice Number
Invoice Date
Start Date
End Date
Due Date

Client info
    customer-name value is printed on an unlabeled line
    Address:
    Phone:
    Email:

Transactions for card
    card value

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

- `client_name` stores the BVD customer-name value even though the source line itself is unlabeled.
- `card_number` stores the value from `Transactions for card`.
- BVD card number is source data; it is not a TruckERP truck/driver identifier.

---

# 4. Exact BVD transaction fields — 21

The BVD transaction contract is these exact source columns, in this order:

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

Database columns:

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

The database column names are SQL-safe names for the exact BVD source fields. The BVD meaning must not be changed during extraction.

Example:

```text
BVD PDF: Unit # = 1104
DB:      unit_number = 1104
```

Later backend resolution may add:

```text
truck_id = 87
```

but `unit_number = 1104` remains unchanged.

---

# 5. BVD control / summary / Grand Totals fields

The same `fuel_bvd` table also stores BVD control and summary rows using `row_type`.

Known page-1 source/control labels include:

```text
SUBTOTAL
Card #
Fuel Total
DF
Sub Total
```

Known Grand Totals columns are exactly:

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

Observed Grand Totals row labels:

```text
TA
TF
DF
Manual
Express
Grand Total
```

Additional columns in `fuel_bvd` used for these rows:

```text
row_label
product
final_amount
```

Shared monetary/source columns such as `qty`, `pre_tax_amt`, `hst`, `gst`, `pst`, `qst`, `disc_rate`, `disc_amt`, and `cur` are reused where the BVD row supplies them.

Do not classify `Manual` or `Express` as Legend product codes unless BVD source evidence explicitly establishes that later.

---

# 6. BVD Legend fields

The BVD PDF Legend uses:

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

The same `fuel_bvd` table stores Legend rows with:

```text
row_type = LEGEND
legend_code
legend_product_name
```

---

# 7. TruckERP-owned fields

These fields do **not** come from BVD. They belong to TruckERP.

## 7.1 Identity / tenancy

```text
id
tenant_id
import_id
```

`import_id` groups all rows created from the same uploaded/processed BVD PDF.

Implementation 1 intentionally keeps this grouping key in the one-table design rather than creating a separate BVD import table.

## 7.2 Source / audit

```text
source_file_name
source_file_sha256
source_storage_ref
source_page
source_row_number
```

Purpose:

- identify the original source PDF;
- prevent/identify duplicate imports;
- retain source traceability;
- identify where a row came from in the PDF.

## 7.3 Upload / processing timing

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

`processing_duration_ms` is backend-measured processing time.

Keep both timestamps and duration so backend diagnostics can distinguish when processing started/finished and how long the processing itself took.

Example:

```text
uploaded_at             = 2026-09-20 21:30:02-04
processing_started_at   = 2026-09-20 21:30:05-04
processing_completed_at = 2026-09-20 21:30:07-04
processing_duration_ms  = 1842
processed_by            = <TruckERP user id>
parser_version          = BVD_PDF_V1
parse_status            = SUCCESS
```

Initial `parse_status` values:

```text
SUCCESS
REVIEW
FAILED
```

`parse_status` describes the processing result for the imported PDF and is expected to be consistent across rows sharing the same `import_id`.

## 7.4 Row-level review audit

```text
review_status
reviewed_at
reviewed_by
review_reason
extraction_warnings
```

Initial `review_status` values:

```text
PENDING
APPROVED
REVIEW
REJECTED
```

`extraction_warnings` is TruckERP-owned structured warning data for parser/extraction concerns on the row. It does not alter any BVD source value.

Examples of warning reasons may include:

```text
LOW_CONFIDENCE_FIELD
FIELD_UNREADABLE
EXPECTED_FIELD_MISSING
AMBIGUOUS_ROW
```

The exact warning vocabulary is a backend contract and must be validated server-side.

Review/approval authority is enforced by the backend.

## 7.5 TruckERP identity resolution

```text
truck_id
driver_id
owner_operator_id

truck_match_status
driver_match_status

matched_at
ownership_resolved_at
```

Initial match status values:

```text
MATCHED
UNMATCHED
REVIEW
```

`matched_at` records when the backend identity-resolution process matched the source row to TruckERP identities.

`ownership_resolved_at` records when the backend resolved the applicable ownership/O/O relationship for that transaction context.

Example:

```text
BVD source:
    unit_number = 1104
    driver_name = JASPREET CHOKAR

TruckERP backend resolution:
    truck_id = 87
    truck_match_status = MATCHED
    driver_id = 214
    driver_match_status = MATCHED
    owner_operator_id = 31
    matched_at = <backend timestamp>
    ownership_resolved_at = <backend timestamp>
```

BVD source fields remain unchanged after this resolution.

Important:

```text
unit_number = BVD source truth
truck_id    = TruckERP resolved FK
```

Truck ownership/assignment logic must be resolved in the backend using the transaction context/date and TruckERP history. The browser is never authoritative for this mapping.

## 7.6 Database audit

```text
created_at
updated_at
```

---

# 8. Implementation 1 table shape

```sql
CREATE TABLE fuel_bvd (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id               BIGINT NOT NULL,
    import_id               UUID NOT NULL,

    row_type                TEXT NOT NULL,

    -- BVD invoice/header source fields
    invoice_number          TEXT,
    invoice_date            TIMESTAMP,
    start_date              TIMESTAMP,
    end_date                TIMESTAMP,
    due_date                TIMESTAMP,

    client_name             TEXT,
    client_address          TEXT,
    client_phone            TEXT,
    client_email            TEXT,

    card_number             TEXT,
    hst_number              TEXT,
    qst_number              TEXT,

    -- Exact 21 BVD transaction fields
    auth_code               TEXT,           -- Auth Code
    driver_name             TEXT,           -- Driver Name
    unit_number             TEXT,           -- Unit #
    transaction_date        TIMESTAMP,      -- Date
    site_number             TEXT,           -- Site #
    site_name               TEXT,           -- Site Name
    site_city               TEXT,           -- Site City
    prov_st                 TEXT,           -- Prov/ST
    prod                    TEXT,           -- Prod
    qty                     NUMERIC(14,4),  -- QTY
    retail                  NUMERIC(14,6),  -- Retail
    billed                  NUMERIC(14,6),  -- Billed
    pre_tax_amt             NUMERIC(14,4),  -- Pre Tax AMT
    hst                     NUMERIC(14,4),  -- HST
    gst                     NUMERIC(14,4),  -- GST
    pst                     NUMERIC(14,4),  -- PST
    qst                     NUMERIC(14,4),  -- QST
    disc_rate               NUMERIC(14,6),  -- Disc Rate
    disc_amt                NUMERIC(14,4),  -- Disc AMT
    final_amt               NUMERIC(14,4),  -- Final AMT
    cur                     TEXT,           -- CUR

    -- BVD control / Grand Totals / Legend support
    row_label               TEXT,
    product                 TEXT,
    final_amount            NUMERIC(14,4),
    legend_code             TEXT,
    legend_product_name     TEXT,

    -- Source traceability
    source_file_name        TEXT,
    source_file_sha256      TEXT,
    source_storage_ref      TEXT,
    source_page             INTEGER,
    source_row_number       INTEGER,

    -- TruckERP processing/audit
    uploaded_at             TIMESTAMPTZ,
    uploaded_by             TEXT,
    processing_started_at   TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    processing_duration_ms  BIGINT,
    processed_by            TEXT,
    parser_version          TEXT,
    parse_status            TEXT,

    -- TruckERP row-level review
    review_status           TEXT,
    reviewed_at             TIMESTAMPTZ,
    reviewed_by             TEXT,
    review_reason           TEXT,
    extraction_warnings     JSONB,

    -- TruckERP identity resolution
    truck_id                BIGINT,
    driver_id               BIGINT,
    owner_operator_id       BIGINT,
    truck_match_status      TEXT,
    driver_match_status     TEXT,
    matched_at              TIMESTAMPTZ,
    ownership_resolved_at   TIMESTAMPTZ,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

This SQL is the **Implementation 1 design shape**. Before migration code is written, foreign-key targets and existing TruckERP model/type conventions must be checked against the repository so we do not guess table names or ID types.

---

# 9. Backend authority lock

The browser does not own Fuel business logic.

Frontend responsibilities:

```text
show original PDF
show BVD extracted values
show backend statuses/results
allow authorized user review/correction actions
send actions to API
```

Backend responsibilities:

```text
BVD extraction validation
row classification
field validation
unit_number -> truck_id resolution
driver matching
owner-operator/company ownership resolution
date-effective history lookup
reconciliation
fuel pricing rules
deductions
settlement logic
posting gates
audit trail
RBAC / permissions
```

The frontend must never be the authority for money, ownership, matching, reconciliation, or posting.

---

# 10. Financial separation lock

Do not add these calculated/decision fields to `fuel_bvd`:

```text
O/O fuel charge
payroll deduction
settlement amount
TruckERP discount calculation
functional_amount / FX-converted accounting amount
financial responsibility result
reconciliation result
posting result
```

`fuel_bvd` is BVD source evidence plus TruckERP audit/resolution metadata.

Later financial decisions must live in their own backend financial/settlement records and may reference the BVD source row.

This keeps the distinction explicit:

```text
BVD evidence = what the provider said
TruckERP financial record = what TruckERP decided/charged/posted
```

---

# 11. Implementation 1 lock summary

Implementation 1 is limited to:

```text
BVD source facts
+
TruckERP source/audit fields
+
TruckERP row-level review fields
+
TruckERP identity-resolution fields
```

Locked operating decisions:

```text
ONE fuel_bvd table
same import_id for rows from the same PDF
parse_status = import/PDF processing status
review_status = individual row review status
BVD source values are never overwritten
unit_number is not a FK
truck_id is resolved by backend logic
frontend is never authority for matching or money
financial charges/settlement data do not belong in fuel_bvd
```

---

# 12. Next design step

The BVD source schema and current TruckERP-owned operational fields are now frozen for Implementation 1 design review.

Before migration code is written:

```text
1. verify existing TruckERP FK targets / ID types
2. verify whether any old Fuel migrations were applied to a real tenant DB
3. create migration only after those checks
4. create SQLAlchemy model
5. add backend validation
6. test with the verified BVD PDF
```
