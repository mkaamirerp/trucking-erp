# TruckERP Fuel / Fuel-Card Module Design

**Status:** Discussion/design lock candidate — architecture foundation only; not implementation-complete and not Gold.

**Purpose:** Capture the full Fuel / Fuel-Card architecture before implementation so provider parsing, truck ownership, owner-operator charging, reconciliation, review, settlement/payroll, Dispatch/Load boundaries, and future provider integrations are built on one consistent foundation.

This document is intentionally broader than a PDF parser design. Fuel/Card is a money-moving module and must preserve provider facts, prove where every transaction belongs, and prevent financial posting until all required gates pass.

---

## 1. Core principles

### 1.1 Fuel-card transaction does not mean fuel expense

A fuel-card provider is a **payment source**. A provider statement/API may contain many transaction types:

- Fuel / diesel
- DEF
- Reefer fuel
- Scale
- Cash advance
- Coolant
- Oil
- Additive
- Other product purchase
- Repair/service
- Parking
- Toll
- Lumper
- Other / unknown

The transaction must first preserve what the provider reported, then TruckERP classifies it and determines where the money belongs.

### 1.2 Parser output is evidence, not financial authority

No parser, OCR system, or AI model may directly create a payroll/settlement deduction.

```text
Provider PDF / API
        ↓
Provider facts
        ↓
Review + reconciliation
        ↓
Truck / owner / payee resolution
        ↓
Pricing + financial-responsibility rules
        ↓
Settlement eligibility
        ↓
Posting
```

### 1.3 One canonical transaction model

TruckERP has one canonical Fuel/Card transaction model across providers and countries.

Provider adapters may read different layouts, but after normalization they hydrate the same canonical fields. Fields not supplied by a provider remain null/blank rather than causing a separate provider-specific core schema.

### 1.4 Preserve provider facts separately from TruckERP decisions

Never overwrite source facts to make them fit TruckERP.

Examples of immutable provider facts:

- Card number as reported
- Unit number as reported
- Driver name as reported
- Transaction date/time
- Product
- Quantity
- Provider price(s)
- Taxes
- Discounts
- Fees
- Transaction total
- Currency
- Provider subtotal/control totals

TruckERP relationships are separate:

- `truck_id`
- `driver_id`
- `owner_operator_payee_id`
- classification
- financial responsibility
- pricing agreement
- settlement/payroll link
- gate statuses

---

## 2. Three intake paths

TruckERP supports exactly three initial Fuel/Card entry paths:

1. **Provider API**
2. **Digital provider PDF**
3. **Manual driver entry**

All three paths converge into the same canonical transaction model and downstream financial rules.

The source must remain recorded on every transaction, for example:

```text
API
PDF
MANUAL_DRIVER
```

---

## 3. Three product surfaces: Admin, Operations, Driver/O-O

Fuel/Card has three different user-facing concerns.

### 3.1 Admin / configuration

Admin decides:

- Which fuel-card providers the tenant uses
- Which provider connections are active
- API credentials / account identifiers
- Provider environment/base URL where applicable
- Auto-sync policy
- Provider-specific mapping/profile
- Who has permission to configure provider connections

### 3.2 Operations / Fuel workspace

Operations works with:

- Provider imports
- PDF review queue
- Transactions
- Reconciliation failures
- Unmatched units/cards/drivers
- Duplicates
- Financial destinations
- Posting/settlement readiness

### 3.3 Driver / Owner-Operator portal

Drivers/O-Os do not need the full provider/audit record.

They see the operationally useful subset and settlement breakdown, while Admin retains access to the complete source record.

---

## 4. Admin provider configuration

Existing `/admin/integrations/fuel` is the correct conceptual home for provider connection setup. It must become a real configuration surface rather than a placeholder.

A provider configuration should support fields/concepts such as:

- Provider code/name
- Enabled/disabled
- Connection type (`API`, `FILE`, future types)
- Account/client identifier
- API key/secret reference
- Environment / endpoint where applicable
- Auto-sync enabled
- Sync frequency
- Last sync timestamp
- Last sync result
- Test connection
- Manual `Sync now`

### 4.1 Credential security

Provider API secrets must remain server-side.

The browser must never receive a stored secret after save. UI may show only a masked state such as:

```text
API key: ••••••••
Configured: Yes
```

Do not hard-code provider secrets into React/frontend code.

### 4.2 Multi-provider from day one

A tenant may use BVD, Nationwide, EFS, Comdata, WEX, or future providers at the same time.

Do not create BVD-specific infrastructure that prevents multiple simultaneous providers.

---

## 5. Provider architecture

```text
Provider-specific API / PDF
        ↓
Provider adapter/profile
        ↓
Canonical TruckERP Fuel/Card transaction model
        ↓
Shared reconciliation + ownership + settlement gates
```

Each provider profile owns its source interpretation:

- Header fields
- Transaction-row format
- Control/subtotal row format
- Currency behavior
- Provider-specific price/discount meanings
- Deduplication identifiers if supplied

Shared TruckERP logic owns:

- Canonical transaction persistence
- Truck resolution
- Historical ownership/payee resolution
- Classification
- Financial responsibility
- O/O pricing
- Settlement eligibility
- Audit

---

## 6. BVD is the first production provider contract

BVD is the primary first implementation/provider profile for the Canadian use case. The initial Fuel/Card architecture should be proven with BVD first, while remaining capable of supporting many other providers.

### 6.1 BVD invoice/header fields

Extract and preserve:

- Provider
- Invoice number
- Invoice date
- Statement start date
- Statement end date
- Due date
- Client/customer information

### 6.2 BVD transaction fields

The real BVD statement provides:

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

These values are provider facts and must remain exactly tied to their source transaction row.

### 6.3 BVD layout in Admin review

For BVD, the right-side Admin review view should preserve the BVD transaction meaning and organize the operational view primarily by **Truck Unit #**.

Example concept:

```text
UNIT 1100
  BVD transaction rows...
  Unit subtotal / control information

UNIT 1104
  BVD transaction rows...
  Unit subtotal / control information
```

The backend still preserves card-level and provider-level controls even when the operational presentation is grouped by unit.

### 6.4 BVD product codes are source facts

Do not replace BVD product codes with TruckERP classifications.

Store both concepts separately:

```text
provider_product_code = TA
transaction_classification = FUEL
```

Provider code remains the original source value.

### 6.5 BVD control rows

BVD subtotal/card/product/grand-total rows are **control rows**, not transaction rows.

The parser must preserve them separately for reconciliation.

---

## 7. Nationwide is the second real provider contract

Nationwide proves that providers can use materially different PDF structures. TruckERP must not force the BVD layout onto Nationwide.

### 7.1 Nationwide normal transaction columns

For a normal detail row Nationwide provides:

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

### 7.2 Nationwide unit price meaning depends on jurisdiction

Use a neutral canonical name such as **Provider Unit Price**.

Nationwide's source rule is:

- US transaction: the column is the final gallon price; no GST/HST on US fuel
- Canadian transaction: the column is an ex-tax unit price and applicable Canadian tax is represented separately

Do not force the source label `Ex-GST` to be the canonical TruckERP field name.

### 7.3 Card number + unit number identifies the provider-side card/truck pairing

For Nationwide, the important pairing is:

```text
provider + account + card number + unit number
```

Preserve both:

- `card_number_snapshot`
- `unit_number_snapshot`

The pair identifies the card/unit relationship, while a single transaction still requires transaction-level identity such as date/time + product + amount or a provider transaction ID when available.

### 7.4 Nationwide row type must be identified before interpreting columns — CRITICAL

Nationwide is a structured digital table, but **the meaning of the visual positions changes by row type**.

The parser must first classify the row:

```text
TRANSACTION
CARD_TOTAL
INVOICE_SUMMARY
```

Only after classifying the row may the parser interpret its cells.

#### Normal TRANSACTION row

Use the normal transaction headings.

#### CARD_TOTAL row

A line such as:

```text
XXXXX87115 Total
```

is not a transaction.

It is a provider control row.

On a Canadian card-total row, Nationwide can place GST/QST text and values visually under positions that correspond to normal transaction columns such as Date/City. Therefore fixed x-position/column-name assumptions alone are unsafe.

Rule:

> Detect `CARD_TOTAL` first; then apply the Nationwide total-row schema.

### 7.5 Nationwide group pattern

One card/unit group may contain multiple products followed by one control total:

```text
DIESEL
SCALE
DIESEL
DEF PUMP
REEFER
...
CARD TOTAL
```

The `CARD TOTAL` row never creates an expense transaction.

### 7.6 Nationwide CAD and USD must reconcile independently

A single Nationwide invoice can contain both Canadian and US transactions.

Required reconciliation:

```text
CAD classified transactions = CAD provider control total = CAD validated total
USD classified transactions = USD provider control total = USD validated total
```

Never combine CAD + USD into one fake provider total before a separate downstream currency-conversion/accounting process.

### 7.7 Provider rounding / displayed precision

Nationwide printed card/invoice controls may differ by a cent or small amount from a simple sum of displayed rounded transaction values.

Preserve separately:

- Provider detail-row values
- Calculated detail-row sum
- Provider card total
- Provider invoice total
- Variance

Do not alter a source transaction amount merely to force equality.

Any allowed provider-rounding policy must be explicit and tested. Until that policy is proven, unexplained variance remains review-required.

### 7.8 Nationwide CSV note

Nationwide may provide an attached CSV with further detail. Future work may use PDF + CSV together, but PDF must remain independently reviewable and source-preserving.

---

## 8. Digital PDF parsing policy

### 8.1 Digital PDF first — not OCR first

For a valid digital provider PDF with usable embedded text/table information:

1. Read the digital PDF content first
2. Preserve provider row boundaries
3. Preserve row order
4. Identify provider/profile
5. Identify row type
6. Map source fields into strict provider JSON
7. Normalize into canonical TruckERP fields

OCR is only for scanned/image-only PDFs or digital PDFs without usable embedded content.

### 8.2 AI / mini-model responsibility

If a small/mini GPT is used, its job is narrow:

- Extract source header facts
- Extract source detail rows
- Extract source control rows
- Return strict JSON to a declared schema
- Preserve row relationships
- Mark missing/uncertain values rather than inventing them

It must **not**:

- Guess owner operator
- Guess truck ownership
- Guess payroll destination
- Guess settlement eligibility
- Rewrite provider amounts
- Combine values from unrelated rows because they look plausible

For known digital provider layouts, deterministic/provider-profile structure should drive extraction. AI is a constrained helper, not a free-form page interpreter.

### 8.3 Row integrity rule

Values belonging to one physical/logical provider row must remain together.

Example:

```text
card + unit + date + city + product + quantity + price + total + currency
```

must stay as one transaction row. Do not take card/unit from one row and price/quantity from another.

---

## 9. Uniform canonical transaction fields

TruckERP uses one field set for BVD, Nationwide, US transactions, Canadian transactions, and future providers.

Canonical source fields include:

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

### 9.1 Uniform does not mean every field is populated

Example:

- BVD may supply auth code, site number, driver name, retail/billed prices and Canadian tax fields
- Nationwide may supply network, USA discount, missed discount and OON fee
- A US row will normally have Canadian tax fields null/not applicable

The field remains in the canonical model; the provider simply does not populate it.

Do not create separate US vs Canada transaction schemas.

---

## 10. Provider import/batch vs transaction records

Do not treat an entire invoice as one fuel expense.

A provider PDF/API import represents a **batch/source statement**, and that batch contains many individual transactions.

Conceptual separation:

```text
fuel_card_import_batches
    one source PDF / API sync batch

fuel_card_transactions
    one provider transaction per row/event
```

The batch owns source-level facts such as:

- Provider
- Invoice/reference
- Statement period
- Original PDF/raw API payload reference
- Source totals by currency
- Parse/review/process state

Each transaction owns row-level facts.

---

## 11. Admin PDF review queue workflow

Admin may upload one PDF or many PDFs, including PDFs from more than one provider.

The workflow is intentionally simple to the user while financial gates remain strict behind the scenes.

```text
Upload multiple PDFs
        ↓
Parse
        ↓
Review queue opens
        ↓
LEFT: current original PDF
RIGHT: parsed TruckERP window
        ↓
Admin checks/corrects
        ↓
Save & Next
        ↓
Current PDF marked reviewed
Next PDF automatically loads on left
Next parsed data automatically loads on right
        ↓
Repeat until queue complete
        ↓
Process
        ↓
Wait while backend gates run
        ↓
Summary screen
        ↓
Admin reviews summary
        ↓
Finalize / OK
        ↓
Window closes — batch is done
```

### 11.1 Save & Next is not posting

`Save & Next` means only:

> I reviewed this source PDF against the parsed values.

It is not permission to move money.

### 11.2 Admin review should show the full provider record

Admin needs all available source fields, control totals, reconciliation information and TruckERP resolution information.

### 11.3 Finalization still requires system gates

Human review does not override reconciliation failures.

If Admin reviewed a PDF but a required financial gate fails, the batch cannot finalize.

---

## 12. Fuel/Card Operations workspace

The operational workspace is separate from Admin provider configuration.

Conceptual routes may include:

```text
/fuel
/fuel/transactions
/fuel/imports
/fuel/review
```

Useful filters include:

- Date / period
- Provider
- Card
- Unit/truck
- Driver
- Owner-operator/payee
- Product/category
- Source (`API`, `PDF`, `MANUAL_DRIVER`)
- Currency
- Company vs O/O responsibility
- Matched/unmatched
- Reconciled/unreconciled
- Posted/unposted

The primary operational grouping should support truck/unit because deductions and company expenses must be traceable by equipment.

---

## 13. Manual driver entry

Manual driver entry is a first-class intake path, not a separate accounting system.

The driver should enter only practical information, for example:

- Truck/unit (default from assignment where reliable)
- Transaction date/time
- Station/location
- Product/fuel type
- Quantity
- Litres/gallons
- Amount
- Currency
- Receipt/photo where available

The logged-in driver identity should normally provide the driver context automatically.

Manual entry enters the same canonical transaction pipeline and later can be matched/reconciled against provider API/PDF data.

### 13.1 Manual/API/PDF duplicate risk

A driver may enter a purchase manually and the same purchase may later arrive via provider API or PDF.

Duplicate/reconciliation logic must prevent double charging.

---

## 14. Transaction date/time is financially authoritative

Keep these dates separate:

- **Transaction date/time** — when the purchase happened
- **Invoice date** — when provider created the invoice
- **Imported at** — when TruckERP received/uploaded it
- Future `posted_at` / `settled_at` — workflow/accounting timestamps

Historical decisions must use the original transaction date/time, not the invoice date and not today's relationships.

Transaction date/time determines:

- Which truck/unit history applies
- Which card/unit assignment applies
- Who owned the truck at that time
- Which O/O/payee applied
- Which pricing agreement was effective
- Which settlement period can include the transaction

---

## 15. Truck identity and unit-number history

Unit number is an operational identifier, not the permanent identity of a physical truck.

Use permanent `truck_id` plus effective-dated unit-number history.

```text
truck_id = permanent physical asset identity
unit_number_snapshot = what provider reported at transaction time
```

Historical resolution:

```text
provider unit number + transaction date/time
        ↓
unit-number history
        ↓
truck_id
```

If the unit cannot be uniquely resolved for that date/time, stop and require review.

### 15.1 Same truck renumbered vs replacement truck

- Same physical truck, new unit number → same `truck_id`, new history interval
- Old truck replaced by another physical truck → new `truck_id`

Never convert Truck A into Truck B merely by changing VIN/unit fields.

### 15.2 Changing a unit number must be controlled

A unit-number change is not a simple text edit because many systems can depend on it.

Before changing, TruckERP should evaluate affected relationships such as:

- Current driver assignment
- Active trip(s)
- Fuel-card mapping
- Provider/card aliases
- ELD/GPS mapping
- Maintenance history
- IFTA/mileage
- Registration/documents
- Scheduled/future work
- Other integrations using the unit identifier

The old unit number remains historical; it is never erased from old transactions.

---

## 16. Truck ownership and O/O/payee relationship

Truck ownership must be decided when a truck is added.

Supported conceptual choices include:

- Company-owned
- Owner-operator-owned
- Leased / other supported relationship

If owner-operator-owned, Admin must select **which O/O/payee/business owns or is financially responsible for the truck**.

Ownership must be effective-dated.

Historical fuel transactions resolve to the owner/payee that applied on the transaction date, not whoever owns the truck today.

---

## 17. Owner-operator/payee is the financial counterparty

Fuel deduction logic must not assume the driver personally owns the money relationship.

An owner-operator/payee can have:

- One truck and drive it personally
- One truck with another driver
- Five trucks with five drivers
- More complex fleets later

TruckERP settles with the O/O/payee/business according to its agreement.

TruckERP does **not** decide how that O/O pays its own employee drivers merely because those drivers appear on the card transactions.

### 17.1 Multi-truck O/O breakdown is mandatory

Settlement must show total O/O deduction and allow breakdown by truck/unit, then transaction.

Example:

```text
ABC Transport

Unit 1100      ...
Unit 1104      ...
Unit 1120      ...
-----------------
Total Fuel/Card deduction
```

Each unit expands/drills into provider transaction detail.

---

## 18. O/O fuel pricing agreement

For company drivers, the O/O fuel-charge setup is disabled/not applicable.

For an O/O participating in the company fuel program, supported pricing methods include:

- Pump price / no provider discount passed through
- Full provider/company discount
- Fixed cents per litre/gallon passed to O/O
- Percentage of provider discount passed to O/O

Example concept:

```text
Pump price:             3.00
Provider discount:      0.25
Company/provider cost:  2.75
O/O discount allowed:   0.05
O/O charged price:      2.95
```

Percentage means **percentage of the provider discount**, not percentage of pump price.

### 18.1 Fuel pricing belongs to compensation/settlement relationship

The agreement ultimately belongs to the O/O/payee compensation/settlement relationship, even if it is configured during onboarding.

It should be effective-dated so historical transactions use the rule that applied on their transaction date.

### 18.2 Combined vs segmented onboarding

TruckERP already supports the concept of combined vs segmented setup.

- **Combined/smaller company:** authorized owner/admin/reviewer may configure O/O fuel pricing during review
- **Segmented/larger company:** hiring manager approves the application/qualification side, then HR/Payroll/Compensation configures monetary terms downstream

Hiring manager should not be forced to decide compensation/fuel pricing in segmented mode.

Permissions should govern who can edit the fuel agreement; do not hard-code a single department name as the only possible owner.

---

## 19. Financial responsibility is separate from transaction classification

Two questions must be answered independently:

1. What is this transaction?
2. Who is financially responsible?

Examples:

### Company truck / company driver

- Fuel → company expense
- DEF → company expense
- Coolant/oil/additive/product → company expense; **no driver deduction**
- Repair/service → company expense unless explicit policy says otherwise
- Cash advance → driver receivable/payroll deduction under policy

### Owner-operator truck

- Fuel → O/O charge according to fuel pricing agreement
- DEF → O/O deduction
- Coolant/oil/additive/product → O/O deduction
- Repair/service → normally O/O deduction subject to contract/rule
- Cash advance → O/O/payee deduction unless explicitly driver-specific under policy

### Required financial destinations

Before posting, every classified provider transaction must resolve to an allowed destination such as:

- Company expense
- Owner-operator/payee deduction
- Driver receivable/deduction
- Load/Dispatch expense/accessorial flow
- Toll module / toll settlement flow
- Explicit reviewed `Other`

No transaction may disappear or remain financially unassigned while the provider batch is finalized.

---

## 20. O/O settlement transaction detail

An O/O deduction must keep full operational context, not only the amount.

For example a coolant charge should retain/display:

- O/O/payee
- Unit number
- Driver name/context
- Provider
- Transaction date/time
- Site/location
- Product
- Auth/provider transaction ID where available
- Currency
- Provider amount
- O/O settlement deduction amount

The O/O portal can show a reduced view, but the source detail remains drillable/auditable.

---

## 21. O/O portal reduced view vs Admin full view

Admin/review sees the full source and financial record.

O/O portal should normally show only useful settlement-facing fields such as:

- Date/time
- Unit number
- Driver
- Location/station
- Product
- Quantity
- Price charged to O/O
- Total deduction
- Currency

Optionally provide provider retail/discount details where the product policy wants that transparency.

Do not maintain a separate O/O transaction model; both views come from the same canonical transaction record.

---

## 22. Lumper boundary — Dispatch/Load owns the load relationship

Lumper is relevant because it may occasionally come through a fuel card, but it is not a Fuel/Card-owned business workflow.

Fuel/Card may:

- Ingest the provider transaction
- Classify it as `LUMPER`
- Preserve provider payment facts

Dispatch/Load owns:

- Driver receipt upload
- Receipt review
- Attaching receipt/charge to the correct Load
- Broker reimbursement/accessorial
- Receivable state

Do not auto-attach a lumper merely because the driver had an active trip. Multi-load/multi-stop trips can make that wrong.

When carrier paid a lumper that broker owes back, the Load/accounting side later represents both:

- carrier-paid expense
- broker reimbursement receivable/accessorial

This is a cross-module TODO/boundary, not part of the initial Fuel parser implementation.

---

## 23. Toll and other cross-module boundaries

A fuel-card provider can carry transactions that ultimately belong elsewhere.

Examples:

- `TOLL` → Toll module / toll settlement rules
- `LUMPER` → Dispatch/Load/accessorial workflow
- `CASH_ADVANCE` → Driver/O-O settlement/payroll rules
- `SCALE` → company/O-O/load policy as configured

Fuel/Card remains the source ingestion and classification point; it must not absorb every downstream business workflow into one module.

---

## 24. Strict reconciliation — core financial invariant

This module moves money. Reconciliation is mandatory.

### 24.1 Every provider line accounted for exactly once

Required invariant:

```text
All truck transactions
+ all other classified transactions
+ explicitly accounted provider rounding variance (only where allowed)
= Provider control total
= Validated total
```

And:

```text
missing transactions = 0
unintended duplicate transactions = 0
unresolved financial destinations = 0
unexplained variance = 0
```

### 24.2 Grand total alone is not sufficient

A batch can balance overall while individual trucks are wrong.

Therefore reconciliation must use all provider controls available, not only the final invoice amount.

Potential control levels include:

1. Transaction-row integrity/arithmetic where source supports it
2. Date + unit association
3. Unit totals where source supports them
4. Card totals
5. Product totals
6. Currency totals
7. Invoice/provider grand totals

A matching grand total does not excuse an incorrect unit/date/card assignment.

### 24.3 Transaction date must stay attached to the exact row

Swapping dates between two otherwise valid rows can leave unit and invoice totals unchanged but still send the money to the wrong settlement period or owner.

Therefore row-level date/unit integrity is a required gate.

### 24.4 Provider total and validated total

The final summary must clearly prove, per applicable currency:

```text
Provider Total = Validated Total
Difference = 0.00
```

while also proving every source row is accounted for exactly once.

---

## 25. PDF financial gates

PDF is riskier than API because extraction itself can be wrong.

Required conceptual gates:

1. Source/document validity
2. Correct provider/profile
3. Parser completeness
4. Correct row-type classification
5. Row boundary integrity
6. Critical-field completeness
7. Date + unit integrity
8. Provider subtotal/card/product controls
9. Currency/invoice controls
10. Duplicate detection
11. Human review completed
12. Truck resolution
13. Historical ownership/payee resolution
14. Financial-responsibility resolution
15. Pricing agreement validation
16. Settlement eligibility

If any required money gate is `FAIL` or `REVIEW`, do not post.

---

## 26. API path — provider facts are authoritative, handling is still strict

API is simpler because the provider supplies structured data directly.

TruckERP accepts the provider's raw numbers as authoritative source facts and does not rewrite them.

Still required:

- Persist/freeze raw payload or source evidence
- Provider transaction uniqueness/idempotency
- Strict normalization without changing meaning
- Historical truck resolution
- Historical ownership/payee resolution
- Financial-responsibility resolution
- O/O pricing validation
- Settlement gate

Hard invariants should include concepts such as:

```text
provider transaction ID = unique within provider/account scope
raw amount = immutable
raw unit = immutable
raw transaction datetime = immutable
```

A repeated provider transaction must not create a second charge.

If a provider reuses the same transaction ID with changed values, treat it as an amendment/reversal/review case rather than silently overwriting posted history.

---

## 27. Duplicate and reconciliation behavior across intake sources

The same purchase may appear through more than one intake path:

```text
MANUAL_DRIVER
then PDF
then API
```

TruckERP must prevent double posting.

Strong duplicate/match signals may include:

- Provider transaction/auth ID
- Provider + account + card + transaction datetime
- Unit + product + quantity + amount + datetime
- Other provider-specific identifiers

Do not automatically merge ambiguous transactions without an auditable rule/review.

---

## 28. Settlement/payroll handoff

A provider invoice total does **not** equal one O/O's payroll/settlement deduction.

The provider batch first reconciles as a source. Then eligible transactions are routed to the correct financial party.

Settlement uses only transactions that belong to:

- Correct owner/payee
- Correct truck(s)
- Correct transaction dates
- Correct pricing agreement
- Correct settlement period
- Correct financial-responsibility path

### 28.1 Provider amount vs settlement amount

Keep separate:

- Provider amount/cost
- O/O contractual settlement charge

They may differ because the O/O fuel agreement can pass through all, some, or none of the provider discount.

Never alter provider facts to make them equal settlement charges.

### 28.2 Settlement reconciliation

For one settlement:

```text
sum(eligible O/O transaction charges)
= settlement Fuel/Card deduction
```

The O/O must be able to drill down from total → unit → individual provider transaction.

---

## 29. Review/process summary

After all PDFs are reviewed, Admin clicks `Process`.

The backend runs the gates and returns a summary rather than immediately hiding failures.

Useful summary values include:

- Files reviewed
- Files passed
- Files needing review
- Transaction count
- Provider breakdown
- Currency breakdown
- Company transactions
- O/O transactions
- Driver/cash-advance items
- Unmatched trucks
- Unmatched owners/payees
- Duplicate transactions
- Reconciliation failures
- Provider total per currency
- Validated total per currency
- Difference per currency

`Finalize` becomes available only when all required gates pass.

After successful Finalize/OK, the review window closes and the batch is complete.

---

## 30. Audit and correction policy

Keep an audit trail for:

- Original PDF/API payload
- Parser output
- Reviewed/corrected value
- Reviewer
- Review timestamp
- Correction reason
- Provider-control reconciliation
- Card/unit/truck matching
- Ownership/payee resolution
- Financial-responsibility decision
- Pricing agreement used
- Settlement posting
- Reversal/adjustment

### 30.1 Parsed vs reviewed value

Where a human corrects extraction, retain both concepts:

```text
parsed_value
reviewed_value
review_reason
reviewed_by
reviewed_at
```

### 30.2 After posting

Do not silently rewrite posted financial history.

Corrections require an auditable adjustment/reversal workflow.

---

## 31. Conceptual status lifecycle

A batch may move through states such as:

```text
UPLOADED
PARSED
REVIEW_REQUIRED
REVIEWED
PROCESSING
RECONCILIATION_FAILED
RECONCILED
READY_TO_FINALIZE
FINALIZED
```

Exact implementation names remain to be decided, but the architectural distinction between parsing, human review, reconciliation, and financial posting is required.

A transaction may separately carry gate/readiness concepts such as:

```text
source_reconciled
truck_resolved
ownership_resolved
financial_responsibility_resolved
pricing_validated
settlement_eligible
posted
```

---

## 32. Data relationships to preserve

The Fuel/Card foundation must support relationships among:

```text
Provider
  ↓
Provider account
  ↓
Card
  ↓
Source transaction
  ↓
Unit-number snapshot
  ↓
Historical truck_id
  ↓
Historical owner/company
  ↓
O/O payee when applicable
  ↓
Pricing agreement when applicable
  ↓
Settlement/payroll posting
```

Driver is important operational context but is not always the financial owner of an O/O transaction.

---

## 33. First implementation sequence

Recommended implementation order after architecture lock:

1. Canonical Fuel/Card transaction schema
2. Provider import/batch schema
3. Provider/source control-total schema
4. Admin provider configuration model
5. BVD digital-PDF profile + strict hydration contract
6. BVD Admin review layout grouped by unit
7. Truck ownership + O/O/payee relationship confirmation
8. Effective-dated unit-number history
9. Effective-dated O/O fuel pricing agreement
10. PDF review queue UI (`left PDF / right parsed`, Save & Next)
11. Reconciliation engine and gate statuses
12. BVD API adapter
13. Matching/dedupe across sources
14. Fuel/Card Operations workspace
15. Manual driver entry
16. Nationwide provider profile + row-type rules
17. Settlement/payroll bridge
18. Cross-module classification hooks (Toll, Lumper, etc.)
19. Audit/reversal handling
20. Tests/fixtures
21. Establish Fuel Gold only after verified implementation

---

## 34. Required test families

Before Fuel can be treated as financially safe, tests should cover at minimum:

- BVD digital-PDF extraction
- BVD row/source mapping
- BVD provider totals
- Nationwide transaction vs card-total row detection
- Nationwide Canadian total row GST/QST placement
- Nationwide mixed CAD/USD reconciliation
- Provider rounding/variance behavior
- Duplicate PDF/API/manual transaction handling
- Historical unit-number resolution
- Historical O/O ownership resolution
- Company vs O/O financial responsibility
- Company-driver no-deduction product behavior
- Cash advance routing
- O/O fuel pricing modes
- Effective-date pricing changes
- Multi-truck O/O settlement breakdown
- Settlement total = eligible transaction charge sum
- Posted correction/reversal audit behavior

---

## 35. Current unresolved implementation details

The following remain intentionally unresolved until we have code/provider evidence or an explicit business decision:

- Exact database column types and decimal precision
- Provider-specific accepted rounding tolerance
- Exact BVD API contract
- Exact Nationwide API/CSV contract
- Which additional providers are implemented after BVD/Nationwide
- Final settlement/payroll FK/table structure
- Exact provider-card assignment history table design
- Exact financial-responsibility policy for scale/parking/repair in edge cases
- Exact manual-driver receipt requirements
- Final UI wording for `Save & Next`, `Process`, `Finalize`
- Final permission names for Fuel Admin / compensation setup

Do not invent these details before evidence or product decisions exist.

---

## 36. Architecture lock summary

The Fuel/Card module is not just a fuel parser.

It is a provider-ingestion + financial-control subsystem with these locked principles:

1. Three intake paths: API, digital PDF, manual driver entry.
2. Many providers, one canonical transaction model.
3. Provider facts are immutable source evidence.
4. BVD is the first production provider profile; Nationwide is the second real layout proof.
5. Digital PDFs use their digital structure first; OCR is fallback for scanned/unusable documents.
6. AI/mini-model extracts into strict JSON but does not decide money ownership.
7. Admin reviews PDF left / parsed data right, Save & Next through a queue, then Process → Summary → Finalize.
8. Unit number is not permanent truck identity; historical resolution uses transaction date/time.
9. Truck ownership/O-O payee must be explicit and historical.
10. O/O fuel pricing belongs to the O/O/payee agreement and is effective-dated.
11. Company drivers are not charged for company-truck operating products such as coolant.
12. Cash advances route to driver/O-O responsibility rather than becoming generic truck fuel expense.
13. Lumper/load reimbursement remains a Dispatch/Load workflow after Fuel/Card ingestion/classification.
14. Every provider line must be accounted for exactly once.
15. All classified transaction totals + allowed control adjustments must reconcile to provider controls and validated totals by currency.
16. Grand-total equality alone is insufficient; row/date/unit/card controls matter.
17. Parser review does not bypass financial gates.
18. Provider amount and O/O settlement amount remain separate.
19. Multi-truck O/O settlement must show truck-level and transaction-level breakdown.
20. Posted financial history is corrected by audited adjustment/reversal, never silent rewrite.
