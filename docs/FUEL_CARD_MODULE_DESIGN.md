# TruckERP Fuel / Fuel-Card Module Design

**Status:** Discussion/design lock candidate — not implementation-complete, not Gold.

**Purpose:** Define the Fuel / Fuel-Card module before implementation. This document captures the agreed business workflow, provider PDF contracts, provider/API boundary, owner-operator charging rules, truck ownership relationships, reconciliation gates, and payroll/settlement handoff.

---

## 1. Core design rule

A fuel-card provider transaction is **not automatically a fuel expense**.

The provider is the payment source. Each transaction must preserve the provider's original facts and then be classified/routed by TruckERP.

Examples include:

- Fuel
- DEF
- Scale
- Cash advance
- Product purchase (coolant, oil, additive, etc.)
- Repair/service
- Parking
- Toll
- Lumper
- Other / review-required

The Fuel/Card module may ingest and classify these transactions, but downstream business ownership remains with the appropriate module (for example, Dispatch/Load for lumper reimbursement).

---

## 2. Three intake paths

TruckERP supports three Fuel/Card entry paths:

1. **Provider API**
2. **Digital provider PDF**
3. **Manual driver entry**

All three paths must converge on the same canonical transaction model and downstream financial rules.

---

## 3. Provider architecture

TruckERP must support many fuel-card providers. BVD and Nationwide are the first real provider contracts, but the module must not be hard-coded around either one.

Architecture:

```text
Provider-specific API / PDF
        ↓
Provider adapter/profile
        ↓
Canonical TruckERP Fuel/Card transaction model
        ↓
Shared reconciliation + ownership + settlement gates
```

Provider-specific facts must be preserved, but common business fields must hydrate into one uniform TruckERP schema.

If a provider does not supply a field, the field remains null/blank. Do not create separate core schemas for BVD vs Nationwide.

---

## 4. BVD first production contract

BVD is the first-class Canadian provider contract for initial implementation.

### 4.1 BVD invoice/header fields

Extract:

- Provider
- Invoice number
- Invoice date
- Invoice start date
- Invoice end date
- Due date
- Client/customer information

### 4.2 BVD transaction fields

The BVD transaction table contains:

- Card number
- Auth code
- Driver name
- Unit number
- Transaction date/time
- Site number
- Site name
- Site city
- Province/state
- Product code
- Quantity
- Retail price
- Billed price
- Pre-tax amount
- HST
- GST
- PST
- QST
- Discount rate
- Discount amount
- Final amount
- Currency

These provider values are preserved exactly as source facts.

### 4.3 BVD control totals

BVD subtotal/card/product/grand-total rows are control rows, not transactions.

The parser must keep these separate from transaction rows and use them for reconciliation.

---

## 5. Nationwide Fuel provider contract

Nationwide is the second real provider contract and has a materially different PDF layout from BVD.

### 5.1 Nationwide transaction-table columns

For normal transaction rows, Nationwide shows:

- Account Code
- Card Number
- Unit #
- Date
- City
- Pr/St
- Product
- Volume
- Ex-GST ($/U)
- Total
- Network
- Currency
- USA Discount
- Missed Disc
- OON Fees

The canonical TruckERP name for `Ex-GST ($/U)` should be neutral, such as **Provider Unit Price**, because its meaning depends on jurisdiction:

- **US transaction:** final gallon price; no GST/HST on US fuel
- **Canadian transaction:** ex-tax unit price; applicable Canadian taxes are carried separately

### 5.2 Nationwide card number + unit number

For Nationwide, the provider-side card/truck relationship is identified by the combination of:

```text
provider + account + card number + unit number
```

Preserve both `card_number_snapshot` and `unit_number_snapshot` permanently, even if a card or truck assignment changes later.

For transaction-level identity/deduplication, use additional fields such as transaction date/time, product and amount, or provider transaction ID when available.

### 5.3 Nationwide row types — CRITICAL

Nationwide is a structured digital table, but **the meaning of the cell positions changes by row type**.

The parser must first classify the row before interpreting cells.

Supported row types:

```text
TRANSACTION
CARD_TOTAL
INVOICE_SUMMARY
```

#### TRANSACTION row

Use the normal transaction headings:

```text
Card Number
Unit #
Date
City
Pr/St
Product
Volume
Provider Unit Price
Total
Network
Currency
USA Discount
Missed Disc
OON Fees
```

#### CARD_TOTAL row

A line such as:

```text
XXXXX87115 Total
```

is **not a transaction**.

It is a reconciliation/control row.

The same horizontal positions no longer have the normal transaction meanings. On Canadian card-total rows, Nationwide may place fields such as GST and QST in positions that visually sit under normal transaction columns such as Date/City.

Therefore:

> Never interpret Nationwide total rows using the transaction column names just because values appear under those visual positions.

First detect `CARD_TOTAL`, then apply the card-total schema.

A card-total row may contain:

- Card number
- Unit number/group context
- GST total where applicable
- QST total where applicable
- Volume total
- Amount total
- USA Discount total
- Missed Discount total
- Other provider control totals where present

### 5.4 Nationwide grouped transaction pattern

A Nationwide card block may contain many transaction rows, including different products, followed by one card-total row.

Example pattern:

```text
DIESEL
SCALE
DIESEL
DEF PUMP
...
CARD TOTAL
```

The parser must consume all detail rows in the card/unit group and then store the yellow/`Total` line separately as the group control total.

Do not create a transaction from the total row.

### 5.5 Nationwide multiple products

The same card/unit can have multiple products in the same statement period, including examples such as:

- DIESEL
- DEF PUMP
- SCALE
- REEFER

The product value must remain attached to the exact source row.

### 5.6 Nationwide CAD and USD reconciliation

Nationwide can contain Canadian and US transactions on the same invoice.

Reconcile currencies independently:

```text
CAD transactions = CAD provider total = CAD validated total
USD transactions = USD provider total = USD validated total
```

Never combine CAD and USD into one provider total before any downstream accounting conversion.

### 5.7 Nationwide printed totals vs displayed row arithmetic

Nationwide may print card/invoice control totals that differ by a cent or two from the simple sum of displayed rounded row amounts because of provider precision/rounding.

Preserve separately:

- Provider row amounts
- Provider card subtotal
- Provider invoice total
- Calculated detail-row sum
- Variance

The provider-declared control total is an authoritative source fact. The reconciliation engine must distinguish an accounted-for provider rounding variance from a genuine unexplained mismatch.

Do not silently alter any source transaction amount to force equality.

### 5.8 Nationwide CSV note

Nationwide invoices may state that an attached CSV contains further transactional detail.

Future implementation may support PDF + CSV together, but the PDF path must remain independently reviewable and reconcilable.

---

## 6. Digital PDF parsing policy

For a valid digital PDF with usable embedded text/table structure:

1. Read the embedded PDF text/table structure first.
2. Do not use OCR as the primary path.
3. Preserve row boundaries and provider table structure.
4. Map known provider fields into strict JSON.
5. Use AI only as a constrained structured-extraction/helper layer where needed; AI must not freely associate values from unrelated rows.
6. Use OCR only when the document is scanned/image-only or lacks usable embedded text.

Parser output is evidence, not authority to move money.

---

## 7. Uniform canonical transaction fields

TruckERP uses one canonical transaction shape across providers.

Common fields include:

- Provider
- Account code
- Card number
- Auth/provider transaction code
- Driver name snapshot
- Unit number snapshot
- Transaction date/time
- Site number
- Site name
- City
- Province/state
- Country
- Product code
- Product description
- Quantity
- Quantity unit (litres/gallons/etc.)
- Provider unit price
- Retail price
- Billed price
- Pre-tax amount
- HST
- GST
- PST
- QST
- Provider discount rate
- Provider discount amount
- Missed discount amount
- Out-of-network fee
- Transaction total/final amount
- Currency
- Network

Provider-specific fields remain nullable when not supplied.

Do not remove fields from the canonical schema simply because one provider does not use them.

---

## 8. Provider facts vs TruckERP resolution

Keep provider facts separate from TruckERP-derived relationships.

### Provider/source facts — immutable after final review

Examples:

- card number snapshot
- unit number snapshot
- transaction date/time
- driver name snapshot
- product
- quantity
- provider prices
- taxes
- discounts
- total
- currency
- provider control totals

### TruckERP resolution fields

Resolved after parsing/review:

- truck_id
- driver_id
- owner_operator_payee_id
- transaction classification
- financial responsibility
- pricing agreement
- settlement link
- gate statuses

The parser must never populate ownership/payee/settlement fields by guessing.

---

## 9. Admin PDF review workflow

Admin can upload one or many PDFs, including multiple providers.

Workflow:

```text
Upload PDFs
    ↓
Parse
    ↓
Review queue
    ↓
LEFT: original PDF
RIGHT: parsed TruckERP window
    ↓
Save & Next
    ↓
Automatically load next PDF + next parsed record
    ↓
Repeat until all reviewed
    ↓
Process
    ↓
Backend gates/reconciliation
    ↓
Summary
    ↓
Admin reviews
    ↓
Finalize / OK
    ↓
Window closes
```

`Save & Next` means the admin reviewed the PDF against parsed values. It is not financial posting.

The admin review view should expose the full provider record needed for reconciliation and audit.

---

## 10. O/O portal view

The owner-operator portal should show a reduced, understandable subset rather than every provider/audit field.

Typical O/O-facing transaction fields:

- Date/time
- Unit number
- Driver
- Location/station
- Product
- Quantity
- Price charged to O/O
- Total deduction
- Currency

Every O/O deduction must remain traceable back to the exact provider transaction, unit, driver, date/time, product, location and source document/API record.

---

## 11. Truck identity and unit-number history

Never use the unit number as the permanent identity of a truck.

Use a permanent `truck_id` plus an effective-dated unit-number history.

Historical provider records keep the source `unit_number_snapshot` exactly as reported.

When resolving a historical transaction:

```text
provider unit number + transaction date/time
    ↓
unit-number history
    ↓
truck_id
```

If a unit cannot be uniquely resolved for that date, stop and require review.

Renumbering the same physical truck keeps the same `truck_id`.

Replacing the physical truck creates a new `truck_id`.

---

## 12. Truck ownership / owner-operator relationship

When a truck is added, ownership must be explicit:

- Company-owned
- Owner-operator-owned
- Leased / supported future relationship

For owner-operator-owned equipment, link the truck to the correct owner-operator/payee.

Ownership must be effective-dated so historical transactions resolve to the owner/payee that applied on the transaction date, not today's owner.

---

## 13. Owner-operator fuel pricing agreement

For company drivers, the O/O fuel charge configuration is disabled/not applicable.

For owner-operators participating in the company fuel program, support pricing methods such as:

- Pump price
- Full provider/company discount
- Fixed cents per litre/gallon
- Percentage of provider discount

The fuel agreement belongs to the O/O/payee compensation/settlement relationship and should be effective-dated.

In segmented onboarding, hiring managers do not decide monetary fuel rules. HR/Payroll/Compensation completes that downstream setup. In combined mode, authorized admin/owner users may complete it during review.

---

## 14. Financial responsibility by transaction type

Classification and financial responsibility are separate concepts.

Examples:

### Company truck / company driver

- Fuel → company expense
- DEF → company expense
- Coolant/oil/additive/product → company expense; no driver deduction
- Cash advance → driver receivable/payroll deduction, subject to policy

### Owner-operator truck

- Fuel → O/O fuel charge according to pricing agreement
- DEF → O/O deduction
- Coolant/oil/additive/product → O/O deduction
- Repair/service → normally O/O deduction, subject to contract/rule
- Cash advance → O/O/payee deduction unless explicitly driver-specific under company policy

Every financial posting retains unit number, driver context and provider transaction detail.

---

## 15. Lumper boundary

Fuel/Card may ingest/classify a lumper transaction, but Fuel/Card does not own final load association or reimbursement workflow.

Dispatch/Load owns:

- driver receipt upload
- receipt review
- load association
- broker reimbursement/accessorial
- receivable status

Do not auto-attach a lumper merely because the driver had an active trip. Multi-load/multi-stop cases require Dispatch review unless the match is unambiguous under future explicit rules.

---

## 16. Strict reconciliation gates

This is a money-moving module. Parser output alone is never sufficient for posting.

### Source reconciliation rule

Every provider line must be accounted for exactly once.

```text
All truck transactions
+ all other classified transactions
+ accounted provider rounding variance where explicitly allowed
= Provider control total
= Validated total
```

Required conditions:

- no missing transactions
- no duplicate transactions
- no unexplained variance
- no unresolved currency mixing

### Multiple gates

Before a transaction becomes settlement-eligible, it must pass the applicable gates:

1. Document/source validity
2. Parser completeness
3. Row-type correctness
4. Row/source integrity
5. Provider card/subtotal reconciliation
6. Provider invoice/currency total reconciliation
7. Duplicate/idempotency check
8. Truck resolution using transaction date/time
9. Ownership/payee resolution using transaction date/time
10. Pricing agreement validation using transaction date/time
11. Financial-responsibility resolution
12. Settlement eligibility

If any required money gate is `FAIL` or `REVIEW`, do not post.

---

## 17. API path

Provider API data is treated as authoritative raw provider input.

TruckERP must not rewrite provider amounts, dates, unit numbers or transaction IDs to make them fit internal records.

API controls still include:

- immutable raw payload
- provider transaction uniqueness/idempotency
- strict normalization
- historical truck resolution
- historical ownership/payee resolution
- pricing-rule validation
- settlement posting gate

API simplicity does not remove downstream financial gates.

---

## 18. Settlement/payroll handoff

The whole provider invoice does not necessarily equal one O/O's settlement deduction.

Settlement uses the exact eligible transaction set for:

- the correct owner/payee
- the correct truck(s)
- the correct transaction dates
- the correct pricing agreement
- the correct settlement period

Multi-truck O/O settlements must provide breakdown by truck and drill-down to transaction detail.

Example:

```text
ABC Transport

Unit 1100    ...
Unit 1104    ...
Unit 1120    ...
-------------
Fuel/Card deduction total
```

Each line remains traceable to the provider source.

---

## 19. Audit / correction policy

Keep:

- original source PDF/API payload
- parser output
- reviewed/corrected values
- reviewer
- review timestamp
- correction reason
- matching decisions
- ownership/payee resolution
- pricing rule applied
- settlement posting

After financial posting, do not silently rewrite history. Corrections require an auditable adjustment/reversal workflow.

---

## 20. Implementation order

Recommended order:

1. Canonical Fuel/Card schema
2. Provider import/batch schema
3. BVD PDF profile + hydration contract
4. Nationwide PDF profile + row-type rules
5. Admin provider configuration
6. Truck ownership + O/O/payee FK
7. Unit-number history
8. O/O fuel pricing agreement
9. PDF review queue UI
10. Reconciliation engine
11. BVD API adapter
12. Provider adapter framework
13. Matching/dedupe
14. Fuel/Card operations UI
15. Driver manual entry
16. Settlement/payroll bridge
17. Audit/tests
18. Establish Fuel Gold only after verified implementation

---

## 21. Current unresolved implementation details

Still to be decided/verified from real provider evidence or code-level implementation:

- exact database column types/precision
- exact rounding-tolerance policy per provider
- exact BVD API contract
- exact Nationwide API/CSV contract
- final settlement/payroll FK structure
- whether provider card assignment history deserves its own first-class table
- final UI wording for review/finalize states

Do not invent these details before evidence is available.
