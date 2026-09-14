# TruckERP Fuel / Fuel-Card Module Design

**Status:** Discussion/design lock candidate — not implementation-complete, not Gold.

**Purpose:** Define the Fuel / Fuel-Card module before implementation. This document captures the agreed business workflow, BVD PDF contract, provider/API boundary, owner-operator charging rules, truck ownership relationships, reconciliation gates, and payroll/settlement handoff.

---

## 1. Core design rule

A fuel-card provider transaction is **not automatically a fuel expense**.

The provider (BVD first, future providers later) is the payment source. Each transaction must preserve the provider's original facts and then be classified/routed by TruckERP.

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

### 2.1 API

Provider API values are authoritative raw provider facts. TruckERP must not rewrite provider amounts, dates, unit numbers, or provider transaction identifiers.

The strictness is in **how TruckERP handles and posts the API data**:

- freeze the raw payload
- idempotency / duplicate protection
- normalize formats without changing meaning
- resolve truck historically
- resolve owner/payee historically
- apply the correct effective fuel agreement
- only then make the transaction settlement-eligible

### 2.2 Digital PDF

The PDF path is higher risk because the document must be parsed. Parser output is **evidence, not authorization to move money**.

The PDF path therefore requires human review plus automated reconciliation gates before posting.

### 2.3 Manual driver entry

Manual entry is driver-level input but still enters the same canonical transaction workflow. Driver identity should normally come from the logged-in user, and the assigned truck should default where possible.

Manual entry should be simple for the driver and not expose accounting complexity.

---

## 3. Front end, backend, and admin boundary

The module has three major surfaces.

### 3.1 Fuel/Card operations front end

Operational routes should be separate from Admin integration settings, for example:

```text
/fuel
/fuel/transactions
/fuel/imports
/fuel/review
```

The working area shows transactions, imports, reconciliation/review status, filters, truck/unit grouping, provider, source, owner-operator/payee, and posting state.

### 3.2 Backend

The backend owns:

- canonical transaction schema
- provider import batches
- provider adapters
- PDF parser profile integration
- normalization
- duplicate detection
- historical truck resolution
- ownership/payee resolution
- financial responsibility routing
- owner-operator pricing calculations
- reconciliation gates
- settlement eligibility
- audit trail

### 3.3 Admin integration settings

The existing `/admin/integrations/fuel` route is the correct place for provider configuration.

Admin should configure:

- provider
- enabled/disabled
- connection type
- base/API endpoint
- account/client identifier
- API credential references
- environment
- automatic sync
- sync frequency
- last sync/result
- test connection

Credentials must remain server-side. The browser must not receive stored API secrets after save.

TruckERP should be multi-provider from day one even if BVD is the first provider.

---

## 4. BVD PDF is the first real provider contract

The BVD digital PDF defines the first concrete statement layout.

The parser must preserve the provider fields as printed rather than replacing them with generic names that lose provider meaning.

### 4.1 BVD statement/import header

At import-batch level capture at least:

- provider
- invoice number
- invoice date
- statement start date
- statement end date
- due date when present
- client/account identity
- source file
- source type (`PDF`)
- import/review/reconciliation status
- provider control totals
- created/imported/reviewed metadata

### 4.2 BVD transaction row fields

Preserve the BVD transaction layout:

```text
Auth Code
Driver Name
Unit #
Date / Time
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

These are provider facts and must remain traceable exactly as received/parsed.

### 4.3 BVD product codes

Preserve the provider product code exactly and separately derive TruckERP classification.

Known BVD legend from the reviewed sample:

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

Do not replace the raw provider product code with a generic category.

Example:

```text
product_code = "TA"            # provider fact
transaction_type = "FUEL"      # TruckERP derived classification
```

---

## 5. Canonical schema direction

Use two primary layers.

### 5.1 `fuel_card_import_batches`

Represents the provider invoice/statement/import.

Candidate fields:

```text
id
provider_id
provider_code
source_type                 API | PDF | MANUAL
invoice_number
invoice_date
statement_start_date
statement_end_date
due_date
provider_account_ref
source_document_key
raw_payload_hash            API path when applicable
provider_total
validated_total
currency
status
uploaded_by
reviewed_by
reviewed_at
processed_at
finalized_at
created_at
updated_at
```

### 5.2 `fuel_card_transactions`

Provider facts:

```text
id
import_batch_id
provider_id
provider_transaction_id
auth_code
card_reference
transaction_datetime
driver_name_snapshot
unit_number_snapshot
site_number
site_name
site_city
province_state
country
product_code
quantity
unit_of_measure
retail_price
billed_price
pre_tax_amount
hst_amount
gst_amount
pst_amount
qst_amount
discount_rate
discount_amount
final_amount
currency
raw_description
```

TruckERP-derived fields must be separate from provider facts:

```text
transaction_type
truck_id                    nullable until resolved
driver_id                   nullable until resolved
owner_operator_payee_id     nullable until resolved
trip_id                     nullable
financial_responsibility
pricing_agreement_id        nullable
settlement_id               nullable
match_status
review_status
source_reconciled
transaction_validated
truck_resolved
ownership_resolved
pricing_validated
settlement_eligible
posted
```

The original provider facts remain immutable after finalization. Corrections after posting require an audited adjustment/reversal, not silent mutation.

---

## 6. BVD PDF review workflow

Admin may upload one PDF or many PDFs, including PDFs from more than one provider.

After upload, parsing can be started for the queue.

### 6.1 Review workspace

Use a side-by-side review workflow:

```text
LEFT:  Original PDF
RIGHT: TruckERP parsed fields / transaction rows
```

The right side should mirror the provider layout as closely as practical, with the BVD view grouped operationally by **Truck Unit #**.

Admin reviews the current PDF, corrects staging values when necessary, then clicks:

```text
Save & Next
```

That action:

- saves the reviewed staging data
- marks that document reviewed
- automatically advances to the next PDF on the left
- automatically loads the next parsed provider window on the right

Repeat until the queue is complete.

### 6.2 Process after all PDFs are reviewed

When the review queue is finished, the admin clicks:

```text
Process
```

TruckERP then runs the reconciliation and financial gates behind the scenes.

### 6.3 Summary

After processing, show a final summary containing:

- files reviewed
- provider(s)
- transaction count
- truck/unit totals
- other expense totals
- unmatched/review-required items
- duplicates
- provider total
- validated total
- difference
- gate failures if any

If every required gate passes, admin confirms/finalizes and the review window closes.

Human review is a gate, but it does not replace automated financial validation.

---

## 7. BVD front-end layout rule: group by Truck Unit #

The BVD operational review should preserve the provider row layout but group transaction rows by `Unit #`.

Example concept:

```text
UNIT 1100
  Auth | Driver | Date/Time | Site | Prod | QTY | Retail | Billed |
  Pre Tax | HST | GST | PST | QST | Disc Rate | Disc Amt | Final | CUR

  ...transactions...

  UNIT TOTAL

UNIT 1104
  ...transactions...

  UNIT TOTAL
```

The provider statement facts stay intact while TruckERP adds relational context separately.

---

## 8. Truck identity and unit-number history

`unit_number` is not the permanent identity of a truck.

Use an immutable internal `truck_id`.

Example:

```text
truck_id = 842
unit_number = 1100
```

Fuel/Card transactions must preserve:

```text
unit_number_snapshot = "1100"
truck_id = 842
```

If the physical truck is later renumbered, old transactions still show the original provider unit number.

### 8.1 Unit-number history

TruckERP needs effective-dated unit-number history, conceptually:

```text
truck_id
unit_number
effective_from
effective_to
reason
changed_by
```

Historical provider matching uses **transaction date/time + unit-number history**, not the truck's current unit number.

### 8.2 Renumbering vs replacing a truck

- Same physical truck, new unit number -> same `truck_id`, new unit-number history row.
- Different physical truck replacing the old truck -> new `truck_id`.

Do not convert one physical asset into another by simply changing VIN/unit fields.

---

## 9. Truck ownership must be explicit

When adding a truck, TruckERP must identify ownership/relationship, for example:

```text
Company owned
Owner-operator owned
Leased / other supported relationship
```

If owner-operator owned, select the owning O/O business/payee.

A single O/O may have one truck today and five trucks later.

The financial model therefore cannot assume:

```text
one owner-operator = one driver = one truck
```

The durable relationship is closer to:

```text
OWNER-OPERATOR BUSINESS / PAYEE
  -> Truck 1100
  -> Truck 1104
  -> Truck 1120
  -> ...
```

Settlement is with the O/O/payee while transaction detail remains broken down by truck/unit and driver.

---

## 10. Owner-operator fuel pricing agreement

The current boolean `participates_in_fuel_discount_program` is not sufficient by itself.

For an owner-operator participating in the fuel program, TruckERP needs a pricing rule.

Supported methods:

```text
PUMP_PRICE
FULL_PROVIDER_DISCOUNT
FIXED_CENTS_DISCOUNT
PERCENT_OF_PROVIDER_DISCOUNT
```

Example:

```text
Pump price:                 $3.00
Provider/company discount:  $0.25
Company net cost:           $2.75
O/O allowed discount:       $0.05
O/O charge price:           $2.95
```

For percentage mode, the percentage applies to the **provider discount**, not the pump price.

Example:

```text
provider discount = $0.25
O/O receives 20% of discount = $0.05
O/O price = $3.00 - $0.05 = $2.95
```

Unless explicitly allowed by future policy, the O/O discount should not exceed the provider discount.

### 10.1 Company driver rule

For a company driver, the O/O fuel charge/pricing fields are disabled/not applicable.

```text
employment_relationship_type = company_driver
-> no O/O fuel pricing rule
```

### 10.2 Workflow ownership

Small-company/combined onboarding mode:

- reviewer/admin may configure the compensation/fuel rule during review

Large-company/segmented onboarding mode:

- hiring manager approves the applicant
- application moves to downstream HR/Payroll/Compensation setup
- downstream authorized staff configure the fuel pricing agreement
- final onboarding waits for required downstream setup

Do not hard-code this to a literal HR job title. Use permission/capability ownership.

### 10.3 Agreement belongs financially to O/O/payee

Even if the rule is initially configured during person onboarding, the durable financial agreement belongs to the O/O/payee/business relationship so that one O/O with multiple trucks can be settled correctly.

The agreement should be effective-dated because historical transactions must use the rule in effect on the transaction date.

---

## 11. Financial responsibility rules

Classification and financial responsibility are separate concepts.

Every provider transaction must have a financial destination before final posting.

Candidate responsibility types:

```text
COMPANY
OWNER_OPERATOR
DRIVER
LOAD_DISPATCH
OTHER_REVIEWED
```

### 11.1 Fuel

- Company truck/company driver -> company expense, no driver fuel deduction.
- O/O truck -> O/O charge according to effective O/O fuel agreement.

### 11.2 DEF / coolant / oil / additive / truck products

Company truck/company driver:

```text
Provider expense -> Company expense
Driver deduction -> $0
```

The employee may legitimately buy coolant or another truck product for the company's equipment.

O/O truck:

```text
Provider expense -> carrier/provider payable
O/O settlement deduction -> full applicable amount unless another explicit contract rule exists
```

The O/O deduction must preserve:

- O/O/payee
- unit number
- truck
- driver name
- transaction date/time
- provider
- auth/provider transaction ID
- site/location
- product
- amount/currency
- source document/API reference

### 11.3 Cash advance

Cash advance is person/payee financial responsibility rather than a normal truck operating expense.

- Company driver -> driver receivable / authorized payroll deduction
- O/O -> O/O/payee settlement deduction

### 11.4 Lumper

Fuel/Card may ingest/classify a lumper transaction, but this module does not own final load association or broker reimbursement workflow.

Dispatch/Load owns:

- receipt upload/review
- load association
- broker reimbursement/accessorial
- receivable lifecycle

Do not auto-attach a lumper to a load merely because the driver had an active trip. Multi-load/multi-stop cases require Dispatch review unless an unambiguous rule is later established.

### 11.5 Toll

A provider-card toll transaction can be classified here, but downstream Toll/settlement policy determines financial treatment.

---

## 12. Reconciliation principle: this is money

The system must use multiple strict gates. A parser match or grand-total match alone is not enough.

**Parser output is not posting authority.**

A transaction cannot become payroll/settlement-eligible merely because it was parsed successfully.

---

## 13. PDF-specific gate chain

Recommended high-level flow:

```text
DIGITAL PROVIDER PDF
    -> document validation
    -> provider parser
    -> parsed staging
    -> human review
    -> source reconciliation
    -> transaction validation
    -> truck resolution
    -> ownership/payee resolution
    -> financial responsibility
    -> O/O pricing validation when applicable
    -> settlement eligibility
    -> final posting
```

### Gate 1 — Document identity

Validate the expected provider/document format and capture provider/invoice/period metadata.

### Gate 2 — Parser completeness

Critical fields cannot silently disappear.

For BVD fuel/card rows, critical identity/financial fields include at minimum:

- auth/provider transaction identity when present
- transaction date/time
- unit number when present
- product
- quantity when applicable
- final amount
- currency

Missing/ambiguous critical fields force review.

### Gate 3 — Row integrity

Where enough fields exist, recompute/check row arithmetic and make sure values from one row did not shift into another row.

### Gate 4 — Date + unit integrity

Transaction date/time and unit number must remain attached to the exact provider row.

A parser can produce the correct grand total and still be wrong if it swaps truck amounts or dates.

### Gate 5 — Unit reconciliation

For each unit represented in the source, the complete set of parsed rows assigned to that unit must reconcile to the source unit-level facts/control totals where the provider exposes them or where they can be deterministically derived from the source rows.

### Gate 6 — Card/product/subtotal reconciliation

Where BVD/provider supplies card totals, product totals, or subtotals, reconcile against them.

### Gate 7 — Provider grand total

All source transaction rows must reconcile exactly to the provider's statement/invoice control total, subject only to explicit decimal-rounding policy.

### Gate 8 — Exact accounting of every provider line

Every source transaction must be accounted for exactly once:

```text
no missing transaction
no duplicated transaction
```

A total can still match when one same-value transaction is duplicated and another is missing; therefore line-level identity is mandatory.

### Gate 9 — Truck resolution

Resolve:

```text
transaction_datetime
+ unit_number_snapshot
-> effective unit-number history
-> unique truck_id
```

If no unique truck can be proven, stop.

### Gate 10 — Ownership/payee resolution

Using the transaction date/time, determine whether that truck belonged to:

- company
- a specific O/O/payee

Do not use current ownership for historical transactions.

Missing/overlapping/ambiguous ownership stops posting.

### Gate 11 — Financial responsibility

Every transaction must route to exactly one recognized financial destination before finalization.

### Gate 12 — O/O pricing

For eligible O/O fuel transactions:

- find the effective pricing agreement on transaction date
- calculate the O/O charge
- preserve provider amount separately
- validate calculation

Provider amount and O/O settlement amount are different financial facts and must never be conflated.

### Gate 13 — Settlement eligibility

Only transactions that pass every required gate become settlement-eligible.

---

## 14. Provider total and validated total hard rule

The final batch must prove:

```text
ALL TRUCK-RELATED TRANSACTIONS
+ ALL OTHER CLASSIFIED EXPENSE TRANSACTIONS
= PROVIDER TOTAL
```

and:

```text
PROVIDER TOTAL
= VALIDATED TOTAL
```

Therefore:

```text
Provider Total - Validated Total = 0.00
```

No provider line may disappear merely because it is not fuel.

Truck-related and other transactions must together account for the entire provider source.

Examples of "other" routed transactions include:

- scale
- cash advance
- lumper
- parking
- toll
- product purchase
- repair/service
- reviewed other

If the totals do not reconcile, finalization is blocked.

---

## 15. Transaction date/time is authoritative for historical relationships

Do not use invoice date as a substitute for transaction date.

Maintain distinct timestamps:

```text
transaction_datetime   # when the purchase happened
invoice_date           # provider statement/invoice date
imported_at             # when TruckERP received it
posted_at               # downstream posting timestamp
settled_at              # settlement timestamp when applicable
```

The transaction date/time determines:

- unit-number history lookup
- physical truck identity
- historical ownership/payee
- effective O/O fuel agreement
- settlement-period eligibility
- driver/trip matching where applicable

A single provider invoice may contain transactions from different dates that belong to different settlement periods.

---

## 16. Settlement/payroll bridge

The Fuel/Card module does not hand payroll one invoice total.

It hands settlement/payroll the exact set of validated, eligible individual transactions for the correct payee and settlement period.

For an O/O with multiple trucks, the settlement must provide a breakdown by unit and allow drill-down to individual provider transactions.

Example:

```text
ABC Transport

Unit 1100      $1,200.10
Unit 1104      $1,580.32
Unit 1120      $1,506.00
              ---------
Fuel/Card deduction total = $4,286.42
```

Each unit must drill down to transaction details including driver, date/time, provider, site/location, product, amount, and source reference.

### 16.1 Settlement reconciliation

For a settlement:

```text
sum(eligible validated transaction charges for this payee + period)
=
settlement Fuel/Card deduction total
```

This is separate from provider-invoice reconciliation.

---

## 17. API-specific invariants

Provider API numbers are authoritative and immutable.

Hard rules:

```text
provider transaction ID = unique per provider/account
raw provider amount = immutable
raw provider unit number = immutable
raw provider transaction datetime = immutable
raw provider payload retained/hashed
```

TruckERP may change/review its own relational resolution before posting, but it does not rewrite provider facts.

If the provider later changes/reverses a transaction, treat that as a provider amendment/reversal workflow, not silent replacement.

---

## 18. PDF staging and correction audit

For PDF parse review, preserve both machine output and reviewed value where a correction occurs.

Conceptually:

```text
parsed_value
reviewed_value
review_reason
reviewed_by
reviewed_at
```

The original PDF remains immutable evidence.

Once finalized/posted, later changes require audited adjustment/reversal behavior.

---

## 19. Suggested statuses

### Import batch

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

### Transaction gates

```text
source_reconciled
transaction_validated
truck_resolved
ownership_resolved
financial_responsibility_resolved
pricing_validated
settlement_eligible
posted
```

A failed/review gate must prevent monetary posting.

---

## 20. Duplicate and idempotency rules

Strong duplicate signals include:

- provider + provider transaction ID/auth code
- provider + card + transaction datetime
- unit + quantity + amount + transaction datetime
- source document/import batch relationships

API imports must be idempotent.

PDF/manual/API duplicates must not result in double charges.

A manual driver entry later matched by API/PDF should become a reconciliation/match case, not a second financial transaction.

---

## 21. Provider facts vs TruckERP decisions

Keep these two layers visibly separate.

### Provider facts

What BVD/provider actually said:

- provider transaction ID/auth
- driver name snapshot
- unit number snapshot
- transaction date/time
- site/location
- product code
- quantity
- retail/billed pricing
- taxes
- discount
- final amount
- currency

### TruckERP decisions

What TruckERP resolved/calculated:

- transaction classification
- truck_id
- driver_id
- O/O/payee
- financial responsibility
- O/O pricing agreement
- O/O charge
- trip/load link when appropriate
- settlement eligibility
- posting status

Do not mutate provider facts to make them fit internal data.

---

## 22. Security and audit requirements

Audit at minimum:

- provider configuration changes
- credential configuration changes (never log secret values)
- imports
- parser corrections
- classification changes
- truck resolution/remapping
- ownership/payee resolution/remapping
- pricing agreement changes
- settlement posting
- duplicate resolution
- adjustments/reversals

Money-affecting actions require actor, timestamp, before/after values, and source context.

---

## 23. Tests required before Gold

At minimum:

- BVD PDF regression fixture tests
- parser field-map tests
- date + unit row-integrity tests
- row arithmetic tests
- card/product/subtotal reconciliation tests
- provider grand-total reconciliation tests
- missing-row test
- duplicated-row test
- unit-history truck-resolution tests
- historical ownership tests
- effective-dated O/O pricing tests
- company-driver no-deduction tests
- O/O product-deduction tests
- cash-advance routing tests
- API idempotency tests
- manual/API/PDF duplicate reconciliation tests
- settlement-period eligibility tests
- multi-truck O/O settlement breakdown tests
- audit tests

Fuel Gold is established only after the module is verified. Until then, this is a design/implementation document, not a Gold declaration.

---

## 24. Implementation order

Recommended order:

```text
1. Canonical provider/card schema
2. BVD field contract + parser JSON contract
3. Admin provider configuration
4. Truck ownership + O/O/payee relationship review
5. Effective-dated unit-number history
6. O/O fuel pricing agreement
7. BVD PDF parser/profile
8. PDF review queue UI (PDF left / parsed window right / Save & Next)
9. Reconciliation engine and gates
10. BVD API adapter
11. Matching + dedupe/idempotency
12. Fuel/Card operations UI grouped by Unit #
13. Manual driver entry
14. Financial responsibility routing
15. Settlement/payroll bridge
16. Cross-module hooks (Lumper/Dispatch, Toll, etc.)
17. Audit + regression tests
18. Establish Fuel Gold only after verification
```

---

## 25. Locked principles from current discussion

1. **Fuel-card transaction does not mean fuel expense.**
2. **One provider source can contain truck expenses and non-truck expenses.**
3. **Every provider line must be accounted for exactly once.**
4. **All truck + other classified expenses must equal Provider Total.**
5. **Provider Total must equal Validated Total.**
6. **Parser output cannot directly move money.**
7. **Human review does not bypass automated gates.**
8. **Transaction date/time controls historical matching and settlement eligibility.**
9. **Unit number is a historical operational identifier; `truck_id` is permanent identity.**
10. **Truck ownership must identify company vs O/O and which O/O/payee.**
11. **O/O pricing agreement is effective-dated and financially belongs to the O/O/payee relationship.**
12. **Company drivers are not charged for ordinary company-truck products such as coolant.**
13. **O/O truck products paid by the carrier are normally O/O deductions unless an explicit rule says otherwise.**
14. **Cash advance routes to driver/O/O financial responsibility, not ordinary truck expense.**
15. **Lumper load association belongs to Dispatch/Load, not Fuel/Card.**
16. **Provider facts stay immutable; TruckERP decisions live separately.**
17. **No unresolved/ambiguous money-routing item may post.**
18. **Settlement must show unit-by-unit and transaction-level detail for O/O deductions.**

---

## 26. Open items still requiring implementation-level decisions

These are intentionally not invented here and should be decided with real provider/API evidence or business policy:

- exact BVD API authentication and endpoint contract
- exact provider credential storage mechanism already preferred by platform infrastructure
- exact schema names/column types/indexes after checking current tenant DB conventions
- exact effective-dated ownership table shape if one already exists or needs extension
- exact monetary rounding policy per provider/currency/unit
- whether specific product/repair categories need configurable deduction policies beyond the agreed default rules
- whether O/O truck-level fuel-pricing overrides are needed beyond the O/O/payee default
- exact settlement posting model/FKs after Payroll module review
- exact cross-module contract for Toll
- exact cross-module contract for Lumper/Dispatch/Accounts Receivable

Do not fill these gaps speculatively during implementation; inspect existing models and real provider data first.
