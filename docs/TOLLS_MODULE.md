# TruckERP Tolls Module

**Status:** Working design / research document  
**Purpose:** Living source of truth for the TruckERP Tolls module.  
**Rule:** Add provider capabilities only when confirmed by provider documentation or a verified integration source. Do not design permanent schema from assumptions.

---

## 1. Module Goal

TruckERP Tolls should provide one place to ingest, normalize, review, reconcile, assign, process, and retain toll-related transactions across supported toll providers and toll authorities.

The module must be provider-agnostic. PrePass may be a major source/aggregator, but TruckERP's permanent toll model must not be designed around a single provider's raw payload.

---

## 2. Provider Research

### 2.1 PrePass / PrePass Plus

**Research priority:** First toll integration to investigate.

### Confirmed coverage / capability

PrePass states:

> **In addition to weigh station bypassing, PrePass Plus takes the hassle out of tolls by enabling fleets to pay tolls, handle violations and toll disputes through a single transponder, and receive a consolidated bill from one service provider.**

Source image / coverage reference:

![PrePass Plus expanded coverage legend](https://enrollment.prepass.com/images/Expanded_Legend.png)

Source:
- PrePass / PrePass Plus enrollment material
- Image: https://enrollment.prepass.com/images/Expanded_Legend.png

### What this means for TruckERP

PrePass Plus potentially covers more than simple toll-charge ingestion. The Tolls module should be designed with room for these business functions:

1. **Toll transactions**
   - Import toll charges.
   - Preserve provider transaction identity and raw source data.
   - Map transactions to TruckERP assets / units.

2. **Consolidated billing**
   - Support a provider invoice/statement that may contain tolls from multiple toll authorities.
   - Reconcile the provider statement total against accepted TruckERP toll transactions.

3. **Violations**
   - Preserve violation-related transactions separately from ordinary toll charges when the provider exposes them.
   - Do not silently classify violations as normal tolls.

4. **Toll disputes**
   - Allow future support for dispute lifecycle/status if PrePass exposes dispute data or actions through its API.
   - Do not implement dispute workflow until the API/documentation is verified.

5. **Single-transponder / multi-network operation**
   - Do not assume one toll authority equals one transponder.
   - Provider/account/transponder/vehicle relationships must preserve history.

6. **Toll authority normalization**
   - Even when PrePass is the source, the underlying toll authority should be retained when available.
   - TruckERP should be able to report by provider and by underlying toll authority.

---

## 3. Initial Source Architecture

```text
Toll sources
├─ PrePass API / PrePass Plus
├─ E-ZPass / toll authority CSV or other export
├─ other toll providers / aggregators
└─ manual entry

        ↓

provider/source adapter

        ↓

normalized review rows

        ↓

mapping + validation + reconciliation

        ↓

Process

        ↓

immutable toll history
```

This is an initial architecture direction only. It is not yet a locked database design.

---

## 4. PrePass API — Confirmed Contracts

### 4.1 Account API v1

**Purpose:** Returns all PrePass accounts associated with the authenticated user, including detailed account information.

**Request endpoint:**

```http
GET https://api.prepass.com/accounts/v1/accounts
```

**Response content type:** `application/json`

**Security declared by this OpenAPI contract:**

The Account API v1 specification declares an API-management subscription key using either:

```text
Ocp-Apim-Subscription-Key: <subscription key>
```

as a request header, **or**:

```text
?subscription-key=<subscription key>
```

as a query parameter.

TruckERP should prefer the header form so the subscription key is not placed in URLs/logs.

**Important:** this Account API OpenAPI document declares the subscription-key schemes but does not itself declare a Bearer security scheme. Do not assume the same authentication combination applies uniformly to every PrePass endpoint; follow each API contract.

**200 OK response object:** `GetAccountsResponse`

| Field | Required | Type | Meaning |
|---|---:|---|---|
| `status` | No | string | API request status |
| `message` | No | string | API request status message |
| `accounts[].accountNumber` | Yes | string | PrePass account number tied to API credentials |
| `accounts[].accountName` | Yes | string | Account name in PrePass systems |
| `accounts[].costCenter` | No | string | Customer-defined organization/location/expense-center code |
| `accounts[].accountStatus` | Yes | string | Account status: `Active`, `Inactive`, or `Archived` |

### 4.2 TruckERP implications from Account API v1

This confirms that one authenticated PrePass integration can expose **multiple PrePass accounts**. Therefore TruckERP must not assume a single PrePass account per tenant.

Minimum source-account identity to preserve:

```text
provider = PREPASS
account_number
account_name
cost_center
account_status
```

Minimum PrePass connection secrets/config now known:

```text
client_id
client_secret_ref
subscription_key_ref
api_base_url = https://api.prepass.com
```

The subscription key is separate from the client secret and should use the same write-only secret-reference handling.

Important design consequences:

- `accountNumber` is the external PrePass account identity and should be stored as a string.
- `costCenter` is optional and may represent the customer's internal location or expense-center organization.
- `accountStatus` must not be reduced to a boolean because PrePass distinguishes `Active`, `Inactive`, and `Archived`.
- Toll imports should retain which PrePass account produced each transaction.
- If the Toll Transaction API requires an account number, TruckERP can populate the selectable accounts directly from this API rather than requiring manual account-number entry.
- Inactive or archived accounts may still matter for historical transactions and must not be deleted merely because they are not active.
- PrePass account data is provider metadata, not TruckERP's canonical company/terminal structure. Mapping a PrePass cost center to a TruckERP terminal, division, or expense center should be explicit.

### 4.3 Token API v1

**Purpose:** Obtain a security token for PrePass API access using the client ID and client secret.

**Base server:**

```text
https://api.prepass.com/auth/v1
```

**Endpoint:**

```http
POST https://api.prepass.com/auth/v1/token
```

**Required request headers:**

```text
client_id: <PrePass client ID>
client_secret: <PrePass client secret>
```

The OpenAPI definition explicitly places both values in request headers. Do not implement this as an assumed generic OAuth form-body request.

**Successful response fields:**

| Field | Type | Meaning |
|---|---|---|
| `token_type` | string | Issued token type; example is `Bearer` |
| `expires_in` | integer | Token lifetime in seconds |
| `ext_expires_in` | integer | Extended lifetime value |
| `access_token` | string | API access token |

The documented example returns `expires_in: 3599`, so normal token life is approximately one hour.

**Documented errors:**

- `400` — invalid request / missing required authentication material.
- `401` — invalid client credentials.

### 4.4 TruckERP implications from Token API v1

The PrePass connection layer can now be treated as confirmed rather than placeholder behavior.

Recommended connection/test flow:

```text
client_id + client_secret_ref
        ↓
POST /auth/v1/token
        ↓
Bearer access_token

subscription_key_ref
        ↓
call Account API using its documented APIM subscription-key security
        ↓
confirm authorized PrePass accounts
        ↓
connection test = OK
```

The exact combination of Bearer token + subscription key must be implemented per endpoint documentation. The Account API OpenAPI contract explicitly declares the subscription key; the Token API supplies the Bearer token for PrePass API access.

Important rules:

- Store both the client secret and the APIM subscription key only through TruckERP's credential/secret reference mechanism.
- Do not display the client secret after save.
- Treat the returned Bearer token as sensitive ephemeral authentication material.
- Prefer memory/Redis/encrypted short-lived cache rather than storing the raw access token permanently in the provider connection row.
- Refresh the token when expired or shortly before expiry.
- A "Test Connection" should obtain a token **and then call Account API v1**, so success proves both authentication and actual account access.
- Do not automatically enable the provider merely because credentials were saved.

---

## 5. PrePass Toll Transaction API v1 — Confirmed

**Purpose:** Retrieve detailed toll transaction records for PrePass accounts.

**Endpoint:**

```http
GET https://api.prepass.com/tolltransaction/v1/transactions
```

### Request rules that matter

- `startPostDate` and `endPostDate` are required.
- Post-date format: `yyyy-mm-dd`.
- Start date cannot be more than 2 years old.
- One request may cover at most 31 days.
- For a one-day pull, PrePass says the end date should be the following day.
- At least one `accountNumbers` or `costCenters` filter is required.
- Account numbers and cost centers cannot be mixed in the same request.
- Multiple account numbers or cost centers can be comma-separated.
- Supplying a parent account returns associated child-account data.
- Pagination is supported.
- `pageSize` defaults to 10,000 and has a maximum of 10,000.

### Response fields worth preserving

**Identity / account**
- `tollId` — PrePass unique toll transaction ID.
- `accountNumber`, `accountName`.
- `billToAccountNumber`, `billToAccountName`.
- `costCenter`.

**Dates**
- `postDateTime`.
- `invoiceDateTime`.
- `entryDateTime`, `entryDateTimeUtc`.
- `exitDateTime`, `exitDateTimeUtc`.

**Vehicle / transponder**
- `deviceNumber` — transponder or sticker number.
- `ppDeviceId` — PrePass unique main device ID.
- `vehicleNumber` — customer's unique vehicle identifier.
- `plateNumber`, `plateState`.
- `deviceStatus` — Assigned or Unassigned.
- `readType` — Plate or Device.

**Toll authority / location**
- `tollAgencyCode`, `tollAgencyName`, `tollAgencyState`.
- `billingAgencyCode`.
- `entryPlazaCode`, `entryPlazaName`.
- `exitPlazaCode`, `exitPlazaName`.
- `tollClass`.

**Money / business state**
- `tollCharge` — total charges associated with the toll transaction.
- `tollCategory` — Normal or Violation.
- `disputeStatus`.
- `disputeStatusReason`.

**Pagination**
- `pageInfo.pageNumber`.
- `pageInfo.pageSize`.
- `pageInfo.totalRecords`.
- `pageInfo.totalPages`.


### 5.1 OpenAPI implementation cautions

The supplied OpenAPI 3.0.1 contract confirms the endpoint and field set above, but it also contains type inconsistencies that the adapter must tolerate.

- `tollId` is declared as a **string** in the schema, while the example payload shows a numeric value.
- `tollCharge` is declared as a **string** in the schema, while the example payload shows numeric values such as `8.25` and `12`.
- `accountNumber` and `billToAccountNumber` are declared as integers in the Toll Transaction API, even though the Account API represents account numbers as strings. TruckERP should normalize external account identifiers to strings internally rather than depend on the provider's inconsistent schema typing.
- `entryDateTimeUtc` and `exitDateTimeUtc` are explicitly nullable.
- Several fields are marked required by the schema but may contain empty strings in actual examples, including plate and entry-plaza values. "Required" must therefore mean "key present," not "usable business value."
- `costCenter` is optional and documented as being included only when requesting transactions by cost center.
- The API documents `204 No Content` in addition to `200`, `400`, `401`, `403`, `404`, and `500`.

**Adapter rule:** ingest the raw payload exactly as returned, then normalize types defensively.

Recommended normalization examples:

```text
provider_transaction_id = str(tollId)
account_number          = str(accountNumber)
bill_to_account_number  = str(billToAccountNumber)
toll_amount             = Decimal(str(tollCharge))
```

Do not reject a transaction solely because a provider field is returned with a different JSON primitive type than the OpenAPI schema example implies.

### Important TruckERP conclusions

This API already gives us most of the data we were hoping to avoid rebuilding from individual toll agencies:

- underlying toll authority
- billing authority
- entry/exit plazas
- local and UTC timestamps
- vehicle number
- transponder/sticker identity
- plate identity
- toll class
- toll amount
- Normal vs Violation
- dispute state
- billing account and invoice date

PrePass therefore fits the role of a **major toll aggregator/source adapter** in TruckERP.

TruckERP should use `tollId` as the provider transaction identity for duplicate protection. The provider payload must still be retained raw.

Vehicle mapping should use a controlled hierarchy rather than guessing:

```text
PrePass vehicleNumber
    ↓
known TruckERP unit mapping

deviceNumber / ppDeviceId
    ↓
historical transponder-to-asset assignment

plateNumber + plateState
    ↓
historical asset plate identity

otherwise
    ↓
REVIEW / unmapped
```

`readType` matters because a transaction may have been identified by **Plate** rather than **Device**.

Violations must remain distinguishable from normal toll charges, and dispute fields must be retained even if TruckERP initially treats disputes as read-only provider state.

### Confirmed gap

The documented Toll Transaction response does **not** show separate fields for discount amount, administrative fee, violation fee, currency, or invoice number. Do not invent these fields as PrePass-supplied values unless another API or later documentation confirms them.

---


## 6. PrePass Fleet Management API v2 — Confirmed

**Purpose:** Manage vehicles enrolled in bypass and/or tolling services, including vehicle lookup, transponder lookup/assignment/order, vehicle add/update/delete, and lost/stolen transponder reporting.

**Base server:**

```text
https://api.prepass.com/fleetmanagement/v2
```

### 6.1 Vehicle lookup

```http
GET /vehicles
```

Supports lookup by:

- `vin`
- `vehicleNumber`
- `accountNumber`
- `costCenter`

The response can include:

- `accountNumber`
- `costCenter`
- `vin`
- `vehicleNumber`
- `tempPlate`
- `licensePlateNumber`
- `licensePlateState`
- `declaredWeight`
- `irpNumber`, `irpState`
- `iftaNumber`, `iftaState`
- `transponderNumber`
- `vrn`
- `hazmatHauler`
- `vehicleImage`
- `leasedVehicle`
- `leasingCompany`
- `leaseExpirationDate`

This is a strong identity bridge between PrePass and TruckERP assets because one response can tie together:

```text
VIN
↔ customer vehicle/unit number
↔ plate + state/province
↔ transponder number
↔ PrePass account/cost center
```

### 6.2 Vehicle lifecycle actions

The API also exposes:

```text
POST   /vehicle   add vehicle
PATCH  /vehicle   update vehicle
DELETE /vehicle   remove vehicle
```

VIN is the immutable lookup key for updates.

TruckERP should initially treat these write operations as **future capability**, not automatic behavior. The first integration phase should be read/sync only unless a later decision explicitly enables outbound PrePass fleet management.

### 6.3 Transponder lookup

```http
GET /transponder
GET /transponders
```

`GET /transponder` looks up one transponder by `transponderNumber`.

`GET /transponders` lists transponders by PrePass account number or cost center.

Returned transponder records can include:

- `accountNumber`
- `vin`
- `vehicleNumber`
- `vrn`
- `transponderNumber`
- `costCenter`

The examples prove that a transponder may exist with blank VIN and vehicle number, so TruckERP must support **unassigned transponders** rather than assuming every device belongs to an asset.

### 6.4 Transponder operations

The API also supports:

```text
POST /orders               order transponders for specified VINs
POST /transponders/lost    report lost or stolen transponders
```

PrePass states that transponders are assigned to vehicles during order fulfillment.

### 6.5 TruckERP implications

The Fleet Management API materially improves toll attribution.

Recommended mapping priority can now be strengthened to:

```text
1. PrePass vehicleNumber → TruckERP unit number
2. VIN → TruckERP asset/VIN identity
3. transponderNumber → current/historical PrePass device assignment
4. plate number + jurisdiction → historical asset plate identity
5. otherwise → REVIEW / unmapped
```

TruckERP should sync PrePass fleet reference data separately from toll transactions so the transaction processor is not forced to rediscover vehicle identity one row at a time.

Suggested provider-side reference caches:

```text
prepass_vehicle_reference
prepass_transponder_reference
```

These are source/reference tables, not replacements for TruckERP's canonical Asset/VIN history.

Important design rules:

- VIN remains the strongest asset identity when present.
- `vehicleNumber` is customer-assigned and can map naturally to TruckERP unit number, but should not replace VIN identity.
- Transponder assignments may change over time, so TruckERP should preserve effective-dated assignment history rather than only the current mapping.
- Unassigned transponders are valid provider state.
- Plate matching must remain historical because plates can change.
- PrePass IRP/IFTA/lease fields are useful enrichment but should not overwrite TruckERP canonical compliance/asset records silently.
- The Fleet Management v2 OpenAPI file does not declare a security scheme. Authentication must therefore remain driven by confirmed PrePass endpoint/security documentation rather than inferred from this file.
- The older `/fleetmanagement/v2/accounts` endpoint is explicitly deprecated; use Account API v1 instead.

### 6.6 Scope note

PrePass warns not to use this API to update tractors enrolled in the Toll Violation Prevention Program (VPP) or trailer plates. Any future write integration must respect that restriction.

---


## 7. PrePass GPS Data API v2 — Confirmed

**Purpose:** Allows carriers to send truck-trip GPS data to PrePass for toll validation.

**Base server:**

```text
https://api.prepass.com/api/tolls/gps/v2
```

**Endpoint:**

```http
POST /gpsevents?accountNumber=<PrePass account>
```

The account number is required as a query parameter.

### 7.1 Payload structure

Top-level request fields:

- `postedTime`
- `vehicles[]`

Each vehicle can include:

- `deviceNumber`
- `vin`
- `totalAxleCount`
- `plateNumber`
- `plateState`
- `trackSegment[]`

Each GPS point can include:

- `latitude`
- `longitude`
- `timestamp`
- `timezone`
- `speed`
- `direction`
- `locationAccuracy`

The schema marks these vehicle/GPS fields nullable, so TruckERP must not assume every GPS submission contains every identifier or telemetry value.

### 7.2 Responses

- `200` — GPS data processed successfully.
- `400` — validation failure; response can identify invalid vehicles and individual invalid GPS entries.
- `401` — unauthorized.
- `500` — server error.

The validation-error response is detailed enough to identify both the vehicle index and GPS-entry index that failed, which is useful for batch diagnostics.

### 7.3 TruckERP implications

This API is **not part of the core toll-transaction import path**. It is a future validation/enrichment integration.

Potential architecture:

```text
TruckERP ELD / GPS source
        ↓
normalized trip GPS
        ↓
PrePass GPS Data API
        ↓
PrePass toll validation
        ↓
PrePass Toll Transaction API
        ↓
TruckERP toll transaction reconciliation
```

Potential value:

- help validate whether a truck actually traveled through a toll location
- support investigation of questionable tolls/violations
- strengthen device/plate/VIN attribution
- provide axle-count context for toll-class validation
- improve future dispute workflows

Initial Tolls implementation should **not depend on GPS submission**. Build toll ingestion so it works without this API; add GPS validation later when TruckERP has a stable ELD/GPS source.

### 7.4 Privacy and retention rule

GPS payloads contain sensitive vehicle-location history. If TruckERP later enables this integration:

- send only the minimum GPS window required for the PrePass use case
- do not duplicate long-term GPS retention merely because PrePass accepts the data
- log batch/result metadata without logging complete raw location traces
- keep tenant authorization and audit boundaries strict

---





## PDF / No-Account Intake Lock

TruckERP Tolls must support tolls that arrive **without any API account or transponder relationship**.

Real-world cases include:

- a carrier/driver has no toll-provider account or transponder
- a toll authority sends a bill by email as a PDF
- a toll bill is downloaded manually from a portal
- a missing toll was not present in the API feed
- a plate-read toll arrives separately from the normal provider feed

Therefore PDF/manual document upload is a **first-class source**, not a temporary workaround.

### Source types

Initial Toll source types:

```text
API
FILE
MANUAL
```

`FILE` includes provider/user-downloaded statement or transaction files such as:

```text
PDF
CSV
```

Examples:

- E-ZPass portal CSV download
- toll-authority PDF bill received by email
- manually downloaded PDF statement
- missing toll file uploaded by admin

This mirrors the Fuel design: the business source is a file intake path, while the file format determines the parser/profile behavior.

### File flow

```text
Admin uploads toll file
        ↓
detect/validate declared file format within Toll intake
        ↓
PDF → explicit TOLL document profile using shared Document Platform
CSV → Toll CSV adapter/profile
        ↓
Toll-specific normalization
        ↓
resolve vehicle/unit
        ↓
store toll transaction(s)
        ↓
admin history/detail
```

The Toll module owns the business intake. PDF and CSV are two representations of the same file-source concept.

The calling Toll API selects the Toll profile explicitly. Document Platform must not inspect a PDF and guess that it is a toll document.

### Account/transponder rule

A file-based toll must **not** require:

- provider connection
- PrePass account
- transponder number
- device assignment

Plate number, VIN, unit number, or other document evidence may be used to resolve the TruckERP vehicle/unit.

If the vehicle cannot be resolved confidently, keep the transaction review/unmapped rather than guessing.

### Missing-toll / overlap rule

File upload must coexist safely with API data.

A PDF or CSV may contain:

- transactions already received from an API
- transactions missing from the API
- a mixture of both

Do not blindly insert duplicates and do not blindly discard a PDF because some rows overlap.

Provider/API identity should be used when available. PDF-only rows need a separate source-row/document identity and conservative duplicate detection based on the strongest available source evidence.

The original uploaded file and extracted/parsed raw source data must be retained for audit.

---

## Pull-Based Downstream Consumption Lock

The Tolls module is primarily a **vehicle-linked transaction store and query source**.

Normal business behavior is simple:

```text
tolls arrive
    ↓
store against correct unit
    ↓
admin can view if needed
    ↓
STOP
```

Most companies do not review toll transactions one by one before paying/using them. TruckERP should therefore avoid building an unnecessary per-row operational workflow around tolls.

### Admin view

Admin needs a straightforward history/search screen for audit and troubleshooting.

Primary display fields:

```text
Date/Time
Unit
Toll Agency
Amount
Type
Read By
Identifier
```

Expanded row shows full provider detail.

### Downstream access model

Downstream modules should **pull/query** tolls when needed rather than Tolls pushing financial actions into other modules.

Example:

```text
Payroll requests:
unit = 1104
from = Monday
to = Sunday

Tolls returns:
all toll transactions for unit 1104 in that date range
```

Then Payroll/Settlement/other downstream logic decides whether those tolls are:

- owner-operator deductions
- company expenses
- settlement items
- ignored for that workflow
- handled under another rule

The Tolls module does not make that decision.

### Locked API/query principle

Tolls must support efficient queries by at least:

```text
tenant_id
unit_id / unit_number
transaction date/time range
```

Provider identifiers such as device/transponder/plate remain available for lookup and troubleshooting, but downstream business modules should normally consume tolls by TruckERP unit identity + date range.

**Architecture rule:** downstream modules pull toll data on demand; Tolls does not push payroll/owner/settlement actions.

---

## Toll Event Ordering and Multiple Tolls per Unit

A single vehicle/unit can legitimately receive multiple toll transactions within the same hour or even within a few minutes.

Example:

```text
Unit 1104
10:05  Niagara bridge toll      $5.25
10:42  I-90 toll transaction    $12.00
```

These are two separate toll events and must remain two separate records.

**Locked rule:** never deduplicate or collapse tolls by date + unit, date + device, or hour.

Provider uniqueness comes from the provider transaction identity:

```text
provider = PREPASS
provider_transaction_id = tollId
```

The normal Toll History view should be ordered/grouped primarily by:

```text
transaction date/time
    ↓
unit number
    ↓
read source / identifier
```

Where the identifier is:

```text
readType = DEVICE
→ deviceNumber / transponder number

readType = PLATE
→ plateNumber + plateState
```

For display, multiple rows for the same unit on the same date/hour are expected and correct.

The expanded row can show the provider details that distinguish the events, including entry/exit plaza and timestamps.

---

## Vehicle-Boundary Lock

**Tolls is a vehicle/unit module first.**

The Tolls module's responsibility is to ingest, normalize, validate, and attach each toll transaction to the correct TruckERP vehicle/unit.

Example:

```text
PrePass toll
    ↓
resolve to unit 1104
    ↓
store toll against unit 1104
    ↓
STOP
```

At this stage it does **not matter** whether unit 1104 is:

- a company-owned truck
- an owner-operator truck
- driven by a company driver
- driven by an owner-operator
- temporarily assigned to another driver

Those are downstream business relationships.

The Tolls module must **not** decide:

- driver deduction
- owner-operator deduction
- payroll treatment
- settlement treatment
- company-vs-owner expense responsibility

Those rules belong to later downstream modules that can consume the vehicle-linked toll transaction together with effective-dated ownership/engagement/pay rules.

**Locked design rule:** first attach the toll correctly to the vehicle/unit. Ownership, driver, payroll, settlement, and other financial responsibility logic is applied later.

---

## 8. Design Principles

- Provider data is source data; TruckERP owns the canonical business model.
- Raw provider values must be retained for audit/reprocessing.
- Money must reconcile before permanent processing.
- No silent guessing for vehicle/unit mappings.
- Processed financial history should be immutable except through controlled correction/adjustment workflows.
- Tolls must resolve the correct vehicle/unit. Ownership, driver, payroll, settlement, and responsibility logic are downstream concerns.
- Toll charges, violations, fees, discounts, reversals, and adjustments must remain distinguishable if the source exposes them.

---

## 9. Open Research Items

- Whether disputes can be created/updated through API or are portal-only.
- Whether consolidated invoice/statement identifiers are available from another PrePass API.
- Whether PrePass exposes historical transponder assignment events, or only current assignment state.
- Coverage gaps that would require direct E-ZPass/agency imports.
- Canada toll coverage and currency behavior.
- Any PrePass API rate limits not shown in the supplied specifications.

---


---


## Current Repository Audit Before Implementation

A read-only repository audit was completed before Toll implementation.

### Confirmed current state

- No `toll_*` database tables or SQLAlchemy models exist.
- No Toll Alembic migrations exist.
- No Toll router, API service, schema, provider adapter, upload endpoint, history endpoint, or search endpoint exists.
- No Toll frontend page, route, navigation item, provider screen, upload screen, or API client exists.
- No Toll Document Platform profile exists yet.
- Existing Fuel/Card code can classify a source row as `TOLL`, but the row remains in Fuel.
- Existing Fuel code does not push those rows into a Toll module.
- Existing downstream acknowledgement columns in Fuel are unused and do not define the new Toll architecture.
- Existing Fuel transaction identity already demonstrates the useful pattern that source-row identity and provider transaction identity are separate from the canonical record.
- Existing Truck/Asset models and unit-number history are reusable for unit resolution.
- Existing shared Document Platform PDF capabilities are reusable for future Toll PDF intake.

### Existing Fuel behavior that must NOT define Toll

Fuel currently has financial-responsibility logic that may inspect company/O/O context for rows classified as `TOLL`. The new Toll module must not copy or depend on that behavior.

The Toll boundary remains:

```text
source toll
    ↓
resolve correct vehicle/unit
    ↓
store toll
    ↓
STOP
```

Ownership, driver, payroll, settlement, and deduction policy remain downstream.

### Implementation consequence

Because no Toll module exists, implementation can begin without legacy Toll-table migration or compatibility work.

The first implementation slice should establish the canonical Toll data boundary before adding provider-specific APIs.

Recommended sequence:

```text
1. toll_source_batches
2. toll_transactions
3. FILE intake foundation
4. first structured CSV adapter (E-ZPass-style portal export)
5. simple admin history/search + expand detail
6. downstream read/query by unit + date range
7. PrePass connection/API sync
8. PDF Toll profile
9. manual entry / email intake as later slices
```

Provider account/connection must remain optional because FILE intake can exist without any provider account or transponder.

---



## Segment 1 — Implemented Canonical Schema Foundation

**Implementation commit:** `a5a2f13`  
**Commit message:** `feat: add toll canonical schema foundation`

**Implementation status:** coded and committed on local `main`; no tenant migration was run, no API image was reloaded, and nothing was deployed/live at the time of this checkpoint.

### Files implemented

- `app/models/toll.py`
- `app/models/__init__.py`
- `alembic_tenant/versions/t1a2b3c4d5e6_toll_source_batches_transactions.py`
- `tests/test_toll_segment_1.py`

### Migration

```text
revision: t1a2b3c4d5e6
revises:  m7n8o9p0q1r2
tenant Alembic heads after implementation: exactly one
```

### Implemented table: toll_source_batches

Purpose: one incoming Toll source batch.

Implemented source model:

```text
source_type:
  API
  FILE
  MANUAL

file_format:
  PDF
  CSV
  NULL for non-FILE sources
```

Important implementation rules:

- PDF and CSV are file formats, not separate business source types.
- `file_format` must be NULL unless `source_type = FILE`.
- `provider_code`, `provider_connection_id`, and `account_reference` are nullable.
- FILE intake therefore does not require a provider account, API connection, or transponder.
- `provider_connection_id` has no FK yet because no Toll provider-connections table exists in Segment 1.
- `source_hash` is indexed by tenant but is **not unique**.
- `source_import_ref` is indexed by tenant but is **not unique**.
- Duplicate file detection/reprocessing policy belongs to later FILE intake logic, not a permanent database uniqueness rule.
- Default batch status is `RECEIVED`.

### Implemented table: toll_transactions

Canonical Toll rows intentionally remain small.

Identity model:

```text
TruckERP canonical identity:
  tenant_id + id

provider identity:
  provider_transaction_id
  nullable
  not PK
  not globally unique

source-row identity:
  tenant_id + batch_id + source_row_order
  optional source_row_id
```

The schema deliberately does **not** make any of the following unique:

```text
date + unit
datetime + unit
date + device
hour + unit
```

Multiple legitimate Toll events for the same unit within minutes are structurally allowed.

### Vehicle/unit fields

Implemented:

- nullable `truck_id`
- `unit_number_snapshot`
- tenant-safe FK `(tenant_id, truck_id) -> trucks(tenant_id, id)`
- FK delete behavior: `RESTRICT`

No Driver, Owner Operator, payee, payroll, settlement, or financial-responsibility linkage exists in Toll Segment 1.

### Canonical transaction fields

Segment 1 includes the small working Toll record needed by TruckERP, including:

- provider transaction identity
- source-row identity
- source transaction datetime text/provenance
- transaction date/datetime
- vehicle/unit link and unit snapshot
- toll agency code/name
- amount
- currency
- transaction type
- read type
- device/transponder identifier field
- plate number/state
- dispute status
- full `provider_raw` JSONB source evidence
- audit timestamps

The complete provider/file row remains in `provider_raw`; provider-specific fields such as plaza detail, toll class, billing authority, PrePass device ID, account names, dispute reason, etc. are not all promoted to canonical columns.

### Money

`amount` is:

```text
NUMERIC(14,4)
NOT NULL
```

No float money semantics are used.

Fuel-specific quantity/unit-price/tax/O-O pricing/settlement fields are absent.

### Transaction and read types

Initial canonical transaction type is limited to:

```text
NORMAL
VIOLATION
```

No unconfirmed refund/reversal/void enum was invented.

`read_type` is nullable and supports:

```text
DEVICE
PLATE
```

A separate display `identifier` column was intentionally **not stored**.

Future UI derives it:

```text
DEVICE -> device_number
PLATE  -> plate_number + plate_state
```

### Pull-query indexes

Segment 1 includes indexes supporting the future downstream pull model, including queries around:

- tenant + transaction date
- tenant + truck + transaction datetime
- tenant + unit-number snapshot + transaction datetime
- tenant + batch
- tenant + source hash
- tenant + source import reference

This supports the locked downstream use case:

```text
give me all tolls for unit 1104
from Monday through Sunday
```

without adding Payroll/O-O/Settlement responsibility to the Toll schema.

### Segment 1 tests

`tests/test_toll_segment_1.py`:

**13 passed**

The tests lock:

- canonical/provider/source-row identity separation
- date/unit/device are not uniqueness keys
- downstream pull indexes
- API / FILE / MANUAL source types
- PDF / CSV as FILE formats
- non-unique indexed source hash
- non-unique indexed source import reference
- `NUMERIC(14,4)` amount
- NORMAL / VIOLATION
- nullable DEVICE / PLATE
- no stored display identifier
- tenant-safe Truck FK
- required JSONB object source evidence
- absence of Driver/O-O/Payroll/Settlement fields
- no Toll provider-connection FK in Segment 1

### Explicitly deferred

Not implemented in Segment 1:

- CSV parsing
- PDF parsing
- PrePass API
- Toll provider connections
- frontend/history UI
- email intake
- manual-entry UI
- scheduler
- payroll/settlement
- Fuel-to-Toll copy/push

---

# Appendix A — PrePass Source Contract Archive

This appendix preserves the API contract details supplied during research so the TruckERP design does not depend on chat memory.

**Source files supplied:**
- `get-api-token-v1.json` — Token API v1
- `prepassapim-account-api-v1.json` — Account API v1
- `prepass-public-tolls-transactions-api-v1.json` — Toll Transaction API v1
- `prepassapim-fleetmgmt-v2.json` — Fleet Management API v2
- `prepassapim-tollsapi-v2.json` — GPS Data API v2
- Earlier pasted PrePass Toll Transaction API documentation text
- PrePass Plus capability statement and coverage image reference

No secrets, real credentials, or full sample bearer-token values should ever be copied into this document.

---

## A1. Token API v1 — Complete preserved contract

### Metadata

```text
OpenAPI: 3.0.1
Title: Token API
Version: v1
Description: Obtain a security token for API access using your client ID and secret.
Server: https://api.prepass.com/auth/v1
```

### Endpoint

```http
POST /token
```

Full URL:

```text
https://api.prepass.com/auth/v1/token
```

### Required request headers

| Name | Location | Required | Description |
|---|---|---:|---|
| `client_id` | header | Yes | Client ID provided by PrePass |
| `client_secret` | header | Yes | Client Secret provided by PrePass |

### 200 response

Content type: `application/json`

| Field | Type | Description |
|---|---|---|
| `token_type` | string | Type of token issued |
| `expires_in` | integer | Token lifetime in seconds |
| `ext_expires_in` | integer | Extended lifetime |
| `access_token` | string | Bearer access token |

Documented example values:

```json
{
  "token_type": "Bearer",
  "expires_in": 3599,
  "ext_expires_in": 3599,
  "access_token": "<redacted sample bearer token>"
}
```

### Errors

**400**
- Example error: `invalid_request`
- Example meaning: required client information missing.
- Provider example references Microsoft/Azure AD error code `900144`.

**401**
- Example error: `invalid_client`
- Example meaning: invalid client secret.
- Provider example references Microsoft/Azure AD error code `7000215`.

### TruckERP preservation rule

Persist:
- `client_id`
- `client_secret_ref`
- token expiry metadata if needed

Do not persist:
- raw client secret
- full sample tokens
- long-lived raw access tokens in ordinary config tables

---

## A2. Account API v1 — Complete preserved contract

### Metadata

```text
OpenAPI: 3.0.1
Title: Account API
Version: v1
Description: Returns all accounts associated with the authenticated user, including detailed information for each account.
Server: https://api.prepass.com/accounts/v1
```

### Endpoint

```http
GET /accounts
```

Full URL:

```text
https://api.prepass.com/accounts/v1/accounts
```

### Security declared by OpenAPI

Header option:

```text
Ocp-Apim-Subscription-Key: <subscription key>
```

Query option:

```text
?subscription-key=<subscription key>
```

TruckERP preference: header form.

### 200 response — GetAccountsResponse

| Field | Required | Type | Description |
|---|---:|---|---|
| `status` | No | string | API request status |
| `message` | No | string | API request status message |
| `accounts[].accountNumber` | Yes | string | PrePass account number tied to API credentials |
| `accounts[].accountName` | Yes | string | Account name in PrePass systems |
| `accounts[].costCenter` | No | string | Customer-defined organization/location/expense-center code |
| `accounts[].accountStatus` | Yes | string | `Active`, `Inactive`, or `Archived` |

Example shape:

```json
{
  "status": "success",
  "message": "Accounts retrieved successfully.",
  "accounts": [
    {
      "accountNumber": "123123",
      "accountName": "Location Name 123123",
      "costCenter": "0202001",
      "accountStatus": "Active"
    },
    {
      "accountNumber": "123124",
      "accountName": "Location Name 123124",
      "costCenter": "0203001",
      "accountStatus": "Inactive"
    },
    {
      "accountNumber": "123125",
      "accountName": "Location Name 123125",
      "costCenter": "0204001",
      "accountStatus": "Archived"
    }
  ]
}
```

### Other responses

- `400 Bad Request`
- `403 Forbidden`
- `404 Not Found`
- `500 Internal Server Error`

### Important account rules

- One authenticated user/credential set may see multiple accounts.
- `costCenter` is optional.
- Historical inactive/archived accounts must remain addressable for old toll records.
- Do not equate PrePass account or cost center directly with TruckERP tenant/company/terminal without an explicit mapping.

---

## A3. Toll Transaction API v1 — Complete preserved contract

### Metadata

```text
OpenAPI: 3.0.1
Title: Toll Transaction API
Version: v1
Description: Get Toll Transaction Details
Server: https://api.prepass.com/tolltransaction/v1
```

### Endpoint

```http
GET /transactions
```

Full URL:

```text
https://api.prepass.com/tolltransaction/v1/transactions
```

### Request parameters

| Name | Location | Required | Provider type | Description / constraint |
|---|---|---:|---|---|
| `startPostDate` | query | Yes | DateTime | `yyyy-mm-dd`; cannot be more than 2 years old; starts at 12:00 AM |
| `endPostDate` | query | Yes | DateTime | `yyyy-mm-dd`; range cannot exceed 31 days; for one day use following day as end date |
| `accountNumbers` | query | Conditional | Integer in this API | One or multiple account numbers, comma-separated; parent account includes child account data |
| `costCenters` | query | Conditional | String | One or multiple cost-center codes, comma-separated |
| `pageNumber` | query | No | Integer | Default 1; max 2147483647 |
| `pageSize` | query | No | Integer | Default 10000; max 10000 |

Filter rule:
- At least one of `accountNumbers` or `costCenters` is required.
- Do not send both in the same request.

Example URL pattern:

```text
/transactions?startPostDate={startPostDate}&endPostDate={endPostDate}&accountNumbers=...&pageNumber=1&pageSize=10000
```

or:

```text
/transactions?startPostDate={startPostDate}&endPostDate={endPostDate}&costCenters=...&pageNumber=1&pageSize=10000
```

### 200 response top-level fields

| Field | Required | Type | Description |
|---|---:|---|---|
| `statusCode` | Yes | integer | HTTP status code |
| `statusMessage` | Yes | string | Status message |
| `pageInfo.pageNumber` | Yes | integer | Current page number |
| `pageInfo.pageSize` | Yes | integer | Records per page |
| `pageInfo.totalRecords` | Yes | integer | Total matching records |
| `pageInfo.totalPages` | Yes | integer | Total pages |
| `transactions` | No at top schema level | array | List of toll transactions |

### Transaction fields

| Field | Required by schema | Type declared | Meaning |
|---|---:|---|---|
| `tollId` | Yes | string | PrePass unique toll transaction identifier |
| `accountNumber` | Yes | integer | Customer account number |
| `accountName` | Yes | string | Customer account name |
| `billToAccountNumber` | Yes | integer | Billing account number |
| `billToAccountName` | Yes | string | Billing account name |
| `postDateTime` | Yes | string | Transaction posted date/time |
| `invoiceDateTime` | Yes | string | Date/time of PrePass invoice when billed |
| `deviceNumber` | Yes | string | Transponder or sticker number |
| `vehicleNumber` | Yes | string | Customer unique vehicle identifier |
| `plateNumber` | Yes | string | License plate number |
| `plateState` | Yes | string | Plate state/jurisdiction |
| `ppDeviceId` | Yes | string | PrePass unique main device ID |
| `tollAgencyCode` | Yes | string | Toll authority abbreviation, e.g. NYSTA |
| `tollAgencyName` | Yes | string | Toll authority full name |
| `tollAgencyState` | No | string | Toll authority state |
| `billingAgencyCode` | Yes | string | Billing authority abbreviation |
| `entryDateTime` | Yes | string | Entry-point date/time for point-to-point toll |
| `entryDateTimeUtc` | No | string nullable | UTC version of entry date/time |
| `entryPlazaCode` | Yes | string | Entry plaza short description/code |
| `entryPlazaName` | Yes | string | Entry plaza full description |
| `readType` | Yes | string | Plate or Device |
| `exitDateTime` | Yes | string | Toll transaction local date/time |
| `exitDateTimeUtc` | No | string nullable | UTC version of exit date/time |
| `exitPlazaCode` | Yes | string | Exit plaza short description/code |
| `exitPlazaName` | Yes | string | Exit plaza full description |
| `tollClass` | Yes | string | Toll-agency pricing class |
| `tollCharge` | Yes | string declared | Total charges for transaction |
| `tollCategory` | Yes | string | `Normal` or `Violation` |
| `disputeStatus` | Yes | string | Dispute status, e.g. In Dispute, Closed/Complete |
| `disputeStatusReason` | Yes | string | Reason for dispute status |
| `deviceStatus` | Yes | string | Assigned or Unassigned |
| `costCenter` | No | string | Returned only when requesting by cost center |

### Provider example characteristics

Example transaction 1 shows:
- account `123456`
- vehicle `2000`
- device `00409740958`
- agency `OTC` / Ohio Turnpike Commission
- billing agency `EZPass`
- read type `DEVICE`
- exit plaza `239` / Eastgate
- toll class `5`
- toll charge `8.25`
- toll category `Normal`
- device status `assigned`
- cost center `1111`

Example transaction 2 shows:
- same vehicle/device
- entry plaza `161` / Strongsville-Cleveland
- exit plaza `211`
- toll charge `12`

### Schema inconsistencies that must be preserved as adapter knowledge

- `tollId` is declared **string** but examples show numeric JSON values.
- `tollCharge` is declared **string** but examples show numeric JSON values.
- Account API models `accountNumber` as string; Toll Transaction API models it as integer.
- Several required keys may have empty-string values.
- `entryDateTimeUtc` and `exitDateTimeUtc` may be null.
- `costCenter` is optional and only included when querying by cost center.

### Response codes

- `200` success
- `204` no content
- `400` bad request / validation error
- `401` unauthorized
- `403` forbidden
- `404` not found
- `500` server error

Example 400 validation:

```json
{
  "statusCode": 400,
  "statusMessage": "BadRequest",
  "validationErrors": [
    {
      "message": "StartPostDate must precede EndPostDate.",
      "members": ["StartPostDate", "EndPostDate"]
    }
  ]
}
```

### Canonical normalization rule

```text
provider_transaction_id = str(tollId)
account_number          = str(accountNumber)
bill_to_account_number  = str(billToAccountNumber)
toll_amount             = Decimal(str(tollCharge))
```

Always preserve full raw payload before normalization.

---

## A4. Fleet Management API v2 — Complete preserved contract

### Metadata

```text
OpenAPI: 3.0.1
Title: Fleet Management API
Version: v2
Description: Manage vehicles enrolled in bypass and/or tolling services. Add, update or delete vehicles. Assign or request transponders.
Server: https://api.prepass.com/fleetmanagement/v2
```

Provider restriction:
- Do not use this API to update tractors enrolled in Toll Violation Prevention Program (VPP).
- Do not use this API for trailer plates.

### A4.1 GET /vehicles

Purpose: query one vehicle by VIN or vehicle number, or multiple vehicles by account number/cost center.

Parameters:

| Name | Required | Type | Notes |
|---|---:|---|---|
| `costCenter` | Conditional | String | Either account number or cost center required |
| `accountNumber` | Conditional | String | Either account number or cost center required |
| `vin` | No | String | VIN lookup |
| `vehicleNumber` | No | String | Customer vehicle number; max length 8 |

Response fields:

| Field | Type | Notes |
|---|---|---|
| `accountNumber` | string | Assigned PrePass account |
| `costCenter` | string | Assigned customer organization/expense-center code |
| `vin` | string | VIN |
| `vehicleNumber` | string | Customer vehicle number, max 8 |
| `tempPlate` | boolean | Temporary plate flag |
| `licensePlateNumber` | string | Plate number |
| `licensePlateState` | string | State/province |
| `declaredWeight` | integer | 0–600,000 lb |
| `irpNumber` | string | IRP number |
| `irpState` | string | IRP jurisdiction |
| `iftaNumber` | string | IFTA number |
| `iftaState` | string | IFTA jurisdiction |
| `transponderNumber` | string | Assigned transponder |
| `vrn` | string | Vehicle Reference Number |
| `hazmatHauler` | boolean | Hazmat indicator |
| `vehicleImage` | string | Make/color/account text |
| `leasedVehicle` | boolean | Lease indicator |
| `leasingCompany` | string | Leasing company |
| `leaseExpirationDate` | string/date | Lease expiration |

### A4.2 POST /vehicle

Purpose: add vehicle.

Query:
- `accountNumber` or `costCenter`

Required request fields:
- `vin`
- `vehicleNumber`
- `declaredWeight`
- `licensePlate`
- `irp`
- `ifta`

Optional/conditional fields include:
- `vehicleColor`
- `transponderNumber`
- `vrn`
- `hazmatHauler`
- `leasedVehicle`

Important constraints:
- VIN length 16–19, alphanumeric.
- vehicle number length 1–8; pattern allows letters, digits, hyphen.
- permanent plate number length 5–9; uppercase alphanumeric/hyphen.
- plate state is 2-letter jurisdiction.
- declaredWeight integer.
- IRP account number length up to 10.
- IFTA account can be numeric with optional trailing letters per provider pattern.
- transponder number length 9–12 digits.
- vehicle color enum includes BLACK, BLUE, BROWN, GOLD, GRAY, GREEN, MAROON, ORANGE, PURPLE, RED, SILVER, TAN, YELLOW, WHITE.
- if leased vehicle object is passed, company + expiration are paired.
- known leasing-company enum includes Penske, Ryder, Budget, Other, Idealease, Enterprise, United, Paclease, NationaLease, TEC, Velocity.

The provider jurisdiction enums include U.S. states, Canadian provinces/territories, and additional Mexican/other jurisdiction codes.

### A4.3 PATCH /vehicle

Purpose: update vehicle.

Required query:
- `vin`

VIN cannot be changed.

Also requires current/target:
- `accountNumber` or `costCenter`

Provider notes:
- passing a different account/cost center can reassign the VIN to that account/cost center.

Updatable body can include:
- vehicle number
- plate
- declared weight
- IRP
- IFTA
- vehicle color
- transponder number
- VRN
- hazmat flag
- lease information

### A4.4 DELETE /vehicle

Purpose: remove a vehicle.

Required:
- `vin`
- account number or cost center

### A4.5 POST /orders

Purpose: order transponders for specified vehicles.

Provider behavior:
- PrePass assigns transponders to vehicles during fulfillment.
- UPS Ground is default.
- expedited shipping requires contacting PrePass.

Required request fields:
- `vehicles` — list of VINs
- `shippingContactName`
- `shippingContactEmail`
- `shippingStreet1`
- `shippingCity`
- `shippingState`
- `shippingPostalCode`

Other fields:
- `vrn`
- `shippingInstructions`
- `shippingStreet2`

Important:
- VINs must belong to requested account/cost center.
- VINs already having a device are excluded.
- VRN is required for PrePass Plus or tolling-only vehicles.

### A4.6 GET /transponder

Purpose: lookup one transponder.

Required:
- `transponderNumber`

Also account number or cost center.

Response:
- `accountNumber`
- `vin`
- `vehicleNumber`
- `vrn`
- `transponderNumber`
- `costCenter`

Responses include:
- 200
- 204
- 400
- 403
- 500

### A4.7 GET /transponders

Purpose: list transponders by account or cost center.

Response records contain:
- account number
- VIN
- vehicle number
- VRN
- transponder number
- cost center

Provider example explicitly includes an unassigned transponder with blank VIN and vehicle number.

### A4.8 POST /transponders/lost

Purpose: report lost or stolen transponders.

Request fields:
- `transponders[]` — required list of transponder numbers
- `reportedBy` — required reporter name

### A4.9 GET /health

Purpose: check Fleet Management supporting services.

Responses:
- `200` Healthy or Degraded
- `503` unavailable

### A4.10 Deprecated GET /accounts

Fleet Management v2 includes an old `/accounts` endpoint, but PrePass explicitly marks it deprecated and directs integrations to Account API v1.

Do not build against the deprecated Fleet Management accounts endpoint.

### TruckERP fleet-reference rule

Use Fleet Management as provider reference data:

```text
VIN
vehicleNumber
plate + jurisdiction
transponderNumber
accountNumber
costCenter
```

Do not silently overwrite TruckERP canonical asset/compliance records with PrePass values.

---

## A5. GPS Data API v2 — Complete preserved contract

### Metadata

```text
OpenAPI: 3.0.1
Title: GPS Data API
Version: v2
Description: Allows carriers to share truck-trip GPS data with PrePass for tolls validation.
Server: https://api.prepass.com/api/tolls/gps/v2
```

### Endpoint

```http
POST /gpsevents
```

Required query:

| Name | Required | Type | Description |
|---|---:|---|---|
| `accountNumber` | Yes | Integer | PrePass account number |

Full URL pattern:

```text
https://api.prepass.com/api/tolls/gps/v2/gpsevents?accountNumber={accountNumber}
```

### Request body — TollValidationRequest

Top-level:

| Field | Type | Nullable |
|---|---|---:|
| `postedTime` | int64 | Yes |
| `vehicles` | array | Yes |

Each `CustomerVehicle`:

| Field | Type | Nullable |
|---|---|---:|
| `deviceNumber` | string | Yes |
| `vin` | string | Yes |
| `totalAxleCount` | int32 | Yes |
| `plateNumber` | string | Yes |
| `plateState` | string | Yes |
| `trackSegment` | array of GpsLocation | Yes |

Each `GpsLocation`:

| Field | Type | Nullable |
|---|---|---:|
| `latitude` | double | Yes |
| `longitude` | double | Yes |
| `timestamp` | int64 | Yes |
| `timezone` | int32 | Yes |
| `speed` | float | Yes |
| `direction` | float | Yes |
| `locationAccuracy` | float | Yes |

Representative shape:

```json
{
  "postedTime": 0,
  "vehicles": [
    {
      "deviceNumber": "string",
      "vin": "string",
      "totalAxleCount": 0,
      "plateNumber": "string",
      "plateState": "string",
      "trackSegment": [
        {
          "latitude": 0,
          "longitude": 0,
          "timestamp": 0,
          "timezone": 0,
          "speed": 0,
          "direction": 0,
          "locationAccuracy": 0
        }
      ]
    }
  ]
}
```

### Responses

**200**
- Content type `text/plain`
- Example: `GPS Data processed successfully`

**400**
- Content type `application/json`
- Can include:
  - `errorMessages[]`
  - `invalidEntries[]`
  - each invalid entry identifies a vehicle index
  - each invalid vehicle entry can contain `invalidGpsLocationEntries[]`
  - each invalid GPS entry identifies `gpsEntry` index and its errors

**401**
- unauthorized

**500**
- server error

### TruckERP GPS rule

This remains optional/future:
- toll import must work without GPS API
- GPS submission may later support toll validation, dispute investigation, axle-class checks, and identity confirmation
- minimize GPS retention/logging because this is sensitive location history

---

## A6. PrePass Plus capability statement preserved

Provider statement supplied during research:

> **In addition to weigh station bypassing, PrePass Plus takes the hassle out of tolls by enabling fleets to pay tolls, handle violations and toll disputes through a single transponder, and receive a consolidated bill from one service provider.**

Coverage image reference supplied:

```text
https://enrollment.prepass.com/images/Expanded_Legend.png
```

Confirmed business capabilities to preserve in design:
- toll payment
- violations
- toll disputes
- single-transponder operation
- consolidated billing
- weigh-station bypass is a separate PrePass capability but is not part of the initial TruckERP Tolls accounting workflow

---

## A7. Integration facts now considered locked from supplied documentation

1. PrePass has separate Token, Account, Fleet Management, Toll Transaction, and GPS Data APIs.
2. Token API uses `client_id` and `client_secret` headers and returns a Bearer token.
3. Account API v1 declares an APIM subscription key security scheme.
4. Account API can return multiple accounts for one authenticated integration.
5. Toll Transaction API supports account-number or cost-center filtering and pagination.
6. Toll Transaction query windows are max 31 days; start date max age is 2 years.
7. Toll Transaction max page size is 10,000.
8. `tollId` is the provider transaction identity.
9. Transactions expose underlying toll agency and separate billing-agency code.
10. Transactions expose vehicle number, plate, device number, PrePass device ID, device status, and read type.
11. Transactions expose Normal vs Violation and dispute status/reason.
12. Fleet Management gives direct VIN ↔ vehicle number ↔ plate ↔ transponder relationships.
13. Fleet Management supports unassigned transponders.
14. Fleet Management can add/update/delete vehicles, order transponders, and report lost/stolen transponders.
15. Fleet Management writes should remain disabled in TruckERP initial implementation.
16. GPS Data API is outbound carrier-to-PrePass data for toll validation.
17. Initial TruckERP Tolls implementation must not depend on GPS.
18. Raw provider JSON should be retained before normalization.
19. Provider type inconsistencies must be normalized defensively.
20. PrePass provider reference data must not silently replace TruckERP canonical asset/compliance history.

---

## A8. Items still not confirmed by supplied documentation

Keep these as research/open items rather than assumptions:

- exact security combination required by every non-Account PrePass API call
- rate limits
- whether dispute creation/update is available by API
- whether a separate invoice/statement API exists
- whether historical transponder assignment events are available, versus only current state
- separate discount amount
- separate admin fee
- separate violation fee
- transaction currency
- explicit invoice number/statement number
- complete Canada toll-network coverage
- how PrePass represents reversals/voids/adjustments, if exposed separately

---

## A9. Implementation reminder for future sessions

Before changing Tolls code:

1. Read this entire MD.
2. Treat the Appendix source contract as authoritative for the PrePass details supplied so far.
3. Do not recreate provider field names from memory.
4. Do not assume a missing field exists.
5. Preserve raw provider payloads.
6. Normalize provider IDs to strings internally where schemas disagree.
7. Use Decimal for monetary normalization.
8. Keep processed toll history auditable and immutable.
9. Never silently remap an ambiguous toll transaction to a truck/owner.
10. Add new provider documentation here before implementing behavior that depends on it.

## 10. Decision Log

### 2026-10-04 — Tolls documentation started

- Created a dedicated TruckERP Tolls working specification.
- PrePass / PrePass Plus is the first provider/aggregator to research.
- First confirmed functional scope from PrePass:
  - toll payment
  - violation handling
  - toll disputes
  - single-transponder operation
  - consolidated billing
- No permanent toll schema is locked yet.

### 2026-10-04 — PrePass Account API v1 documented

- Confirmed account discovery endpoint: `GET https://api.prepass.com/accounts/v1/accounts`.
- Confirmed one authenticated integration may return multiple PrePass accounts.
- Confirmed account states include `Active`, `Inactive`, and `Archived`.
- TruckERP will preserve provider account identity and historical inactive/archived accounts rather than treating PrePass as a single-account integration.

### 2026-10-05 — PrePass Account API security clarified

- OpenAPI 3.0.1 declares `Ocp-Apim-Subscription-Key` header security or `subscription-key` query security for Account API v1.
- TruckERP should prefer the header form.
- The PrePass provider connection therefore needs a separate `subscription_key_ref` in addition to `client_secret_ref`.
- Do not assume every PrePass endpoint uses an identical security combination; follow each API contract.

### 2026-10-05 — PrePass Token API v1 documented

- Confirmed token endpoint: `POST https://api.prepass.com/auth/v1/token`.
- Confirmed `client_id` and `client_secret` are required request headers.
- Confirmed Bearer token response.
- Confirmed documented token lifetime example of 3599 seconds.
- Connection test should authenticate and then call Account API v1.
- Raw Bearer tokens should remain ephemeral rather than being stored as normal persistent provider configuration.


### 2026-10-05 — PrePass Fleet Management API v2 documented

- Confirmed vehicle lookup by VIN, vehicle number, account number, or cost center.
- Confirmed vehicle response ties together VIN, unit/vehicle number, plate, transponder, account, IRP, IFTA, lease, weight and other provider metadata.
- Confirmed direct transponder lookup and list endpoints.
- Confirmed transponders can exist without assigned VIN/vehicle number.
- Confirmed vehicle add/update/delete, transponder ordering, and lost/stolen reporting APIs exist.
- Initial TruckERP integration should remain read/sync-first; provider write actions require a separate later decision.
- Deprecated Fleet Management `/accounts` endpoint should not be used; Account API v1 is the current source.


### 2026-10-05 — PrePass GPS Data API v2 documented

- Confirmed GPS submission endpoint: `POST https://api.prepass.com/api/tolls/gps/v2/gpsevents`.
- Confirmed required PrePass account-number query parameter.
- Confirmed payload can carry device number, VIN, axle count, plate, and GPS track segments.
- Confirmed GPS points support latitude, longitude, timestamp, timezone, speed, direction, and location accuracy.
- Classified this API as future toll-validation/ELD integration, not a dependency for initial toll ingestion.


### 2026-10-05 — Vehicle-boundary rule locked

- Tolls stops at vehicle/unit attribution.
- A toll mapped to unit 1104 remains a vehicle toll regardless of whether the truck is company-owned or owner-operator-owned.
- Company/O-O ownership, driver responsibility, payroll deductions, settlement treatment, and expense responsibility are downstream concerns.
- Do not couple Tolls normalization to Payroll, Driver, Owner-Operator, or Settlement logic.


### 2026-10-05 — Multiple-toll event rule locked

- One unit/device may have multiple valid tolls within the same hour.
- Date + unit/device is a display/grouping key, not a deduplication key.
- PrePass `tollId` is the provider transaction identity.
- History should retain every event and sort by transaction date/time, then unit, then read source/identifier.
- Expanded details can show plaza and timing data to distinguish nearby toll events.


### 2026-10-05 — Pull-based toll consumption locked

- Tolls is a vehicle-linked transaction store and query source.
- Most tolls do not require item-by-item operational review.
- Admin receives a simple history/search view with expandable provider detail.
- Payroll and other downstream modules query tolls by unit + date range.
- Example: unit 1104, Monday through Sunday.
- Tolls does not push owner-operator, payroll, settlement, or expense actions downstream.
- Downstream modules decide financial responsibility after pulling the relevant vehicle tolls.


### 2026-10-05 — PDF/no-account toll intake locked

- File intake is a first-class Toll source alongside API and manual entry.
- File intake includes PDF and CSV.
- E-ZPass portal CSV downloads are explicitly supported as a normal Toll source.
- A toll can exist without provider credentials, account number, or transponder.
- Emailed/downloaded toll bills and missing tolls can be uploaded by admin.
- Toll PDF uses the shared Document Platform with an explicit Toll profile; CSV uses a Toll CSV adapter/profile.
- File and API sources must coexist without blindly duplicating overlapping transactions.
- Original uploaded file/raw evidence must be retained.


### 2026-10-05 — Toll file-source rule clarified

- PDF and CSV are not separate business-source categories; both are FILE intake.
- E-ZPass portal CSV is a normal Toll source for fleets that do not use a direct API integration.
- Source architecture is API / FILE / MANUAL, with file format handled inside FILE intake.


### 2026-10-05 — Tolls Segment 1 canonical schema implemented

- Local-main implementation commit: `a5a2f13`.
- Added `toll_source_batches` and `toll_transactions`.
- Migration revision `t1a2b3c4d5e6` revises `m7n8o9p0q1r2` and leaves one tenant Alembic head.
- Source hash and source import reference are indexed but deliberately not unique.
- Toll canonical records remain vehicle/unit-bound and contain no Driver/O-O/Payroll/Settlement logic.
- 13 Segment 1 tests passed.
- At this checkpoint the migration had not been applied and the API had not been reloaded/deployed.
