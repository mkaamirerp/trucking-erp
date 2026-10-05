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

## 4. PrePass API Research Checklist

Before coding a PrePass adapter, obtain and inspect the official Toll Transaction API documentation / OpenAPI / Swagger / sample response.

Confirm:

- authentication flow
- client ID / client secret requirements
- account identifier requirements
- endpoint URL and HTTP method
- date-range filtering
- pagination
- rate limits
- transaction identifiers
- transaction date/time
- posting date
- toll authority
- facility / road
- plaza / gantry
- entry / exit location
- transponder identifier
- vehicle identifier
- unit number
- VIN
- plate number / plate state
- axle information
- toll amount
- discounts
- fees
- violation amount/type
- total amount
- currency
- invoice / statement identifiers
- dispute information, if exposed
- voids / reversals / adjustments
- raw response retention requirements

**Do not lock the canonical toll schema until this API contract is reviewed.**

---

## 5. Design Principles

- Provider data is source data; TruckERP owns the canonical business model.
- Raw provider values must be retained for audit/reprocessing.
- Money must reconcile before permanent processing.
- No silent guessing for vehicle/unit/owner mappings.
- Processed financial history should be immutable except through controlled correction/adjustment workflows.
- Asset/unit ownership and assignment must be resolved using historical effective dates, not only the current truck/driver relationship.
- Toll charges, violations, fees, discounts, reversals, and adjustments must remain distinguishable if the source exposes them.

---

## 6. Open Research Items

- Exact PrePass Toll Transaction API v1 request/response schema.
- Whether PrePass API exposes underlying toll authority on every transaction.
- Whether violations are included in Toll Transaction API or a separate API.
- Whether disputes can be created/updated through API or are portal-only.
- Whether consolidated invoice/statement identifiers are returned by API.
- Whether PrePass exposes transponder-to-vehicle assignment history.
- Coverage gaps that would require direct E-ZPass/agency imports.
- Canada toll coverage and currency behavior.

---

## 7. Decision Log

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
