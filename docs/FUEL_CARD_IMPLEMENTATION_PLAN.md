# TruckERP Fuel / Fuel-Card Implementation Plan

**Status:** Execution plan for Cursor. Companion to `docs/FUEL_CARD_MODULE_DESIGN.md`; does not replace the architecture/design document.

**Source of truth:** `docs/FUEL_CARD_MODULE_DESIGN.md`

**Current execution scope:** tenant provider configuration + provider/file intake + BVD/Nationwide document rules + canonical transaction normalization + review + reconciliation + historical truck/ownership resolution + O/O pricing + settlement/audit + UI.

**Explicitly deferred unless reopened:** unverified provider APIs, OAuth/data-sharing flows whose exact provider contract is not yet known, automatic provider-specific rounding tolerances without evidence, and any direct provider machine feed that has not been confirmed by real credentials/specifications.

---

# 0. Operating contract

Fuel/Card is a money-moving subsystem. Do not treat it as normal CRUD.

## 0.1 One segment at a time

Cursor completes one segment only, runs its required tests, records exact results in this file, and stops for review.

Do not begin the next segment until the current segment has:

1. code complete,
2. required tests complete,
3. results recorded,
4. risks/TODO recorded,
5. user/ChatGPT review allowed to happen.

## 0.2 No second parser stack

Reuse existing TruckERP tenancy, people/payee, truck, audit, storage, permissions, settlement and shared Document Platform patterns.

Fuel/Card attaches a Fuel profile to the existing shared document architecture. Do not build a second independent end-to-end PDF/OCR/OpenAI framework.

## 0.3 Provider connectivity rule

Do not assume every fuel-card provider uses REST/API.

TruckERP must support connection/source methods such as:

```text
PDF_UPLOAD
STRUCTURED_FILE_UPLOAD
FILE_EXPORT
SFTP
DATA_SHARING / PARTNER_AUTH      future when provider contract is proven
REST_API                         future when provider contract is proven
MANUAL_DRIVER
```

The backend provider catalog decides which methods exist for each vendor. React must not invent provider fields or connection types.

## 0.4 Provider facts are evidence; parser output cannot move money

Never mutate source facts to force reconciliation.

Parser/AI output must never decide:

- `truck_id`,
- `driver_id`,
- owner/payee,
- O/O pricing,
- financial responsibility,
- settlement eligibility,
- posting.

Those are backend resolution/gate decisions after source extraction/review.

## 0.5 Money rules

No transaction may post while a required gate is `FAIL` or `REVIEW`.

Grand-total equality alone is insufficient. Row identity, transaction date, unit/card relationship, currency controls, truck/ownership history, financial destination and pricing must also be valid.

## 0.6 Transaction date/time is authoritative

Historical truck, unit-number history, ownership/payee, O/O pricing and settlement eligibility use the **transaction date/time**, not invoice date, import time or today's relationships.

## 0.7 Branch discipline

Do not create a new branch merely because a segment starts. Use the current agreed working branch unless explicitly asked otherwise.

## 0.8 Execution record template

At the end of every segment update its record with:

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

Do not mark `PASS` when required tests were skipped.

---

# 1. Locked source -> canonical -> presentation architecture

This is a core Fuel/Card rule.

TruckERP keeps three separate layers:

```text
1. PROVIDER / SOURCE TRUTH
   Exact provider values + original source file/payload

2. CANONICAL TRUCKERP DATA
   Stable internal meanings used for queries, matching, reconciliation and settlement

3. FRONTEND PRESENTATION
   TruckERP-controlled labels, grouping, ordering and display formatting
```

## 1.1 Source truth is lossless

For every provider transaction preserve:

- original PDF/DAT/CSV/file/API payload reference,
- source hash,
- exact source row values,
- source row order/identity,
- provider-specific fields in `provider_raw` or equivalent,
- provider raw currency/unit/product codes when normalization is applied.

When we say “map every field byte-for-byte,” implementation meaning is:

> Do not discard or silently rewrite any provider-supplied field/value required to reproduce and audit what the provider sent.

The original source file itself remains the ultimate evidence.

## 1.2 Canonical data is stable and provider-independent

Provider-specific columns map into a small canonical transaction model. A BVD row, Nationwide row, structured Pilot/Love's feed row or future API row ultimately hydrates the same core record.

## 1.3 Frontend wording is ours

The UI may rename/reorder/group fields for clarity without changing source truth.

Example:

```text
BVD source:        Final AMT
Canonical field:  total_amount
TruckERP UI:       Total Charged
```

Another example:

```text
Nationwide source: Ex-GST ($/U)
Canonical field:   unit_price + unit_price_basis=EX_TAX
TruckERP UI:        Price Before Tax
```

Changing a frontend label must never require rewriting source data or reparsing historical transactions.

---

# 2. Provider, processing network and merchant are different concepts

Do not collapse these into one `vendor` field.

A real transaction can have three separate identities:

```text
PROGRAM / ACCOUNT PROVIDER
    who owns the fleet program/account relationship

PROCESSING / PAYMENT NETWORK
    underlying authorization/payment rail when known

MERCHANT / ACCEPTANCE NETWORK
    where the truck actually bought fuel/product
```

Example based on the observed BVD/Love's workflow:

```text
program_provider     = BVD
processing_network   = T_CHEK       when source/configuration proves it
merchant_network     = LOVES
merchant_site        = actual station/site when available
```

The provider/account that supplies TruckERP's statement/feed remains the **source vendor**. A purchase at Love's does not automatically mean `source_vendor=LOVES` when the carrier used a BVD account/card.

Do not infer a processing network unless provider/card configuration or source evidence establishes it. BVD may support more than one underlying card/network arrangement.

---

# 3. Locked provider intake strategy

Prefer the most structured source the provider actually supports.

```text
Structured API / SFTP / DAT / CSV available
        -> deterministic provider adapter
        -> canonical Fuel/Card staging

Only PDF/report available
        -> Fuel document profile + provider JSON rules
        -> canonical Fuel/Card staging
```

Do not send a structured DAT/CSV feed to AI just because the Fuel module also has a PDF parser.

## 3.1 Current provider matrix

| Provider | Current TruckERP intake direction | Notes |
|---|---|---|
| BVD | PDF + structured BVD/T-Chek export file where available | First production provider. Direct automated API/SFTP still unconfirmed. |
| Nationwide | PDF; CSV companion may be added when real contract/file is captured | Second real provider/layout proof. |
| Pilot Flying J | structured partner/SFTP-style connection when actual tenant credentials/spec are available | Do not invent a public fuel-transaction REST API. |
| Love's | structured partner/SFTP-style connection when actual tenant credentials/spec are available | Public Love's APIs are not assumed to equal fleet transaction feed. |
| WEX/EFS/T-Chek | structured partner/data-sharing/API/feed when exact account contract is confirmed | Provider catalog remains ready for this. |
| Comdata | structured partner/web-service/feed when exact account contract is confirmed | Do not guess required fields before onboarding documentation. |

## 3.2 BVD structured export path

BVD is not PDF-only.

Industry documentation confirms BVD can produce a T-Chek-compatible transaction export such as `TcheckDATTransplus` for TMS import.

TruckERP must therefore support the architecture:

```text
BVD portal / BVD export
        -> structured DAT/file upload
        -> deterministic BVD file adapter
        -> preserve original file + hash + raw row
        -> canonical Fuel/Card staging
        -> reconciliation / ownership / settlement gates
```

This path **bypasses AI document extraction** because the file is already structured.

Do not claim BVD direct SFTP/API until BVD provides the actual machine-feed contract.

## 3.3 Nationwide path

Nationwide remains PDF-first with provider-specific row/control rules. A CSV companion path may be added once a real sample/spec is captured.

## 3.4 JSON rules remain versioned and adjustable

BVD/Nationwide JSON rules are not frozen forever after first draft.

Testing loop:

```text
real provider source
    -> parse
    -> compare parsed JSON to source
    -> mechanical/reconciliation tests
    -> identify error
    -> update provider field/rule JSON
    -> increment/version rule contract
    -> rerun same fixture
    -> lock regression test
```

Rules may be refined as real provider documents expose new layouts.

Unfinalized/review batches may be reparsed under an explicitly selected newer rule version. Finalized financial history is never silently rewritten by a new parser version; corrections require the established audited correction/reversal workflow.

Store the parser/rule version used for every parsed batch.

---

# 4. Shared document parser architecture

Fuel mirrors the Load parser contract pattern:

```text
Calling Fuel module chooses explicit Fuel profile/provider context
        ↓
Shared Document Platform
        ↓
Fuel profile
  + global rules
  + provider rules
  + field rules
  + strict JSON output schema
        ↓
OpenAI/shared model transport when required
        ↓
Mechanical validator
        ↓
Canonical parsed statement JSON
        ↓
Admin review
        ↓
Backend reconciliation / ownership / pricing gates
```

The Document Platform does not autonomously assign financial meaning by guessing a provider.

For a usable digital PDF, follow the current shared policy: send the original PDF with the Fuel JSON rules/schema on the model path. Scanned/image-only sources use shared OCR fallback.

AI performs semantic extraction. Mechanical backend code validates money.

---

# 5. Tenant provider configuration and backend wiring

Fuel provider configuration is tenant-scoped and backend-driven.

## 5.1 Backend provider catalog

The backend owns the supported provider catalog. Initial conceptual entries:

```text
BVD
NATIONWIDE
PILOT_FLYING_J
LOVES
WEX
EFS_TCHEK
COMDATA
```

Each catalog entry defines:

- stable provider code,
- display name,
- supported/enabled state,
- supported connection methods,
- preferred/default connection method,
- parser/adapter/profile code,
- expected file formats,
- optional filename pattern,
- connection field-definition schema,
- credential requirements,
- test-connection capability,
- sync capability,
- scheduling capability,
- provider instructions/help text,
- provider-specific validation rules.

Tenant configuration selects from this catalog. The tenant does not redefine what BVD, Pilot or Love's means.

## 5.2 Vendor dropdown -> provider-defined fields

```text
Fuel Provider
   [Select vendor ▼]
        BVD
        Nationwide
        Pilot Flying J
        Love's
        WEX
        EFS/T-Chek
        Comdata

Select vendor
        ↓
Backend returns supported connection methods + field schema
        ↓
Frontend renders only those fields
        ↓
Authorized user enters tenant-specific values
        ↓
Save
        ↓
Test Connection (when supported)
        ↓
Enable
```

No giant universal form and no frontend-hardcoded provider credential schema.

## 5.3 Example dynamic SFTP schema

Conceptual only; exact provider fields must come from actual provider contracts:

```json
{
  "provider_code": "PILOT_FLYING_J",
  "connection_method": "SFTP",
  "fields": [
    {
      "key": "account_reference",
      "label": "Account / Customer Reference",
      "type": "text",
      "required": false,
      "secret": false
    },
    {
      "key": "sftp_username",
      "label": "SFTP Username",
      "type": "text",
      "required": true,
      "secret": false
    },
    {
      "key": "sftp_password",
      "label": "SFTP Password",
      "type": "secret",
      "required": true,
      "secret": true
    }
  ]
}
```

Provider endpoints/hosts should preferably be backend-known/allowlisted. Do not create an arbitrary-host SSRF/network escape surface.

## 5.4 Same backend from two UI entry points

Provider configuration may be opened from:

```text
Admin -> Integrations -> Fuel
```

or, when RBAC allows:

```text
Fuel -> Providers / Connections -> Add Provider
```

Both are views over the same tenant provider-connection records and endpoints. Do not create duplicate Admin vs Fuel configuration stores.

## 5.5 RBAC is backend enforced

Conceptual capabilities; final names follow repo convention:

```text
fuel.providers.view
fuel.providers.manage
fuel.providers.test_connection
fuel.providers.sync
fuel.imports.review
fuel.imports.process
fuel.imports.finalize
```

Hiding a button is not authorization. Backend must reject unauthorized direct endpoint calls.

## 5.6 Secret handling

Provider secrets are accepted on write but never returned after save.

```text
secret entered
   -> server-side protected storage/reference
   -> later GET:
      configured=true
      masked_display=********
      actual_secret NEVER RETURNED
```

Secrets must be redacted from logs, audit payloads, exceptions and parser/OpenAI handoffs.

## 5.7 Multiple providers and multiple accounts

One tenant may use many providers and multiple accounts under one provider. Do not make provider code alone unique per tenant.

## 5.8 Conceptual backend endpoints

Final paths follow repo conventions, but the backend should provide behavior equivalent to:

```text
GET  /api/v1/fuel/providers
GET  /api/v1/fuel/providers/{provider_code}

GET  /api/v1/fuel/provider-connections
POST /api/v1/fuel/provider-connections
GET  /api/v1/fuel/provider-connections/{id}
PUT  /api/v1/fuel/provider-connections/{id}

POST /api/v1/fuel/provider-connections/{id}/test
POST /api/v1/fuel/provider-connections/{id}/sync
```

A provider whose live adapter is not implemented may return a safe `connection_method_not_implemented` result rather than pretending connectivity works.

## 5.9 Adapter boundary

Define the provider adapter contract before implementing every vendor:

```text
validate_configuration()
test_connection()
fetch_or_receive_source()
parse_structured_source()      when structured
```

BVD/Nationwide PDF extraction remains under the shared Fuel document profile, not under a fake API adapter.

---

# 6. Canonical Fuel/Card data model

## 6.1 Import/source batch

One uploaded/downloaded statement/file/feed batch = one source batch.

Preserve at minimum:

- tenant scope,
- provider code,
- provider connection/account reference,
- source type (`PDF`, `STRUCTURED_FILE`, `SFTP_FILE`, `MANUAL_DRIVER`, future `API`),
- invoice/statement number,
- invoice date,
- statement start/end,
- due date,
- original source storage reference,
- cryptographic hash,
- remote filename/timestamp when applicable,
- imported timestamp,
- parser/adapter/rule version,
- review/process/finalize state,
- reviewer/finalizer/time,
- provider control totals by currency.

## 6.2 Canonical transaction core

| Canonical field | Meaning |
|---|---|
| `transaction_datetime` | Actual provider transaction date/time; date-only allowed when provider supplies no time. |
| `unit_number_snapshot` | Unit exactly as provider reported it. |
| `card_or_account_id` | Provider card/account identifier used for mapping/audit. |
| `driver_name_snapshot` | Provider-reported driver only; nullable; never backfilled. |
| `merchant_site` | Provider site/merchant/network label. |
| `city` | Provider-reported city. |
| `province_state` | Provider-reported province/state. |
| `product` | Controlled canonical product/category label. Raw provider code remains preserved. |
| `quantity` | Provider volume/quantity. |
| `quantity_unit` | `L`, `GAL`, `ITEM`, etc.; source-supported/derived by locked rule. |
| `unit_price` | Canonical provider unit-cost input. |
| `unit_price_basis` | `BILLED`, `EX_TAX`, `FINAL_GALLON_PRICE`, `RETAIL_FALLBACK`, etc. |
| `tax_amount` | Per-row tax only when the provider actually supports it. |
| `discount_amount` | Canonical supported provider discount amount; nullable. |
| `total_amount` | Provider transaction total/final amount; reconciliation anchor. |
| `currency` | Transaction currency. |
| `source_vendor` | BVD, NATIONWIDE, PILOT_FLYING_J, LOVES, WEX, etc. |
| `processing_network` | Optional known payment/processing rail; nullable when unproven. |
| `merchant_network` | Optional merchant/acceptance network when known. |

Provider-specific missing fields remain null; do not invent values to satisfy a universal shape.

## 6.3 Raw provider sidecar — mandatory

Every source transaction preserves provider-specific evidence in `provider_raw` or equivalent JSON.

Examples:

**BVD raw evidence**

- Auth Code,
- Site #,
- original product code,
- Retail,
- Billed,
- Pre Tax AMT,
- HST,
- GST,
- PST,
- QST,
- Disc Rate,
- Disc AMT,
- original CUR,
- any additional BVD export columns.

**Nationwide raw evidence**

- Account Code,
- Card Number,
- Network,
- raw Product,
- Ex-GST ($/U),
- USA Discount,
- Missed Disc,
- OON Fees,
- source Currency,
- provider-specific subtotal/control information.

Future providers keep their full source row in raw evidence even if only 12-16 fields are promoted to canonical columns.

## 6.4 TruckERP resolution fields are separate

Never mix provider facts with:

- `truck_id`,
- `driver_id`,
- `owner_operator_payee_id`,
- classification,
- financial responsibility,
- pricing agreement/rule reference,
- settlement/payroll reference,
- gate/readiness statuses.

Nationwide can legitimately have `driver_name_snapshot=null`; backend may resolve a separate `driver_id` from historical card/unit assignment without rewriting source truth.

---

# 7. Dynamic quantity/unit and currency behavior — LOCKED

Every fuel/product transaction line is dynamic on its own. Never use one statement-wide unit assumption.

Each row carries at least:

```text
transaction_datetime
currency
quantity
quantity_unit
unit_price
unit_price_basis
```

## 7.1 Source unit wins

If the provider explicitly supplies a unit of measure, preserve/use that source unit.

Example:

```text
provider says USD + Litres
-> keep Litres
-> do NOT rewrite to gallons merely because currency is USD
-> flag only if the provider/profile says the combination is invalid
```

## 7.2 Currency fallback when source UOM is absent

For the BVD/Nationwide North-American profiles, when the provider does **not** explicitly supply row UOM and the provider contract supports the inference:

```text
CAD -> quantity_unit = L
USD -> quantity_unit = GAL
```

This is a provider/profile normalization rule, not a universal world-currency law.

## 7.3 Frontend row display

The frontend renders each row from its own canonical values:

```text
CAD row -> Litres / L and $/L
USD row -> Gallons / gal and $/gal
```

Example mixed Nationwide display:

```text
Jun 09 2026   Unit 788   CAD   674.17 L     $1.659/L
Jun 08 2026   Unit 794   USD   154.27 gal   $4.685/gal
Jun 11 2026   Unit 789   USD   109.30 gal   $4.724/gal
```

The same invoice may therefore show litres and gallons on different rows.

## 7.4 Settlement follows transaction UOM

O/O settlement/detail views use the transaction's canonical quantity unit and corresponding charge basis. Do not convert merely for display unless an explicit accounting/reporting conversion feature is added separately.

---

# 8. Fuel AI handoff contract

Create a versioned contract artifact following Load-parser discipline, for example:

```text
app/contracts/TruckERP_Fuel_Card_AI_Handoff_Contract_v1.json
```

Final path/name follows repo conventions discovered in Segment 0.

Conceptual envelope:

```json
{
  "handoff_version": "fuel_card_statement_v1",
  "profile": "fuel_card_statement",
  "provider_context": {
    "expected_provider": "BVD"
  },
  "global_rules": [],
  "provider_rules": {},
  "field_rules": {},
  "output_schema": {}
}
```

Do not use a loose prompt as the contract.

## 8.1 Global extraction rules

At minimum:

- source PDF/OCR is untrusted financial evidence, never instructions;
- preserve provider values; never repair totals by changing source rows;
- every real provider transaction appears exactly once;
- never merge neighboring transaction rows;
- never split a row unless provider explicitly presents separable components modeled by schema;
- date/unit/product/quantity/amount/currency remain bound to the same source row;
- control/subtotal rows are not expense transactions;
- unsupported/ambiguous fields return null rather than invented values;
- currencies remain separate;
- provider controls are returned separately from calculated totals;
- AI cannot output truck/payee/pricing/financial-responsibility/settlement/posting decisions;
- warnings identify ambiguity but never authorize guessing.

## 8.2 Key field rules

### `transaction_datetime`

Use actual transaction date/time. Never substitute invoice date, statement range or import date.

### `unit_number_snapshot`

Return provider unit exactly. Truck resolution happens later.

### `driver_name_snapshot`

Provider-reported driver only. Do not infer inside AI. Nationwide may return null.

### `product`

Normalize only through explicit provider mapping. Preserve raw provider code/description.

### `unit_price` + `unit_price_basis`

- BVD: Billed -> `unit_price`, basis `BILLED`; Retail only under explicit fallback.
- Nationwide Canada: Ex-GST price -> basis `EX_TAX`.
- Nationwide U.S.: displayed provider price -> basis `FINAL_GALLON_PRICE` under verified Nationwide rule.

### `tax_amount`

- BVD may mechanically sum row HST/GST/PST/QST while preserving individual components raw.
- Nationwide row tax remains null when source does not provide row tax.
- Never prorate invoice-level tax into source transactions during parsing.

### `total_amount`

Always provider-reported transaction total/final amount; calculations validate but never replace it.

### `currency`

Preserve row currency and normalize only through explicit mapping while retaining raw source currency.

### `quantity_unit`

Use explicit source UOM first; otherwise use approved provider/currency fallback rule from Section 7.

---

# 9. BVD provider rules — first production baseline

BVD is the primary field/workflow baseline for initial Canadian production.

## 9.1 Verified fixture header

- Invoice `972201`
- Invoice date `2026-07-29`
- Statement start `2026-07-22`
- Statement end `2026-07-28`
- Due date `2026-07-30`
- Client `FIRST BASE FREIGHT LTD.`

## 9.2 Verified transaction 1

```text
Card              4237111
Auth              A204040667-TA
Driver            JASPREET CHOKAR
Unit              1100
Date/time         2026-07-23 02:17:56
Site #            54228
Site/City         BOWMANVILLE
Province          ON
Product           TA
Quantity          719.50
Retail            2.2390
Billed            2.2390
Pre-tax           1425.63
HST               185.33
Final             1610.96
Currency raw      CN
```

## 9.3 Verified transaction 2

```text
Auth              A208448597-TA
Driver            JASPREET CHOKAR
Unit              1104
Date/time         2026-07-27 13:38:39
Site #            58073
Site              BVD NIAGARA
City              Niagara on the Lake
Province          ON
Product           TA
Quantity          754.50
Retail            2.3990
Billed            2.3990
Pre-tax           1601.81
HST               208.24
Final             1810.05
Currency raw      CN
```

## 9.4 BVD controls

```text
Quantity total    1474.00
Pre-tax total     3027.44
HST total         393.57
Final total       3421.01
```

Control/subtotal rows never create transactions.

## 9.5 BVD canonical mapping

```text
Date/time         -> transaction_datetime
Unit #            -> unit_number_snapshot
Card              -> card_or_account_id
Driver Name       -> driver_name_snapshot
Site Name         -> merchant_site
Site City         -> city
Prov/ST           -> province_state
Prod              -> controlled product; raw code retained
QTY               -> quantity
Billed            -> unit_price, basis BILLED
Retail            -> provider_raw; optional explicit fallback only
HST/GST/PST/QST   -> raw components; sum to tax_amount where valid
Disc AMT          -> discount_amount
Final AMT         -> total_amount
CUR               -> normalized currency + raw CUR retained
```

BVD product/source codes (`TA`, `TF`, `DF`, `S`, `C`, `AD`, `O`, `L`, future codes) remain preserved independently of TruckERP classification.

## 9.6 BVD example: source -> canonical -> frontend

Source evidence:

```json
{
  "Prod": "TA",
  "QTY": "719.50",
  "Billed": "2.2390",
  "Final AMT": "1610.96",
  "CUR": "CN"
}
```

Canonical staging:

```json
{
  "transaction_datetime": "2026-07-23T02:17:56",
  "unit_number_snapshot": "1100",
  "driver_name_snapshot": "JASPREET CHOKAR",
  "merchant_site": "BOWMANVILLE",
  "product": "FUEL",
  "quantity": 719.50,
  "quantity_unit": "L",
  "unit_price": 2.2390,
  "unit_price_basis": "BILLED",
  "tax_amount": 185.33,
  "total_amount": 1610.96,
  "currency": "CAD",
  "source_vendor": "BVD",
  "provider_raw": {
    "Prod": "TA",
    "QTY": "719.50",
    "Billed": "2.2390",
    "Final AMT": "1610.96",
    "CUR": "CN",
    "auth_code": "A204040667-TA",
    "site_number": "54228"
  }
}
```

Possible TruckERP frontend presentation:

```text
Date              Jul 23, 2026 02:17
Unit              1100
Driver            Jaspreet Chokar
Fuel Type         Tractor Diesel
Location          Bowmanville, ON
Quantity          719.50 L
Price / Litre     $2.2390
Tax               $185.33
Total Charged     $1,610.96 CAD
```

Frontend labels are presentation only. Provider source remains unchanged underneath.

---

# 10. Nationwide provider rules — second real layout proof

Nationwide proves that provider layouts can differ materially without forcing BVD-shaped tables.

## 10.1 Row type first — critical

Determine row type before interpreting visual positions:

```text
TRANSACTION
CARD_TOTAL
INVOICE_SUMMARY
```

`XXXXX... Total` is a control row, never a purchase.

Canadian control rows may place GST/QST text visually under transaction columns. Fixed x-position interpretation without row classification is unsafe.

## 10.2 Verified Canadian transaction

```text
Account           20250522B
Card              XXXXX87195
Unit              788
Date              2026-06-09
City              NIAGARA-ON-THE-LAKE
Province          ON
Product           DIESEL
Volume            674.17
Unit price        1.659
Total             1263.85
Network           Esso
Currency          CAD
USA Discount      0.00
Missed Disc       0.00
```

Invoice/control evidence:

```text
Canadian volume       674.17 Litres
Total Ex-GST & PST    1118.45
GST                   145.40
PST                   0.00
CAD subtotal          1263.85
```

## 10.3 Explicit Nationwide Canadian GST rule — locked

When a Nationwide `CARD_TOTAL` or `INVOICE_SUMMARY` row is in Canadian context and explicitly contains:

```text
GST 145.40
```

map `145.40` **only** to the GST control field.

Likewise explicit `QST`, `PST` or `HST` label/value pairs map only to their matching control tax field.

Rules:

- classify row type first;
- require explicit tax label/value ownership;
- never interpret GST as Date, City, Product, Volume or transaction Total due to visual position;
- keep tax at control level when Nationwide does not provide per-transaction tax;
- do not prorate invoice/control tax into transaction rows during parsing;
- U.S. rows do not receive inferred Canadian GST/HST/QST/PST.

## 10.4 Verified U.S. transaction

```text
Card              XXXXX07588
Unit              794
Date              2026-06-08
City              PAULSBORO
State             NJ
Product           DIESEL
Volume            154.27
Unit price        4.685
Total             722.75
Network           TA-Petro
Currency          USD
USA Discount      34.56
```

Canonical rules:

```text
Date              -> transaction_datetime (date-only)
Unit #            -> unit_number_snapshot
Card/Account      -> card_or_account_id
Driver            -> null unless source supplies one
Network           -> merchant_site / raw network evidence
City              -> city
Pr/St             -> province_state
Product           -> controlled product + raw source
Volume            -> quantity
CAD Ex-GST price  -> unit_price, basis EX_TAX
USD displayed     -> unit_price, basis FINAL_GALLON_PRICE
Per-row tax       -> null when unsupported
USA Discount      -> supported discount mapping + raw value
Total             -> total_amount
Currency          -> currency
```

## 10.5 Mixed currency/UOM example

One Nationwide statement can render dynamically:

```text
Jun 09 2026   Unit 788   CAD   674.17 L     $1.659/L   Total $1,263.85 CAD
Jun 08 2026   Unit 794   USD   154.27 gal   $4.685/gal Total $722.75 USD
Jun 11 2026   Unit 789   USD   109.30 gal   $4.724/gal Total $516.33 USD
```

Each row decides its own currency/UOM presentation. The statement does not have one global measurement unit.

## 10.6 Currency controls

```text
CAD provider total = 1263.85
USD provider total = 5197.69
```

Reconcile independently. Never create a fake CAD+USD provider total.

## 10.7 Rounding

Preserve:

- provider detail rows,
- calculated row sum,
- printed card/invoice control,
- variance.

Never alter row amounts to force equality. Until a provider-specific tolerance is explicitly approved, unexplained variance remains `REVIEW`.

---

# 11. Provider control totals and row/control separation

Provider controls are reconciliation evidence, never purchases.

Support control types such as:

- card subtotal,
- unit/group subtotal,
- product subtotal,
- currency subtotal,
- invoice/grand total,
- tax control,
- discount control,
- provider-declared total,
- calculated detail-row total,
- variance.

Required invariant per provider/currency:

```text
all validated source transactions
+ explicitly approved provider rounding/control adjustment only when policy allows
= provider declared control total
= validated total
```

And:

```text
missing source transactions = 0
unintended duplicates = 0
unresolved financial destinations = 0
unexplained variance = 0
```

Grand-total equality never excuses wrong unit/date/card assignment.

---

# 12. Historical truck, driver and ownership resolution

`truck_id` is permanent physical asset identity. Unit number is operational and can change.

Required unit history concept:

```text
truck_id
unit_number
effective_from
effective_to
reason
changed_by
```

Resolution:

```text
unit_number_snapshot + transaction_datetime
        -> exactly one truck_id
```

Zero/multiple matches = `REVIEW`; never current-truck fallback.

Ownership/payee is also effective-dated and resolves at transaction time.

Same physical truck renumbered -> same `truck_id`; replacement truck -> new `truck_id`.

Driver identity follows the same source-vs-resolution rule:

```text
driver_name_snapshot = only what provider reported
resolved driver_id   = TruckERP historical relationship
```

Do not backfill provider snapshots.

---

# 13. O/O pricing and financial responsibility

Provider amount/cost and O/O contractual settlement charge are separate.

Supported O/O fuel pricing modes:

- pump price / no provider discount passed through,
- full provider/company discount,
- fixed cents per litre/gallon passed through,
- percentage of provider discount passed through.

Percentage means percentage of the **provider discount**, not pump price.

Example:

```text
Pump price             3.00
Provider discount      0.25
Company/provider cost  2.75
O/O discount allowed   0.05
O/O charged price      2.95
```

Agreement belongs to the O/O/payee settlement relationship and is effective-dated.

Classification and financial responsibility are separate questions.

Company truck/company driver baseline:

- Fuel/DEF/company operating product -> company expense.
- Coolant/oil/additive for company truck -> company expense; no driver deduction.
- Cash advance -> driver receivable/deduction under policy.

O/O truck baseline:

- Fuel -> O/O charge under effective fuel agreement.
- DEF/product/coolant/oil/additive -> O/O deduction under policy.
- Cash advance -> O/O/payee unless explicitly driver-specific policy.

Cross-module:

- Lumper -> Fuel/Card preserves source/classification; Dispatch/Load owns load association/reimbursement.
- Toll -> Toll module/policy owns toll-specific processing.

Every finalized provider transaction must have exactly one allowed financial destination.

---

# 14. Admin review workflow

For document sources:

```text
Upload one or many PDFs
-> Parse
-> review queue
-> LEFT original PDF / RIGHT parsed canonical/provider data
-> Admin checks/corrects
-> Save & Next
-> next PDF auto-loads
-> after queue: Process
-> backend gates
-> Summary
-> Finalize/OK only when allowed
-> close/done
```

`Save & Next` means source review only. It never posts money.

Right pane may present fields in TruckERP-friendly order/labels while retaining a way to inspect provider/raw detail.

Corrections retain:

```text
parsed_value
reviewed_value
review_reason
reviewed_by
reviewed_at
```

---

# 15. Fuel Operations workspace

Minimum filters:

- date/period,
- provider,
- processing network when known,
- merchant/network,
- card/account,
- unit/truck,
- driver,
- O/O/payee,
- product/category,
- source,
- currency,
- company vs O/O responsibility,
- matched/unmatched,
- reconciled/unreconciled,
- posted/unposted.

Unit/truck is a primary grouping.

Exception rows drill to exact source batch/PDF/file/raw evidence.

If RBAC allows, the Fuel page may also expose provider connection cards/settings using the same backend provider-connection model as Admin.

---

# 16. Manual driver entry

Manual entry is a first-class source but not a separate accounting path.

Driver supplies practical fields:

- assigned unit when reliable,
- transaction date/time,
- location/station,
- product,
- quantity,
- quantity unit,
- amount,
- currency,
- receipt/photo where available.

Authenticated context supplies driver identity where possible.

When later provider PDF/DAT/SFTP/API evidence arrives, duplicate matching must prevent a second financial charge. Strong exact matches follow proven rules; ambiguous matches remain review-required.

---

# 17. Settlement/payroll handoff

Provider invoice total is not one O/O settlement deduction.

Settlement selects only transactions matching:

- correct O/O/payee,
- correct historical truck,
- transaction date in settlement period,
- effective pricing agreement,
- correct financial-responsibility route,
- all mandatory gates passed.

Required drill-down:

```text
O/O/payee
 -> Unit 1100
    -> exact transaction rows
 -> Unit 1104
    -> exact transaction rows
 -> total Fuel/Card deduction
```

Each deduction retains source transaction context, currency, quantity/UOM, provider amount and calculated O/O charge.

---

# 18. Audit, correction, reversal and immutability

Preserve:

- original source file/reference/hash,
- provider connection/account,
- parser/adapter/rule version,
- parser output,
- raw provider row,
- parsed/reviewed values,
- reviewer/time/reason,
- truck/card/unit resolution,
- ownership/payee resolution,
- financial responsibility,
- pricing rule/version,
- settlement posting,
- adjustment/reversal.

Use existing `audit_events` where appropriate.

Provider connection changes are auditable but secrets never enter audit payloads.

After posting, do not silently rewrite financial history. Use audited adjustment/reversal.

---

# 19. Implementation segments

## Segment 0 — Repository archaeology

Inspect/reuse:

- tenant DB/migrations,
- truck ownership/unit history,
- people/payee/compensation,
- Document Platform and Load-parser contract pattern,
- audit events,
- storage,
- `/admin/integrations/fuel`,
- RBAC,
- secret-storage patterns,
- scheduler/background job patterns,
- settlement/payroll models.

**Execution Record:** NOT STARTED

## Segment 0A — Provider catalog + tenant connection backend

Implement:

- provider registry/catalog,
- tenant provider connection model,
- connection-method metadata,
- dynamic field schema,
- secure secret reference,
- RBAC-protected endpoints,
- test-connection adapter hook,
- same records exposed from Admin and Fuel page,
- multiple accounts/provider per tenant.

Do not implement fake connectivity for providers without real specs.

**Execution Record:** NOT STARTED

## Segment 1 — Canonical Fuel/Card schema

Implement source batches, canonical transactions, raw sidecar, source identity/order, optional network/merchant fields and separate resolution fields.

**Execution Record:** NOT STARTED

## Segment 2 — Provider controls

Implement control records and transaction/control separation. Controls never increment purchase count.

**Execution Record:** NOT STARTED

## Segment 3 — Historical truck/ownership resolution

Effective-dated unit and ownership/payee history; ambiguous/missing match -> review.

**Execution Record:** NOT STARTED

## Segment 4 — O/O fuel pricing

Implement four pricing modes, effective dates, permissions, provider amount vs settlement charge separation.

**Execution Record:** NOT STARTED

## Segment 5 — Fuel AI handoff contract + validator

Implement versioned JSON contract, provider rules, field rules, strict output schema, mechanical validator and parser-version persistence.

**Execution Record:** NOT STARTED

## Segment 6 — BVD PDF rules + structured export adapter

Implement BVD PDF fixture first. Then implement deterministic structured BVD/T-Chek export-file adapter when the real file sample is available.

Both hydrate the same canonical schema.

**Execution Record:** NOT STARTED

## Segment 7 — Nationwide PDF rules

Implement row-type-first parser, explicit Canadian GST control rule, CAD/USD/UOM behavior, rounding review, driver-null behavior.

**Execution Record:** NOT STARTED

## Segment 8 — Review queue UI/backend

Left source / right TruckERP presentation, Save & Next, Process, Summary, Finalize with backend gates authoritative.

**Execution Record:** NOT STARTED

## Segment 9 — Reconciliation engine

Every source transaction accounted exactly once; provider controls/currency totals validated; unresolved relationships block.

**Execution Record:** NOT STARTED

## Segment 10 — Classification and financial responsibility

Separate transaction category from who owes/pays it; cross-module routing for Toll/Lumper.

**Execution Record:** NOT STARTED

## Segment 11 — Manual driver entry + duplicate matching

Same canonical path; later provider source does not double-charge.

**Execution Record:** NOT STARTED

## Segment 12 — Settlement/payroll handoff

Only eligible resolved rows, multi-truck O/O drilldown, exact sum/idempotency.

**Execution Record:** NOT STARTED

## Segment 13 — Fuel Operations workspace

Transactions/imports/exceptions/provider connections under RBAC, dynamic per-row unit/currency display.

**Execution Record:** NOT STARTED

## Segment 14 — Audit/reversal/immutability

Full trace from provider source to money movement; no silent post-finalization mutation.

**Execution Record:** NOT STARTED

## Segment 15 — End-to-end hardening / Gold readiness

Do not establish Fuel Gold merely because code compiles.

**Execution Record:** NOT STARTED

---

# 20. Required test families

At minimum test:

1. Tenant A cannot access Tenant B provider connection/import.
2. Backend provider catalog drives frontend fields.
3. Unauthorized user cannot manage/test/sync provider connection.
4. Secret write succeeds but secret never returns/logs/audits.
5. Multiple provider accounts under one tenant remain distinct.
6. BVD PDF exact fixture extraction.
7. BVD structured file adapter preserves every source field when fixture becomes available.
8. BVD raw `CN` currency remains preserved while canonical mapping is explicit.
9. BVD controls excluded from transactions and reconcile.
10. Nationwide `TRANSACTION` vs `CARD_TOTAL` vs `INVOICE_SUMMARY` classification.
11. Nationwide `GST 145.40` Canadian control maps only to GST control.
12. Nationwide U.S. row receives no inferred GST/HST/QST/PST.
13. Nationwide driver snapshot remains null when source has no driver.
14. Nationwide CAD and USD reconcile independently.
15. Nationwide mixed statement renders CAD rows in litres and USD rows in gallons when no explicit source UOM overrides.
16. Explicit source UOM always wins over currency fallback.
17. Unit-price basis matches provider semantics (`BILLED`, `EX_TAX`, `FINAL_GALLON_PRICE`).
18. Row boundary contamination is rejected.
19. Parser rule version stored with batch.
20. Reparse with newer rules allowed only under explicit unfinalized workflow.
21. New parser version never silently changes finalized financial history.
22. Historical unit renumber resolves correct permanent truck.
23. Ownership change routes transaction according to transaction date.
24. Company coolant/product purchase does not create driver deduction.
25. O/O fuel pricing modes calculate correctly without changing provider amount.
26. Manual then provider source produces one financial charge after resolution.
27. Lumper remains source-accounted but does not auto-link to arbitrary active load.
28. Provider file/hash idempotency prevents duplicate batch.
29. Transaction-level dedupe works independently of file-level dedupe.
30. Finalization is idempotent.
31. Existing Load parser remains green.
32. Relevant People/Payee/Truck regressions remain green.

---

# 21. End-to-end mandatory scenarios

### A. BVD company truck

BVD source -> parse/map -> review -> controls reconcile -> historical truck -> company expense -> no O/O deduction.

### B. BVD multi-truck O/O

Two BVD units -> same O/O payee -> effective pricing -> unit drilldown -> exact settlement total.

### C. BVD structured export

Real T-Chek-compatible BVD export -> deterministic adapter -> same canonical records as equivalent PDF source -> no AI required.

### D. BVD card used at Love's

Source/account provider remains BVD; merchant may be Love's; processing network stored only when proven. No duplicate “Love's provider” transaction is created merely because merchant is Love's.

### E. Nationwide mixed CAD/USD

CAD line -> litres/$ per litre; USD line -> gallons/$ per gallon unless explicit source UOM says otherwise; currencies reconcile independently.

### F. Nationwide control trap

Canadian GST/QST control row never becomes a fake transaction/date/city.

### G. Nationwide rounding variance

Preserve provider rows and provider control; variance remains review until policy proven.

### H. Manual then provider source

Driver enters transaction manually -> provider source later arrives -> candidate duplicate -> one financial charge.

### I. Historical renumber

Old provider unit snapshot resolves correct permanent truck by transaction date.

### J. Ownership change

Transactions before/after ownership effective date route to correct financial party.

### K. Posted correction

Normal edit blocked -> audited reversal/adjustment.

### L. RBAC provider setup

Authorized user can add provider from Admin or Fuel page using same backend record; unauthorized user blocked server-side.

---

# 22. Review protocol

For each returned implementation segment verify:

- shared TruckERP services were reused;
- provider catalog, not frontend, drives connection fields;
- RBAC is backend enforced;
- secrets never return to browser/log/audit/parser;
- provider source/raw values remain lossless;
- canonical values remain separate from presentation labels;
- provider/program vs processing network vs merchant are not conflated;
- transaction datetime drives historical decisions;
- explicit source UOM wins; approved currency fallback is per-row only;
- control rows are excluded from transactions;
- currencies reconcile independently;
- ambiguous relationships block rather than guess;
- UI cannot bypass backend money gates;
- provider amount and O/O charge remain separate;
- final result traces to exact source evidence;
- tests actually ran with counts recorded.

Any failed answer leaves the segment open.

---

# 23. Explicitly deferred

Unless explicitly reopened:

- unverified BVD direct API/SFTP connection,
- Nationwide automated machine feed beyond captured PDF/real CSV evidence,
- provider APIs/data-sharing flows without actual onboarding contract,
- automatic provider-specific rounding tolerance without proof,
- automatic lumper-to-load matching beyond a separately safe workflow,
- new O/O subsidy rule allowing more discount than provider actually gave,
- currency conversion/accounting translation that rewrites source transaction currency/UOM.

These deferrals must not be silently implemented inside another segment.
