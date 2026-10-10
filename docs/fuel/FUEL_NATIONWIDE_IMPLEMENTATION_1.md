# Nationwide Fuel Implementation 1

Authoritative record for Nationwide **persistence + Process** (parse-only proof remains in commits `598ee81c` / `64cbd495`).

## Fixture

- PDF: `docs/fixtures/fuel/nationwide_fuel.pdf`
- Profile: `NATIONWIDE` / `2026-09-19` in `app/contracts/fuel_provider_profiles.json`

## Provider-native transaction fields

Account Code, Card Number, Unit #, Date, City, Pr/St, Product, Volume, Ex-GST ($/U), Total, Network, Currency, USA Discount, Missed Disc, OON Fees.

No Driver, Auth Code, Site #, BVD Express fields.

## Flow

```
PDF → generic Nationwide parser → fuel_nationwide_* staging
  → review / corrections → reconcile_nationwide_source_rows
  → Process (atomic) → fuel_nationwide + fuel_source_batches (FINALIZED)
  → fuel_source_controls + fuel_transactions (12 purchases only)
  → existing classification backfill
```

## Accepted source

`build_effective_nationwide_rows` = parsed value + latest approved correction overlay. Process uses **one** accepted dataset for reconciliation, permanent source, controls, and canonical projection.

## USD math (two facts)

| Fact | Value |
|------|-------|
| Sum of printed row `Total` (USD) | 5197.67 |
| ROUND(SUM(volume × Ex-GST ($/U)), 2) | 5197.69 |
| Provider USD billing control | 5197.69 |

The **0.02** gap between row totals and billing control is retained source evidence; reconciliation uses precision extension, not row-total rewrite.

## CAD math

- ROUND(674.17 × 1.659, 2) = **1118.45** ↔ Total Ex-GST & PST control
- GST **145.40**, PST **0.00**, Subtotal **1263.85**
- Row-level GST is **not** invented on the single CAD transaction.

## Controls vs transactions

Controls (CARD_TOTAL, CURRENCY_TOTAL, TAX_CONTROL, etc.) persist as `fuel_nationwide` CONTROL rows and `fuel_source_controls` — never as canonical purchases.

## Canonical mapping

Printed row `Total` → `fuel_transactions.total_amount` exactly. `quantity × unit_price` is for reconciliation only.

## Tables

- `fuel_nationwide`, `fuel_nationwide_field_correction`
- `fuel_nationwide_import_stage`, `fuel_nationwide_stage_row`, `fuel_nationwide_stage_field_correction`

## Tests

- `tests/test_fuel_nationwide_source_reconciliation.py`
- `tests/test_fuel_nationwide_process_integration.py`
- `tests/test_fuel_nationwide_parse_preview.py`

See existing Fuel architecture docs for shared batch/canonical/classification behavior.
