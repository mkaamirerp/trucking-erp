# Fuel Gold manifest

**Not established.** There is no `gold/fuel` branch and no `fuel-gold-*` tag yet.

When Fuel is frozen the same way as DL:

1. Create branch `gold/fuel` at the verified commit.
2. Create immutable tag `fuel-gold-YYYY-MM-DD` at that commit.
3. Replace this file with the gold SHA, baked image (if any), dependent files, and parked bugs.
4. Add the row to [GOLD_MODULES.md](./GOLD_MODULES.md).

Do not store Fuel files on `gold/dl` or in `DL_GOLD_MANIFEST.md`.

---

## Future Gold-readiness checklist (reference only)

Fuel Gold is **not established**. Do **not** create branch `gold/fuel` or tag `fuel-gold-*` from this documentation update.

When Fuel later approaches Gold, these architecture locks from `FUEL_CARD_MODULE_DESIGN.md` / `FUEL_CARD_IMPLEMENTATION_PLAN.md` must already be proven in tests and code. This list is a readiness reference, not a freeze and not an implementation contract by itself.

1. **Decimal / money precision** — `NUMERIC`/`Decimal` only; locked scales for quantity, unit price, discount rate/amount, tax amounts, transaction totals, and owner-operator charges; rounding only at documented boundaries.
2. **Three transaction identities** — provider transaction identity, provider source-row identity, and TruckERP canonical identity remain separate; provider auth numbers are not the canonical PK.
3. **Effective-dated card/account assignment** — resolution at transaction datetime; later card moves do not rewrite historical ownership/responsibility.
4. **Extraction correction vs provider amendment** — human pre-finalization review is distinct from provider-issued credit/refund/reversal/void/corrected transactions.
5. **Downstream routing acknowledgement** — Toll/Lumper/other classification is incomplete until the downstream module acknowledges/accounts for the item, or the item stays review-required.
6. **Atomic + idempotent finalization** — no double post on retry; no uncontrolled partial financial posting on mid-batch failure.
7. **Credits / refunds / reversals / voids** — provider sign and source identity preserved; negatives are not rewritten as positive purchases; covered by reconciliation and settlement tests.
8. **Transaction timezone provenance** — provider timestamp stored as supplied; timezone/offset/source retained when present; no silent server/tenant timezone reinterpretation; `transaction_date` is source-local and is not derived from UTC `transaction_datetime`.
9. **Event type raw vs canonical** — `provider_event_type_raw` vs canonical `provider_event_type`; at least `PURCHASE`/`CREDIT`/`REFUND`/`REVERSAL`/`VOID`/`OTHER`/`UNKNOWN`; unknown values never coerced to `PURCHASE`.
10. **Currency raw vs canonical** — `currency_raw` preserves provider representation (e.g. BVD `CN`); `currency` is ISO-style (e.g. `CAD`); normalization does not destroy raw.
11. **Owner-operator charge provenance** — `owner_operator_charge_amount` is derived pricing/settlement; parsers, Segment 1, and Fuel AI never populate it.
12. **Finalization separation of duties** — tenant-configurable `SINGLE_ADMIN` (audited same-person) vs `SEPARATE_APPROVER` (finalizer != reviewer).
13. **Provider layout drift** — one master provider-profiles JSON with one current evidenced section per provider; document evidence must match that section’s layout anchors (mismatch → `PROVIDER_LAYOUT_UNRECOGNIZED`); future multi-layout ambiguity → REVIEW; AI must not silently compensate. Provider raw labels live in the master JSON only; UOM/price-basis currency fallbacks are provider-section scoped when evidenced (not global CAD=L / USD=GAL).
14. **Bulk review / straight-through** — AI confidence alone cannot authorize money; bulk/STP only after deterministic validation, provider controls, reconciliation, and required gates.
15. **Downstream ack escalation** — future states `ROUTING_PENDING` / `ROUTED_AWAITING_ACK` / `ACKNOWLEDGED` / `ROUTING_FAILED` with timestamps/error/retry and configurable aging/escalation.
16. **Reporting currency** — Fuel reconciles original provider currency; Accounting/Reporting conversion never overwrites Fuel source amount/currency; conversion records retain rate, rate source, as-of timestamp, from/to currency, and converted amount.
17. **Provider controls SoT** — `fuel_source_controls` is the sole normalized source of truth for provider control/summary evidence; no authoritative batch-level control-totals sidecar.
18. **Transaction/control exclusivity** — the same provider source row cannot be both a purchase/event transaction and a control; unknown/ambiguous financial meaning is `REVIEW`, not a guessed purchase.
19. **One Fuel parser + provider profiles** — shared Fuel handoff/validator with provider profile/rules JSON (BVD first); not one parser engine per provider.
20. **Exact-source dedupe race-safe** — one uploaded provider file → one `fuel_source_batches` row; `tenant + SHA256` hard stop before parse; concurrent uploads produce one financial source; DB uniqueness is second line; no normal Process Anyway; duplicates reference the existing batch. *(Future Gold — not implemented.)*
21. **Same-provider invoice identity gate** — `tenant + provider_code + invoice_number` (+ supporting facts); matching → hard duplicate; conflicting facts → `INVOICE_IDENTITY_CONFLICT` → REVIEW. *(Future Gold — not implemented.)*
22. **No cross-provider fuzzy duplicate suppression** — BVD compared only to prior BVD; Nationwide only to prior Nationwide; no BVD-vs-Nationwide transaction/invoice dedupe. *(Future Gold — not implemented.)*
23. **Confirmed source facts immutable** — after source review locks PDF-matched amounts, disputes never rewrite the original provider source transaction. *(Future Gold — not implemented.)*
24. **Flags / disputes preserve source facts** — flag ≠ dispute ≠ adjustment; cases are append-only with evidence; source reconciliation can still PASS when capture was correct. *(Future Gold — not implemented.)*
25. **Credits / adjustments separately linked** — provider credits/reversals/adjustments are new linked financial events with provider reference; never silent overwrite of original. *(Future Gold — not implemented.)*
26. **Evidence / audit trail** — dispute case timeline + attachments linked to original transaction/source; original provider PDF never overwritten. *(Future Gold — not implemented.)*
27. **Downstream posting idempotent** — retry/crash does not double-post; settlement adjustments do not overwrite provider source amounts. *(Future Gold — not implemented.)*
28. **Year-end source/adjustment totals reproducible** — original invoices ± credits/reversals/adjustments = net provider activity; settlement net tracked separately. *(Future Gold — not implemented.)*
29. **Async worker durable/recoverable** — if async ingestion is used, jobs survive API restart via durable scheduler/job/outbox; not in-process FastAPI background tasks for money-sensitive work. *(Future Gold — not implemented.)*
30. **Provider identification independent of enabled connections** — all evidenced master profiles (today BVD + NATIONWIDE); soft-disabled connections history-preserving; 0/1/many identification rules. *(Future Gold — not implemented as full upload UX; profile identity rules already locked in design.)*

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
