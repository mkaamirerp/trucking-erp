# TruckERP Fuel / Fuel-Card Module Design

**Status:** Discussion/design lock candidate — architecture foundation only; not implementation-complete and not Gold.

**Purpose:** Capture the full Fuel / Fuel-Card architecture before implementation so provider parsing, truck ownership, owner-operator charging, reconciliation, review, settlement/payroll, Dispatch/Load boundaries, and future provider integrations are built on one consistent foundation.

**Governance:** This document governs architecture. `docs/FUEL_CARD_IMPLEMENTATION_PLAN.md` governs execution sequence. The implementation plan does not replace this design.

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

TruckERP relationships and later derived amounts are separate:

- `truck_id`
- `driver_id`
- `owner_operator_payee_id`
- classification
- financial responsibility
- pricing agreement
- settlement/payroll link
- gate statuses
- `owner_operator_charge_amount` (TruckERP-derived pricing/settlement; never provider source)

Do not use one field for both provider terminology and TruckERP classification. Do not destroy a provider currency representation when mapping to ISO. Do not derive `transaction_date` from a UTC `transaction_datetime`.

### 1.5 Money / decimal precision

Lock this before Segment 1 schema implementation.

Financial calculations must use decimal arithmetic (`Decimal` / PostgreSQL `NUMERIC`). Never use binary floating point (`float`, IEEE 754) for quantity, price, tax, discount, total, or owner-operator charge.

Canonical tenant-DB column precision/scale:

| Canonical field | PostgreSQL type | Purpose |
|---|---|---|
| `quantity` | `NUMERIC(14, 4)` | Volume or count |
| `unit_price` | `NUMERIC(14, 6)` | Provider unit cost; extra scale for fuel unit prices |
| `provider_discount_rate` | `NUMERIC(10, 6)` | Provider discount rate as supplied; store the documented rate meaning (percent vs fraction) without converting silently |
| `provider_discount_amount` | `NUMERIC(14, 4)` | Provider discount money amount |
| tax amounts (`tax_amount`, HST, GST, PST, QST, and other provider tax components) | `NUMERIC(14, 4)` | Each tax component and any canonical tax total |
| transaction totals and related money (`total_amount`, pre-tax, billed, retail, fees) | `NUMERIC(14, 4)` | Provider money amounts used for reconciliation |
| owner-operator charge amounts | `NUMERIC(14, 4)` | Calculated settlement charge; remains separate from provider total |

Exact provider numeric strings belong in `provider_raw` (or equivalent) even after canonical hydration.

Rounding occurs only at documented financial boundaries:

1. Hydration into a canonical `NUMERIC` column (quantize to that column's scale). If the source has more fractional digits than the column, keep the extra digits in source/raw evidence. If quantization would change reconciliation against provider controls, the row/batch is `REVIEW`, not silently forced equal.
2. Currency minor-unit rounding only at settlement/payroll posting, or at a displayed-control comparison that has an evidenced provider rounding policy.
3. Never round source amounts to force grand-total equality.

Default quantization mode is round-half-even unless a captured provider contract requires another mode. JSON/API handoff of money/quantity must use decimal-safe representation (decimal string or equivalent), not native float.

### 1.6 Three transaction identities

Keep these identities separate. Do not collapse them into one `vendor_txn_id` / primary key.

```text
1. PROVIDER TRANSACTION IDENTITY
   Auth code / provider transaction number / provider-supplied unique id
   when the source actually supplies one.
   Scoped by provider + account (or the narrower scope the provider documents).
   May be omitted, reused, or collide across accounts/days.

2. PROVIDER SOURCE-ROW IDENTITY
   Identity of this line inside this source (batch + source order / row id /
   file position). Every ingested row has this even when the provider
   supplies no transaction number.

3. TRUCKERP CANONICAL TRANSACTION IDENTITY
   TruckERP surrogate identity of the canonical Fuel/Card transaction.
```

A provider auth/transaction number is never automatically the canonical primary identity.

Dedupe and idempotency must account for providers that omit, reuse, or scope identifiers differently. A repeated provider id with changed values is an amendment/reversal/review case, not a silent overwrite of posted history. File/hash idempotency and row-level dedupe remain independent.

### 1.7 Provider event type: raw vs canonical

Do not use one field to represent both provider terminology and TruckERP classification.

- `provider_event_type_raw` = exact provider value when supplied
- canonical `provider_event_type` = TruckERP classification

Canonical event type must support at least:

```text
PURCHASE
CREDIT
REFUND
REVERSAL
VOID
OTHER
UNKNOWN
```

An unknown provider value must never be coerced to `PURCHASE`. Preserve the raw value and classify as `UNKNOWN`. `UNKNOWN` is REVIEW-eligible later; it is still source evidence, not a guessed purchase.

### 1.8 Currency: raw vs canonical

Separate:

- `currency_raw` = exact provider representation (example: BVD `CN`)
- `currency` = canonical ISO-style TruckERP value (example: `CAD`)

Never destroy the provider representation when normalizing currency. Fuel reconciles in the original provider currency. Consolidated/base/reporting-currency conversion belongs downstream to Accounting/Reporting and must never overwrite Fuel source amount or currency.

### 1.9 Owner-operator charge provenance

`owner_operator_charge_amount` is a later TruckERP-derived financial value, not provider source truth.

It may remain nullable on the canonical transaction. It is grouped with derived pricing/settlement/resolution data. Segment 1 must never populate or calculate it. Provider parsing must never hydrate it. Fuel AI extraction must never output or hydrate it. Later O/O pricing/settlement logic owns it.

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

### 4.3 Disabled connections remain identifiable — architecture lock

Tenant provider configuration controls:

- credentials;
- API/file sync;
- polling/scheduling;
- connection health;
- preferred/default UX;
- provider automation.

It does **not** control whether TruckERP knows how to identify a manually uploaded historical document.

Provider identification checks **all currently evidenced provider profiles** in the master `fuel_provider_profiles.json` (today exactly `BVD` and `NATIONWIDE`). It does **not** compare only providers currently enabled in tenant configuration.

Example: a tenant switches from BVD to Nationwide. Three months later an old BVD statement/credit arrives. TruckERP must still recognize the document as BVD because the BVD global profile exists.

Disabled provider connections are **soft-disabled / history-preserving**. Do not erase historical connection records.

---

## 5. Provider architecture

```text
Provider PDF / structured file / API
        ↓
Shared acquisition / OCR / OpenAI transport (when needed)
        ↓
ONE generic Fuel parser pipeline
  (Fuel AI handoff contract + mechanical validator)
        ↓
Provider profile / rules JSON (BVD, Nationwide, …)
        ↓
Same canonical Fuel transactions + controls
        ↓
Shared reconciliation + ownership + settlement gates
```

**Architecture lock:** TruckERP builds **one generic Fuel parser**, not one parser engine per provider.

Provider-specific knowledge belongs primarily in **one master provider profile JSON**
(`app/contracts/fuel_provider_profiles.json`) with **exactly one current evidenced
section per provider** (top-level keys today: `BVD`, `NATIONWIDE`). Each section is
identified by `provider_code` + `profile_version` (traceability stamp; no
`profile_code` / `statement_v1` identity). Sections hold anchors, field aliases,
currency mappings, control rules, product legends, and REVIEW
conditions. Profiles are data consumed by the shared pipeline. Do **not** create
`bvd_parser.py`, Nationwide-only transaction models, or duplicate validators/reconcilers
per provider.

Provider-specific **raw source labels** (BVD `CUR` / `Billed`, Nationwide `Currency` /
`Ex-GST ($/U)`, etc.) live only in that provider’s master-JSON section (`field_aliases`
and semantics). Generic Python operates on canonical fields such as `currency_raw` and
`unit_price` after alias application.

**Layout resolution:** given a provider code, select that provider’s current profile
section from the master JSON, then run deterministic (case/whitespace-normalized) anchor
matching. Missing/mismatched required anchors → `PROVIDER_LAYOUT_UNRECOGNIZED` / REVIEW.
If multiple layout versions are ever registered for one provider, zero matches →
unrecognized, multiple matches → `PROVIDER_LAYOUT_AMBIGUOUS` / REVIEW. Never silently
accept an unmatched layout.

**Control-row classification** uses profile-declared deterministic rules (`field_equals`
on a named row-label field, `line_prefix` / `line_equals` on dedicated line text). Do not
substring-search arbitrary transaction values for words such as `TOTAL`. Amount alone
never proves a purchase (`INSUFFICIENT_TRANSACTION_EVIDENCE_AMOUNT_ONLY` → UNKNOWN/REVIEW).

**UOM / price-basis fallbacks** may exist as reusable profile vocabulary
(`quantity_unit_by_currency_fallback`, `unit_price_basis_by_currency`) but actual mappings
are **provider-section scoped and evidence-backed** (e.g. Nationwide only). There is no
global Fuel rule that CAD=litres or USD=gallons. Explicit source UOM / semantics always
override profile fallback.

Thin source adapters are allowed only when a real deterministic format requires translation into the same Fuel contract (for example a future evidenced structured export). Adapters must not become a second business engine.

Each provider profile owns its source interpretation:

- Header fields / labels
- Transaction-row indicators
- Control/subtotal row indicators
- Currency behavior / evidenced mappings
- Provider-specific price/discount meanings
- Deduplication identifiers if supplied
- Layout/version recognition anchors

Shared TruckERP logic owns:

- Canonical transaction + control persistence
- Generic Fuel AI contract and mechanical validation
- Truck resolution
- Historical ownership/payee resolution
- Classification
- Financial responsibility
- O/O pricing
- Settlement eligibility
- Audit

BVD is the first evidence-backed provider profile proving this architecture. Nationwide and later providers (WEX, Comdata, Pilot, Love's, etc.) must reuse the same Fuel parser/handoff/validator with their own profile/rules.

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

Fuel reconciles and preserves original provider currency independently. Consolidated/base/reporting-currency conversion belongs to Accounting/Reporting. Any future conversion record must retain rate, rate source, as-of timestamp, from-currency, to-currency, and converted amount. It must never overwrite Fuel source amount or currency.

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
- Output `truck_id`, `driver_id`, historical card/account assignment, owner/payee, O/O pricing, financial responsibility, settlement, downstream accounting, posting/finalization, or `owner_operator_charge_amount`

For known digital provider layouts, deterministic/provider-profile structure should drive extraction. AI is a constrained helper, not a free-form page interpreter.

### 8.3 Row integrity rule

Values belonging to one physical/logical provider row must remain together.

Example:

```text
card + unit + date + city + product + quantity + price + total + currency
```

must stay as one transaction row. Do not take card/unit from one row and price/quantity from another.

### 8.4 Provider layout drift — architecture lock

Provider parser profiles must be versioned/fingerprinted using deterministic expected anchors, header markers, control markers, and layout markers.

Unrecognized layout:

```text
PROVIDER_LAYOUT_UNRECOGNIZED -> REVIEW
```

AI must not silently compensate for an unrecognized financial-document layout. Implementation belongs with provider parsing segments; this is an architecture lock only.

### 8.5 Strict provider identification — architecture lock

Identification is deterministic against evidenced profiles in the master provider JSON (all evidenced profiles; not tenant-enabled-only — see §4.3).

Rules:

```text
0 profile matches  -> DOCUMENT_PROVIDER_UNKNOWN   -> REVIEW
exactly 1 matches  -> select that provider/profile and continue
2+ match           -> DOCUMENT_PROVIDER_AMBIGUOUS -> REVIEW
```

Never use “closest profile wins” or a fuzzy financial-document winner.

Provider selection and layout validation remain conceptually separate even when the current implementation performs both through anchors.

### 8.6 File safety before parsing — architecture lock

Before AI / full parsing:

1. Enforce a request file-count limit.
2. Stream each upload rather than trusting browser metadata.
3. Validate actual file content/signature, not only filename extension or Content-Type.
4. Enforce actual byte-size limit while reading.
5. Calculate SHA256 during the same streamed read.
6. Continue to use the shared document-safety infrastructure for deeper validation.

PDF magic bytes alone are **not** malware protection.

### 8.7 Async ingestion contract (durable worker required) — architecture lock

Multi-file parsing can take long enough that the eventual API/UI should be async-friendly:

```text
upload
  -> batch accepted
  -> status such as RECEIVED / PARSING
  -> later PARSED / REVIEW_REQUIRED
```

Do **not** invent an in-process FastAPI background task for money-sensitive ingestion.

Before implementing async execution, inspect/reuse an existing durable TruckERP scheduler/job/outbox mechanism if one exists. If none exists, explicitly design/build one later. An API process/container restart must not silently lose a Fuel parse job.

Async transport/execution implementation remains deferred until durable infrastructure is proven.

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

### 9.2 Credits, refunds, reversals and voids

Legitimate negative and reversing provider transactions are first-class source events.

Preserve provider sign and source identity. Distinguish provider terminology from TruckERP classification:

- `provider_event_type_raw` = exact provider value
- canonical `provider_event_type` supports at least `PURCHASE`, `CREDIT`, `REFUND`, `REVERSAL`, `VOID`, `OTHER`, `UNKNOWN`

Do not normalize a negative financial event into a positive purchase. Do not drop sign to make reconciliation look simpler. An unknown provider event value must never be coerced to `PURCHASE`; keep the raw value and use `UNKNOWN` (REVIEW-eligible later).

Credits/refunds/reversals/voids remain in source accounting and must be covered by reconciliation and settlement tests. They are provider financial events, not parser corrections.

---

## 10. Provider import/batch vs transaction records

Do not treat an entire invoice as one fuel expense.

A provider PDF/API import represents a **batch/source statement**, and that batch contains many individual transactions **and** separate provider control/summary rows.

### 10.1 One uploaded file = one `FuelSourceBatch` — architecture lock

For provider documents:

- One PDF / source statement = one `fuel_source_batches` row.
- Uploading 5 PDFs creates up to 5 independent source batches.
- Do **not** introduce a parallel `fuel_card_import_batches` concept.
- `fuel_source_batches` remains canonical.

Multi-file upload may be supported by one request, but each file is independently validated, deduplicated, identified, parsed, and tracked.

Conceptual separation (physical tenant tables use the `fuel_` prefix):

```text
fuel_source_batches
    one source PDF / API sync / structured-file batch

fuel_transactions
    one provider purchase/credit/refund/reversal/void/other/unknown event per row

fuel_source_controls
    normalized provider control / subtotal / currency / tax / invoice summary evidence
```

`fuel_source_controls` is the **sole normalized source of truth** for provider control totals and related summary evidence. Do not store a second authoritative control-totals blob on the batch (for example a batch-level `provider_control_totals_json` sidecar).

The same provider source row must not be represented as both a `fuel_transactions` purchase/event row and a `fuel_source_controls` control row. Ambiguous or unknown financial row meaning is `REVIEW`, not a guessed purchase.

The batch owns source-level facts such as:

- Provider
- Invoice/reference
- Statement period
- Original PDF/raw API payload reference
- Parse/review/process state
- Parser/adapter/rule version
- Source SHA256 (exact-file identity)

Each transaction owns row-level facts. Each control owns control-type/scope/currency/declared-amount facts used by reconciliation.

### 10.2 Exact-file duplicate is a HARD STOP — architecture lock

The earliest duplicate gate is:

```text
tenant_id + source SHA256
```

If the exact file hash already exists for that tenant:

- do **not** parse it again;
- do **not** create another financial source batch;
- do **not** allow a normal “process anyway” action;
- return / reference the existing batch.

Database uniqueness around source hash remains an important second line of defense against concurrency / frontend bugs.

A controlled future “reprocess existing source” operation may exist for recovery / parser investigation, but it reuses the existing immutable source; it does **not** pretend the same PDF is a new provider statement.

### 10.3 Same-provider business-document (invoice) identity gate — architecture lock

After provider / header identity is available, perform a second strong duplicate check **within the same provider**.

Primary lookup concept:

```text
tenant + provider_code + invoice_number
```

Examples:

- BVD + invoice `972201` compares only to earlier BVD invoice `972201`.
- NATIONWIDE + invoice `20250522B-06142026` compares only to earlier Nationwide invoice `20250522B-06142026`.

Invoice number is the first business-document identity gate. Supporting facts are then compared where supplied:

- provider account / account code;
- invoice date;
- statement start / end;
- due date where relevant;
- currency / currencies;
- provider-declared invoice / control totals **by currency**;
- useful source counts / control facts where available.

Do **not** compare CAD and USD as one combined fake total.

**Same provider + invoice + matching supporting facts** → HARD DUPLICATE even if raw PDF bytes / hash differ. Hard stop before a second financial effect. Show the user the existing source (see §11.5). Do not silently drop the attempted upload.

**Same provider + same invoice number but different source facts** → serious identity conflict:

```text
INVOICE_IDENTITY_CONFLICT -> REVIEW
```

Do **not** silently replace, merge, auto-call it a normal duplicate, or process it as a second invoice. UI should show old and newly presented source facts side by side. This may later represent provider correction, reissue, fraud/tampering, or a provider-specific dispute/adjustment mechanism — we do not guess. Provider-specific reissued-invoice / dispute mechanics remain a TODO requiring real evidence (see §35).

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

### 11.4 Bulk review / straight-through — architecture lock

Do not use AI confidence alone to authorize financial transactions.

Rows may become eligible for bulk acceptance / straight-through processing only when deterministic parser validation, provider controls, reconciliation, and required business gates pass.

Exception / `REVIEW` rows require human handling. Tenant straight-through policy can be considered later. Do not implement bulk-accept workflow in Segment 1.

### 11.5 Duplicate UX must preserve current user focus — architecture lock

When a duplicate is detected, do **not** navigate the user away from their current Fuel workspace.

Use a modal / drawer / overlay.

For an exact or business-document duplicate, show at least:

- provider;
- invoice number;
- original filename;
- original upload date/time;
- existing batch id;
- statement period;
- totals by currency;
- transaction count;
- units / trucks where useful;
- current lifecycle status.

Actions should include safe concepts such as:

- `View Existing Batch`
- `Compare`
- `Skip Duplicate` / `Cancel Upload`
- close and return to current work

Do **not** use a normal `Process Anyway` action.

Do **not** label this `Delete` when the attempted duplicate has not become a new financial batch.

### 11.6 Duplicate investigation must show how far the original source travelled

The duplicate warning must eventually be able to trace the existing source through the full financial chain:

```text
source file
  -> FuelSourceBatch
  -> Fuel transactions
  -> source review
  -> reconciliation
  -> financial responsibility
  -> settlement / payroll routing
  -> accounting / posting
```

Example: if Unit 1104 has a `$950.23` charge and that transaction already reached an O/O settlement, the duplicate inspection must be able to show that fact.

This is why downstream records must retain links back to canonical Fuel transaction / source batch identity.

Do not implement later modules now, but preserve this traceability requirement in their design.

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

### 14.1 Transaction timezone provenance

`transaction_datetime` is authoritative only with provenance.

Preserve:

- the provider timestamp exactly as supplied (including date-only when that is all the source has)
- `transaction_date` as the provider/source-local calendar date when that date is determinable from the provider source
- separately, timezone / UTC offset / timezone-source context when the provider supplies it (`transaction_timezone`, `transaction_utc_offset`, and/or `transaction_timezone_source`)
- a normalized timezone-aware `transaction_datetime` only when the provider supplied enough timezone/offset context to know it legitimately

Do not derive or overwrite `transaction_date` from UTC `transaction_datetime`. A provider-local late-night transaction must not move to another transaction date merely because UTC conversion crosses midnight.

If a provider supplies local time without timezone, store that fact. Do not silently reinterpret the timestamp using server time, tenant headquarters timezone, or the current user's timezone.

Historical truck, card/account, ownership/payee, pricing and settlement resolution must use the documented transaction-time interpretation, not a guessed zone.

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

### 15.3 Effective-dated card / account assignment

Card and account assignment is historical, like unit-number and ownership history.

A card or account identifier reported on a transaction is a snapshot, not a permanent binding to today's truck, driver, or payee.

Required resolution:

```text
provider card/account snapshot + transaction_datetime
        ↓
effective-dated card/account assignment history
        ↓
truck / driver / account / financial-responsibility relationships that applied then
```

If a card later moves to another truck, driver, or account, historical transactions keep the relationships that were effective at their transaction datetime. Do not rewrite historical ownership or responsibility from the current assignment.

Zero or multiple matches for that datetime is `REVIEW`. There is no current-assignment fallback.

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

`owner_operator_charge_amount` is produced only by this later pricing/settlement logic. It is not a provider source field and must not be hydrated by parsers or by Segment 1 schema helpers.

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

### 23.1 Downstream routing acknowledgement

Classification as Toll, Lumper, or another downstream module is not financial completeness.

`routed` alone is not enough. Fuel must retain deterministic evidence that the downstream module accepted and accounted for the transaction (acknowledgement / accepted reference / accounted-for state), or the item remains unresolved / `REVIEW`.

This prevents a transaction from disappearing between modules: Fuel has "sent it" and the other module never took it. Until acknowledgement exists, the source line is still Fuel's incomplete accountability item.

Future-state acknowledgement support (architecture lock; do not implement scheduler/workflow in Segment 1):

```text
ROUTING_PENDING
ROUTED_AWAITING_ACK
ACKNOWLEDGED
ROUTING_FAILED
```

Retain timestamps, error, and retry information, plus configurable aging/escalation. `routed` without acknowledgement is still incomplete.

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

Therefore row-level date/unit integrity is a required gate. `transaction_date` remains the provider/source-local date; UTC conversion of `transaction_datetime` must not reassign it.

### 24.4 Provider total and validated total

The final summary must clearly prove, per applicable currency:

```text
Provider Total = Validated Total
Difference = 0.00
```

while also proving every source row is accounted for exactly once.

### 24.5 Reporting currency — architecture lock

Fuel reconciles and preserves original provider currency independently.

Consolidated / base / reporting-currency conversion belongs downstream to Accounting/Reporting and must never overwrite Fuel source amount or currency.

Any future conversion record must retain:

- rate
- rate source
- as-of timestamp
- from-currency
- to-currency
- converted amount

Do not implement conversion workflow in Segment 1.

### 24.6 Flagged / disputed transactions still reconcile to provider source — architecture lock

If Nationwide / BVD billed `$47.50` and TruckERP correctly captured `$47.50`, **source reconciliation can still PASS** even if the charge is disputed or flagged.

Reconciliation answers:

> Did TruckERP accurately reproduce provider source truth?

A dispute answers:

> Should this charge ultimately remain financially ours / the driver's / O-O's?

Do **not** change provider reconciliation merely because a charge has been flagged.

Whether an open dispute places a downstream settlement / payroll hold is a separate policy decision and remains TODO / provider / company-policy dependent (see §35).

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

## 27. Duplicate behavior across intake sources — architecture lock

Duplicate detection has **three separate problems**. Do not collapse them.

### 27.1 Exact source-file duplicate

`tenant_id + source SHA256` — HARD STOP before parsing / second financial batch (see §10.2).

### 27.2 Same-provider business-document duplicate

`tenant + provider_code + invoice_number` (+ matching supporting facts) — HARD DUPLICATE within that provider only (see §10.3).

Conflicting facts under the same provider + invoice → `INVOICE_IDENTITY_CONFLICT` → REVIEW.

### 27.3 NO cross-provider PDF / transaction dedupe — architecture lock

Do **not** compare:

- BVD transaction vs Nationwide transaction;
- BVD invoice vs Nationwide invoice;
- one provider's rows against another provider's rows;

for duplicate suppression.

There is **no** generic:

```text
unit + product + quantity + amount + datetime -> duplicate
```

across two provider profiles.

Do **not** add provider-pair dedupe rules.

BVD duplicate-document checks compare against earlier **BVD** documents. Nationwide duplicate-document checks compare against earlier **Nationwide** documents.

**Locked wording:**

> Provider-document duplicate detection is provider-scoped. BVD documents are compared to prior BVD document identity; Nationwide documents are compared to prior Nationwide identity. TruckERP does not perform fuzzy BVD-vs-Nationwide transaction suppression.

### 27.4 Manual-driver-entry-to-provider matching (Segment 11)

The same purchase may appear through more than one intake path:

```text
MANUAL_DRIVER
then PDF
then API
```

Manual-driver-entry-to-provider matching in Segment 11 is a **separate** problem and may still prevent a manual charge and its later authoritative provider transaction from being financially posted twice. That does **not** authorize fuzzy BVD-vs-Nationwide suppression.

Within a single provider, strong match signals may include:

- Provider transaction / auth ID
- Provider + account + card + transaction datetime
- Other provider-specific identifiers

Do not automatically merge ambiguous transactions without an auditable rule / review.

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

`owner_operator_charge_amount` is this later derived settlement charge. Provider parsing and Segment 1 must leave it null.

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

### 29.1 Atomic and idempotent finalization

Finalization must be both **idempotent** and **atomic**.

Retrying Finalize on an already-finalized batch must not create a second financial posting.

A batch failure midway through posting must not leave an uncontrolled partially-posted financial state. Use one database transaction where practical, or a deterministic recoverable posting state with explicit completion/failure tracking (every intended post either committed, explicitly failed, or safely retryable). Uncontrolled partial posting is not an acceptable outcome.

### 29.2 Finalization separation of duties — architecture lock

Finalization approval policy is tenant-configurable:

```text
SINGLE_ADMIN
  Same reviewer/finalizer is allowed, but the same-person action is explicitly audited.

SEPARATE_APPROVER
  Backend requires finalizer != reviewer.
```

This is an architecture lock only. Do not build finalization workflow in Segment 1.

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
- Flag / dispute case timeline and evidence
- Linked provider credit / reversal / adjustment events

### 30.1 Parsed vs reviewed value

Where a human corrects extraction, retain both concepts:

```text
parsed_value
reviewed_value
review_reason
reviewed_by
reviewed_at
```

### 30.2 Provider source truth becomes immutable after source review — architecture lock

Parser / AI output itself may be wrong.

During source review a reviewer may correct extraction **only** to make TruckERP match what the actual provider PDF says.

Always retain `parsed_value`, `reviewed_value`, correction reason, reviewer, and timestamp.

Example:

```text
PDF says $950.23
AI parsed $950.28
Reviewer corrects reviewed source fact to $950.23
```

After source review confirms that the PDF says `$950.23`, the **provider source fact is locked**.

A later dispute must **never** change that source transaction to `$0`, `$850.23`, etc.

Provider PDF and confirmed TruckERP source truth must remain reconcilable forever.

### 30.3 After posting

Do not silently rewrite posted financial history.

Corrections require an auditable adjustment/reversal workflow.

### 30.4 Extraction correction vs provider amendment

Keep these event types separate:

```text
PRE-FINALIZATION HUMAN CORRECTION
  Human review of extracted/parser values on an unfinalized source.
  Retain parsed_value, reviewed_value, reason, reviewer, timestamp.
  This does not change what the provider issued.

PROVIDER-ISSUED FINANCIAL EVENT
  Amendment, credit, refund, reversal, void, or corrected transaction
  issued by the provider.
  This remains a source financial event with its own source identity.
```

Do not represent a provider change as a parser correction. Do not represent a human extraction correction as a provider credit/reversal.

### 30.5 Flag / dispute / adjustment are three different concepts — architecture lock

Keep them separate.

**FLAG** — someone says this transaction requires attention.

**DISPUTE / CASE** — an investigation or challenge is actively being worked.

**ADJUSTMENT** — an actual financial correcting event exists.

A flag does **not** mutate the provider source transaction. A flag opens an auditable case linked to the exact Fuel transaction.

Examples of flags: unit scale charge questioned; suspected unauthorized purchase; possible duplicate charge within provider statement/account; wrong fee; driver disputes purchase; missing receipt; amount requires provider investigation.

A charge may be flagged and later found valid:

```text
Original source charge: +$47.50
Case resolution: RESOLVED_VALID
Adjustment: none
```

Or provider agrees:

```text
Original source charge: +$47.50
Provider credit:        -$47.50
Net provider effect:     $0.00
```

Never edit the original `+$47.50`.

Partial credits must remain mathematically explicit:

```text
Original:   +$47.50
Adjustment: -$20.00
Net:         $27.50
```

### 30.6 Flag / dispute case requires full trail

The case must eventually support an append-only / auditable timeline containing concepts such as:

- case / flag id;
- original transaction id;
- source batch / invoice;
- unit / truck;
- amount / currency under dispute;
- issue category / reason;
- opened by;
- opened timestamp;
- status changes;
- notes;
- provider contact / reference number;
- driver / O-O communications;
- resolution;
- closed by / time.

Do **not** design this as one mutable note box.

Suggested operational statuses (exact vocabulary remains implementation-time reviewable):

```text
OPEN
UNDER_REVIEW
WAITING_FOR_DRIVER
WAITING_FOR_PROVIDER
DISPUTED
CREDIT_PENDING
PARTIALLY_ADJUSTED
RESOLVED_CREDITED
RESOLVED_VALID
RESOLVED_DENIED
```

The important lock is append-only / auditable transition history. Flag / dispute statuses are operational — they are **not** source mutation (see §24.6).

### 30.7 Evidence attachments are part of the dispute trail

A flag / dispute case must support evidence attachments such as:

- driver receipt;
- scale ticket;
- provider email;
- screenshot;
- dispute form;
- credit memo;
- supporting PDF;
- driver statement;
- other evidence.

Attachments belong to the case and link back to the original Fuel transaction / source.

Do **not** overwrite the original provider PDF.

### 30.8 Provider credit / reversal / adjustment is a NEW linked financial event

If a provider later grants a credit or reversal:

- record the credit / reversal / adjustment separately;
- link it to the original Fuel transaction;
- link it to the dispute / flag case where applicable;
- preserve provider reference / credit memo;
- preserve amount / currency / date / source;
- **never** rewrite the original transaction.

This is required for year-end explainability.

### 30.9 Year-end / provider-account invariant — architecture lock

TruckERP must be able to explain:

```text
original provider invoices
+ provider credits
+ provider reversals
+ provider adjustments
= net provider account activity
```

The original PDFs must continue to match their original confirmed database source amounts.

Separately:

```text
O/O / driver settlement deductions
+ later reimbursements / settlement adjustments
= net settlement effect
```

Do **not** mix source / provider accounting with contractual settlement calculations.

**Locked wording:**

> TruckERP never makes a provider invoice disappear because it is disputed. A confirmed provider source transaction remains immutable. Operational flags and disputes create linked cases with evidence and timeline history. Provider credits, reversals, and adjustments are new linked financial events. This preserves an exact chain from original provider PDF through dispute resolution and downstream settlement/accounting so year-end totals remain reproducible.

---

## 31. Conceptual status lifecycle

A batch may move through states such as:

```text
RECEIVED / UPLOADED
PARSING
PARSED
REVIEW_REQUIRED
REVIEWED
READY_FOR_RECONCILIATION
PROCESSING
RECONCILIATION_FAILED
RECONCILED
READY_TO_FINALIZE
FINALIZED
BLOCKED
```

Exact implementation names remain to be decided, but the architectural distinction between parsing, human review, reconciliation, and financial posting is required. Async `RECEIVED` / `PARSING` states are part of the durable ingestion contract (§8.7), not an excuse for in-process background tasks.

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
- Decimal arithmetic (no float) and locked NUMERIC scales
- Provider id vs source-row id vs TruckERP transaction id remaining distinct
- Effective-dated card/account assignment at transaction datetime
- Extraction correction retained separately from provider amendment/credit/reversal
- Downstream routing acknowledgement (or unresolved/review) for Toll/Lumper/etc.
- Idempotent and atomic finalization (no uncontrolled partial posting)
- Credits/refunds/reversals/voids keep provider sign
- Timezone provenance; no silent server/tenant zone rewrite
- Exact-file SHA256 hard stop (including concurrent upload race)
- Same-provider invoice identity gate (match → hard duplicate; conflict → REVIEW)
- No cross-provider BVD-vs-Nationwide duplicate suppression
- Disabled historical provider still identifiable from manual upload
- Unknown / ambiguous provider identification → REVIEW
- Flag does not mutate confirmed source amount; reconciliation can still PASS
- Provider full / partial credit as new linked adjustment; year-end source + adjustments reproducible
- Duplicate modal / compare preserves current workspace focus

---

## 35. Current unresolved implementation details

The following remain intentionally unresolved until we have code/provider evidence or an explicit business decision:

- Provider-specific accepted rounding tolerance (beyond the locked decimal column scales and rounding boundaries in §1.5)
- Exact BVD API contract
- Exact Nationwide API/CSV contract
- Which additional providers are implemented after BVD/Nationwide
- Final settlement/payroll FK/table structure
- Exact financial-responsibility policy for scale/parking/repair in edge cases
- Exact manual-driver receipt requirements
- Final UI wording for `Save & Next`, `Process`, `Finalize`
- Final permission names for Fuel Admin / compensation setup
- Real BVD dispute / credit process (provider-evidenced)
- Real Nationwide dispute / credit process where not yet fully documented
- Provider dispute deadlines / SLA / escalation
- Whether an open dispute holds downstream O/O / driver settlement (company / provider policy)
- Durable async worker / job / outbox mechanism for Fuel parse ingestion (§8.7)
- Final dispute-case / adjustment schema and attachment model
- Provider-specific reissued-invoice / dispute mechanics after `INVOICE_IDENTITY_CONFLICT`

Locked and no longer open: database precision/scale for quantity, unit price, discount rate/amount, tax amounts, transaction totals, and owner-operator charges (§1.5); three-way transaction identity (§1.6); provider event type raw vs canonical including `OTHER`/`UNKNOWN` with no unknown-to-`PURCHASE` coercion (§1.7, §9.2); currency raw vs canonical (§1.8); owner-operator charge as derived pricing/settlement only — never provider/parser/AI hydrated (§1.9, §18.1, §28.1); transaction timezone provenance and source-local `transaction_date` (§14.1); extraction correction vs provider amendment (§30.4); downstream routing acknowledgement and future ack states (§23.1); atomic + idempotent finalization (§29.1); tenant-configurable finalization separation of duties (§29.2); credits/refunds/reversals/voids (§9.2); provider layout fingerprinting / unrecognized layout → `REVIEW` (§8.4); strict provider identification 0/1/many (§8.5); file safety before parsing (§8.6); one file = one `fuel_source_batches` (§10.1); exact-file and same-provider invoice duplicate gates (§10.2–§10.3); no cross-provider fuzzy dedupe (§27.3); confirmed source immutable after review (§30.2); flag ≠ dispute ≠ adjustment (§30.5); flagged source may still reconcile (§24.6); bulk review not authorized by AI confidence alone (§11.4); reporting currency never overwrites Fuel source amount/currency (§24.5); provider controls live on normalized `fuel_source_controls` as sole control SoT with transaction/control source-row exclusivity (§10); effective-dated card/account assignment physical table `fuel_card_account_assignments` (§15.3 / Segment 3); provider identification independent of tenant enabled/disabled (§4.3).

Do not invent remaining details before evidence or product decisions exist.

---

## 36. Architecture lock summary

The Fuel/Card module is not just a fuel parser.

It is a provider-ingestion + financial-control subsystem with these locked principles:

1. Three intake paths: API, digital PDF, manual driver entry.
2. Many providers, one canonical transaction model — via **one generic Fuel parser** plus **one master provider-profiles JSON** with one current evidenced section per provider (not one parser engine per provider). BVD and Nationwide are the first two sections.
3. Provider facts are immutable source evidence.
4. BVD is the first production provider section; Nationwide is the second real layout proof.
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
21. Money/quantity uses decimal/`NUMERIC` only; locked precision/scale applies before Segment 1 schema; no binary float in financial math.
22. Provider transaction identity, provider source-row identity, and TruckERP canonical transaction identity remain separate.
23. Card/account assignment is effective-dated and resolves at transaction datetime, like truck/ownership history.
24. Human extraction correction is not a provider amendment; provider credits/refunds/reversals/voids are source financial events.
25. Downstream classification (Toll, Lumper, etc.) requires acknowledgement that the other module accounted for the item, or the item stays review-required.
26. Finalization is idempotent and atomic; uncontrolled partial posting is not allowed.
27. Negative and reversing provider transactions keep provider sign and are never rewritten as positive purchases.
28. `transaction_datetime` is authoritative only with timezone/provenance; local time without zone is not silently reinterpreted.
29. `provider_event_type_raw` preserves provider terminology; canonical `provider_event_type` is TruckERP classification (`PURCHASE`/`CREDIT`/`REFUND`/`REVERSAL`/`VOID`/`OTHER`/`UNKNOWN`); unknown values are never coerced to `PURCHASE`.
30. `currency_raw` preserves the provider representation; `currency` is the canonical ISO-style value; normalization must not destroy the raw value.
31. `transaction_date` is the provider/source-local calendar date when determinable; it is never derived from UTC `transaction_datetime`.
32. `owner_operator_charge_amount` is derived O/O pricing/settlement data, not provider source; parsers, Segment 1, and Fuel AI must not populate it.
33. Finalization approval policy is tenant-configurable (`SINGLE_ADMIN` audited same-person vs `SEPARATE_APPROVER` requiring finalizer != reviewer).
34. Provider parser profiles are versioned/fingerprinted; unrecognized layout is `PROVIDER_LAYOUT_UNRECOGNIZED` → `REVIEW`; AI must not silently compensate.
35. AI confidence alone cannot authorize financial transactions; bulk/straight-through requires deterministic validation, provider controls, reconciliation, and required gates.
36. Downstream routing future states include `ROUTING_PENDING`, `ROUTED_AWAITING_ACK`, `ACKNOWLEDGED`, `ROUTING_FAILED` with timestamps/error/retry and configurable aging/escalation.
37. Fuel reconciles original provider currency independently; reporting-currency conversion is Accounting/Reporting downstream and must never overwrite Fuel source amount/currency; conversion records retain rate, rate source, as-of timestamp, from/to currency, and converted amount.
38. Provider control/summary evidence is normalized on `fuel_source_controls` as the sole control source of truth; batches do not keep a second authoritative control-totals sidecar.
39. The same provider source row cannot be both a transaction and a control; unknown/ambiguous financial meaning is `REVIEW`, not a guessed purchase.
40. One uploaded file = one `fuel_source_batches` row; no parallel `fuel_card_import_batches` concept.
41. File safety (count/stream/signature/size/SHA256 + shared document-safety) happens before AI/full parsing; PDF magic alone is not malware protection.
42. Exact-file duplicate (`tenant + SHA256`) is a HARD STOP before parse / second financial batch; no normal “Process Anyway”.
43. Provider identification uses all evidenced master profiles (today BVD + NATIONWIDE), independent of tenant enabled/disabled; soft-disabled connections are history-preserving.
44. Strict identification: 0 → `DOCUMENT_PROVIDER_UNKNOWN`, 1 → continue, 2+ → `DOCUMENT_PROVIDER_AMBIGUOUS`; never fuzzy closest-wins.
45. Provider-document duplicate detection is provider-scoped; no fuzzy BVD-vs-Nationwide transaction suppression.
46. Same provider + invoice + matching facts → hard business-document duplicate; same invoice with conflicting facts → `INVOICE_IDENTITY_CONFLICT` → REVIEW.
47. Duplicate UX uses modal/drawer preserving current focus; View Existing / Compare / Skip; no Process Anyway.
48. Confirmed provider source facts are immutable after source review; disputes never rewrite the original amount.
49. Flag, dispute/case, and adjustment are three different concepts; credits/reversals/adjustments are new linked financial events.
50. Source reconciliation can still PASS when a correctly captured transaction is flagged/disputed.
51. Year-end: original invoices ± credits/reversals/adjustments = net provider activity; settlement adjustments do not overwrite provider source amounts.
52. Async ingestion requires a durable scheduler/job/outbox — not an in-process FastAPI background task for money-sensitive work.
