# Fuel Gold manifest

**Not established.** There is no `gold/fuel` branch and no `fuel-gold-*` tag yet.

When Fuel is frozen the same way as DL:

1. Create branch `gold/fuel` at the verified commit.
2. Create immutable tag `fuel-gold-YYYY-MM-DD` at that commit.
3. Replace this file with the gold SHA, baked image (if any), dependent files, and parked bugs.
4. Add the row to [GOLD_MODULES.md](./GOLD_MODULES.md).

Do not store Fuel files on `gold/dl` or in `DL_GOLD_MANIFEST.md`.

---

## Discussion / future design notes

These notes are parked here so Fuel/BVD design does not accidentally assume that every card transaction is fuel. They are **discussion only** and are not an implementation contract yet.

### Fuel-card / BVD transaction classification

A fuel card is a payment source, not a guarantee that the transaction is a fuel purchase. The future Fuel/Card ingestion model must be able to represent non-fuel activity such as:

- fuel / diesel
- DEF
- scale fees
- lumper fees
- cash advances
- additional products / truck-stop purchases
- parking
- tolls
- repair/service purchases
- other / review-required transactions

The exact enum/schema is intentionally not locked yet.

### Lumper fee boundary with Dispatch / Loads

Lumper handling is primarily a **Dispatch / Load workflow**, not a Fuel-module responsibility.

Normal operational path:

```text
Driver is on a load / trip
  -> driver pays lumper (often personally or by another payment method)
  -> driver uploads the lumper receipt to Dispatch
  -> Dispatch reviews the receipt
  -> Dispatch attaches the receipt / charge to the correct Load
  -> carrier-paid amount is visible on that Load
  -> if broker reimbursement is expected, the Load/accounting workflow tracks that amount as recoverable from the broker
```

A lumper fee may occasionally appear on a BVD/fuel-card transaction feed. When that happens, the future Fuel/Card module should **surface/suggest** the transaction for reconciliation with Dispatch/Load rather than owning the complete lumper workflow.

Important boundary:

- Fuel/Card module: ingest/classify the card transaction and expose a possible lumper match.
- Dispatch/Load: determine the correct load, attach/review the receipt, and own the operational load association.
- Accounting/receivables: track broker reimbursement where applicable.

Do not silently auto-link a lumper transaction to a load merely because the driver/card holder had an active trip. A driver may have multiple loads/stops; matching can use driver, trip, transaction time, location, and receipt context, but ambiguous cases require Dispatch review.

This cross-module workflow is intentionally deferred. See [`docs/ToDo/README.md`](./ToDo/README.md) for the parked implementation item.
