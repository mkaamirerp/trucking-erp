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

Recommended connection flow:

```text
client_id + client_secret_ref
        ↓
POST /auth/v1/token
        ↓
Bearer access_token
        ↓
GET /accounts/v1/accounts
        ↓
confirm authorized PrePass accounts
        ↓
connection test = OK
```

Important rules:

- Store the client secret only through TruckERP's credential/secret reference mechanism.
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

## 6. Design Principles

- Provider data is source data; TruckERP owns the canonical business model.
- Raw provider values must be retained for audit/reprocessing.
- Money must reconcile before permanent processing.
- No silent guessing for vehicle/unit/owner mappings.
- Processed financial history should be immutable except through controlled correction/adjustment workflows.
- Asset/unit ownership and assignment must be resolved using historical effective dates, not only the current truck/driver relationship.
- Toll charges, violations, fees, discounts, reversals, and adjustments must remain distinguishable if the source exposes them.

---

## 7. Open Research Items

- Whether disputes can be created/updated through API or are portal-only.
- Whether consolidated invoice/statement identifiers are available from another PrePass API.
- Whether PrePass exposes transponder-to-vehicle assignment history through Fleet Management API.
- Coverage gaps that would require direct E-ZPass/agency imports.
- Canada toll coverage and currency behavior.
- Any PrePass API rate limits not shown in the supplied specifications.

---

## 8. Decision Log

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

### 2026-10-05 — PrePass Token API v1 documented

- Confirmed token endpoint: `POST https://api.prepass.com/auth/v1/token`.
- Confirmed `client_id` and `client_secret` are required request headers.
- Confirmed Bearer token response.
- Confirmed documented token lifetime example of 3599 seconds.
- Connection test should authenticate and then call Account API v1.
- Raw Bearer tokens should remain ephemeral rather than being stored as normal persistent provider configuration.
