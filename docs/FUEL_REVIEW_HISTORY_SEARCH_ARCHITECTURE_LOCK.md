# Fuel — Review / History Search Architecture (LOCKED)

**Status:** LOCKED — recovered onto `feat/fuel-card` (2026-09-30)  
**Scope:** Defines **two separate** Fuel search experiences. Do not merge them.

**Related (current, authoritative where newer):**

- `docs/FUEL_BVD_IMPLEMENTATION_1.md` — BVD processed record, source money display
- `docs/settlements/FUEL_SETTLEMENT_HANDOFF.md` — Settlement consumption UI rules (future)

---

## A. Processed record search (THIS PHASE — implement per milestone)

**Where:** One opened provider invoice/statement — full processed/read-only record (`FuelBvdProcessedRecordView` / `BvdParsedStatementView` with `presentation=full-stored-detail`).

**Route (current):** `/fuel/bvd/{import_id}/detail` and Fuel home overlay (“Open full invoice”).

**Data:** `GET /fuel/bvd/imports/{import_id}/rows` — permanent `fuel_bvd` rows with effective values (`operationalCell`). **Not** staging.

**Filtering:** Client-side on the already-loaded statement rows (purchases + express transaction sections). View-only; no mutation.

### Search box

Label: **Search this statement**

Applies only to transactions belonging to the **currently opened** import/invoice.

### Searchable concepts (provider-neutral)

| Concept | Typical BVD source fields (effective) |
|---------|----------------------------------------|
| Unit | `unit_number`, `express_tractor` |
| Driver | `driver_name` |
| Card / Account | `card_number` (row + header) |
| Auth / provider transaction identity | `auth_code` |
| Provider reference | `express_code`, `site_number` |
| Product | `prod`, `product`, `legend_product_name` |
| Category | `prod` / `product` / `row_label`; canonical `classification` when linked via existing canonical-transactions API |
| Provider reason | `payee_raw`, `notes_raw`; canonical `provider_reason_raw` when linked |
| Amount | `final_amt`, `final_amount`, `amount_cashed`, `pre_tax_amt` (displayed accepted money) |
| Date | `transaction_date` (accepted timestamp) |

Matching: case-insensitive substring; identifiers as text (preserve leading zeros); trim query whitespace.

### Date period (same statement)

Control: **Date period** with:

- **All transactions** (default)
- Month groups present in statement data, with **month-relative calendar weeks** (not ISO weeks):
  - Week 1 = days 1–7
  - Week 2 = days 8–14
  - Week 3 = days 15–21
  - Week 4 = days 22–28
  - Week 5 = days 29 through actual month end (leap years use real calendar math)
- **Custom dates** (`date_from` / `date_to`, inclusive)

Provider statement period (e.g. BVD Dec 10–Dec 16 on the invoice header) is **evidence** — not the same as calendar-week filters. Calendar weeks filter **transaction date** only.

Search + date filter **combine**. Default: empty search, all transactions, provider/source row order unchanged.

### Result count

Show filtered count, e.g. `7 of 31 transactions`.

---

## B. Global Fuel History (NOT THIS PHASE)

Server-side search/pagination over canonical `fuel_transactions` across providers, WHO/WHEN/SOURCE/DOWNSTREAM, settlement-number search, global totals, CSV export, indexes.

**Do not implement** Global Fuel History in the processed-record milestone.

---

## Payroll / Settlement linkage

Settlement status on Fuel history rows is defined in `docs/settlements/FUEL_SETTLEMENT_HANDOFF.md` (Pending / ✓ SET-####). See also `docs/PAYROLL_OO_FUEL_SETTLEMENT_LINKAGE.md` for boundary reference only.
