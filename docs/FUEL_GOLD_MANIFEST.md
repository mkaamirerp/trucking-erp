# Fuel Gold Manifest

**Status:** NOT GOLD.

There is currently no frozen Fuel Gold branch/tag documented here. Do not treat the existence of Fuel code, passing unit tests, parsed BVD/Nationwide fixtures, or a deploy as Gold by itself.

**Architecture source of truth:** `docs/FUEL_CARD_MODULE_DESIGN.md`  
**Execution plan:** `docs/FUEL_CARD_IMPLEMENTATION_PLAN.md`

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


# 1. Current Gold boundary

Fuel/Card is a money-moving subsystem. Gold means the supported provider paths are source-controlled, reviewable, financially gated, regression-tested and frozen at a known commit/artifact.

Current supported/test provider foundation:

```text
1. BVD
2. Nationwide
```

No third provider is required before Gold for this foundation, and unsupported providers must not be processed through a generic fallback.

---

# 2. Provider-native foundation required before Gold

## 2.1 BVD must be structurally complete

Gold cannot be established until the approved BVD profile proves all of the following:

```text
[ ] approved BVD profile/version exists
[ ] every data-bearing block/group in approved fixtures is inventoried
[ ] exact invoice-header labels are frozen
[ ] Client info block is represented without inventing a customer-name label
[ ] Transactions for card is represented as group context
[ ] child transactions reference/inherit the card-group context
[ ] exact 21 BVD transaction columns are frozen
[ ] transaction-level SUBTOTAL rows are controls, never purchases
[ ] full observed page-1 summary/control sequence is frozen
[ ] Card # / Fuel Total relationship to the card-group key is represented
[ ] Grand Totals exact 11 columns are frozen
[ ] Grand Totals row labels are inventoried
[ ] Manual and Express are not treated as Legend product codes
[ ] Legend block and observed code/product pairs are preserved
[ ] exact provider source values are preserved losslessly and auditable (strings; order preserved where the storage model requires it)
[ ] source evidence is immutable/append-only
[ ] review/correction is append-only
[ ] unknown BVD layout/field/structure changes cause review/reject
[ ] field-completeness tests pass
[ ] structural-completeness tests pass
[ ] document-level BVD regression fixtures pass
```

**BVD Implementation 1 (current milestone):** `docs/FUEL_BVD_IMPLEMENTATION_1.md` governs the locked fidelity path: digital BVD PDF → exact extraction → **one** `fuel_bvd` table → exact source values stored as **TEXT** → PostgreSQL round-trip → PDF left / DB values right. That milestone does **not** require `fuel_source_document`, versioned parse runs, block/record tables, or ordered JSONB native arrays. Passing Implementation 1 is not Fuel Gold; it is source-fidelity proof for BVD only.

A future generalized provider-native layer may store the same fidelity using ordered JSONB/block/record tables. That generalization is **not** a prerequisite for declaring Implementation 1 passed.

## 2.2 Nationwide must prove framework reuse

Nationwide must be implemented as its own exact provider profile, not by forcing BVD-shaped fields onto it.

Gold requires at minimum:

```text
[ ] exact Nationwide source blocks inventoried
[ ] exact ACCOUNT INFORMATION labels frozen
[ ] exact BILLING SUMMARY labels frozen
[ ] exact TRANSACTION BREAKDOWN BY CARD columns frozen
[ ] Account Code and Card Number handled as per-row columns for current fixture
[ ] CARD_TOTAL classified before field interpretation
[ ] Canadian GST/QST control values cannot become fake transaction fields
[ ] unknown Nationwide layout/structure causes review/reject
[ ] Nationwide regression fixtures pass
```

---

# 3. Native-evidence database gates (future Gold / generalization)

Before **final Fuel Gold**, the generalized database model must enforce the source-evidence rules in the long-term architecture. These concepts are **not** prerequisites for BVD Implementation 1 (`fuel_bvd` TEXT columns).

Required concepts for the generalized layer:

```text
fuel_provider_profile
fuel_source_document
fuel_parse_run
fuel_source_block
a provider-native record table
an append-only review/correction table
```

Exact table names may follow repository convention, but behavior must prove:

```text
[ ] unsupported provider/profile cannot start ingestion
[ ] retired profile cannot start new ingestion
[ ] original source file/payload is immutable
[ ] SHA-256 + storage reference identify original file evidence
[ ] same source can have explicit versioned parse runs
[ ] block/group structure is first-class
[ ] group/inherited context is retained
[ ] native field order is preserved
[ ] duplicate native labels can be preserved
[ ] provider-native raw values remain exact strings
[ ] native evidence cannot be UPDATE/DELETE mutated by application role
[ ] review/corrections never overwrite native evidence
[ ] tenant isolation is enforced across document/parse/block/record/review relationships
```

A GIN index on native JSONB is **not** a Gold requirement unless a real production query requires it.

---

# 4. Financial gates required before Gold

Provider-native extraction is necessary but not sufficient for final Fuel Gold.

Gold also requires the later financial layers to be verified:

```text
[ ] reviewed provider evidence maps deterministically to canonical records
[ ] every provider source row/control is accounted for exactly once
[ ] CAD and USD reconcile independently
[ ] no fake cross-currency provider total can pass
[ ] unresolved/review-required controls cannot authorize PASS
[ ] effective reviewed structure/classification drives reconciliation
[ ] grand-total equality cannot hide wrong row/date/unit/card assignment
[ ] transaction datetime/date drives historical truck/ownership resolution
[ ] date-only historical resolution respects provider/source timezone
[ ] truck commercial responsibility is independent of driver employment type
[ ] O/O pricing rejects impossible/negative invalid outcomes
[ ] credit/refund/reversal sign discipline is enforced end-to-end
[ ] READY_FOR_RECONCILIATION means all required review conditions are resolved
[ ] provider amount and O/O settlement charge remain separate
[ ] settlement only receives fully eligible/reconciled records
[ ] finalization is idempotent
[ ] posted corrections use audited adjustment/reversal
```

---

# 5. Confirmed blockers from Fuel archive audit

The uploaded Fuel archive audit confirmed the following issues. These remain Gold blockers until fixed and regression-tested.

## 5.1 O/O responsibility gate

`app/services/fuel_oo_pricing.py` can let `is_company_driver=True` suppress an O/O charge.

Locked rule:

> Truck/commercial fuel responsibility decides who pays. A company-employed driver can operate an O/O-owned truck without converting the truck's fuel responsibility to company responsibility.

## 5.2 DATE_ONLY historical resolution

`app/services/fuel_historical_resolution.py` can select the wrong historical owner/payee around a local-date boundary when date-only input is anchored incorrectly.

## 5.3 Mixed-currency reconciliation

CAD and USD can currently be summed under an insufficiently scoped control and incorrectly return PASS.

## 5.4 Unresolved control can authorize PASS

A review-required or effectively invalid control can still be used as reconciliation evidence.

## 5.5 Review reclassification is not authoritative end-to-end

Changing reviewed structure/role can fail to change the effective transaction/control set used by reconciliation.

## 5.6 O/O numeric sanity

Invalid inputs/outcomes such as negative quantity, discount exceeding applicable price and negative charge can reach calculated status.

## 5.7 Credit/refund/reversal sign discipline

Sign validation exists in code but is not consistently enforced through the complete financial path.

## 5.8 Review readiness

Review/process readiness currently does not prove every unresolved financial condition is cleared.

---

# 6. Current audit test snapshot

At the recorded archive-audit checkpoint:

```text
102 tests passed
```

Three additional test modules did not collect in that audit runtime because `asyncpg` was absent there while repository requirements included `asyncpg==0.31.0`.

That was classified as an audit-environment issue unless reproduced in the real project environment.

This test snapshot is **not** a Gold declaration.

---

# 7. Required Gold regression families

At minimum, a Gold candidate must include green tests for:

- provider/profile whitelist and retirement behavior;
- tenant isolation;
- source-file hash/idempotency;
- immutable source document;
- versioned parse runs;
- ordered/repeated native fields (JSONB or equivalent in the generalized model);
- append-only native evidence;
- append-only review overlay;
- BVD exact 21 transaction fields;
- BVD exact page-1 controls;
- BVD exact 11 Grand Totals columns;
- BVD card-group inheritance;
- BVD Legend and Manual/Express separation;
- Nationwide exact native columns;
- Nationwide transaction vs CARD_TOTAL classification;
- unsupported/changed layout review/reject;
- cross-currency reconciliation rejection;
- unresolved-control reconciliation rejection;
- reviewed-role authority;
- historical date-only timezone resolution;
- O/O responsibility independent of driver employment type;
- O/O numeric sanity;
- credit/refund/reversal sign rules;
- finalization idempotency;
- settlement drill-down and exact totals;
- posted adjustment/reversal audit behavior;
- relevant Load / People / Payee / Truck regressions.

---

# 8. Gold freeze procedure

When all required gates pass and Fuel is intentionally frozen:

1. identify the exact verified commit;
2. record the exact deployed/baked image or artifact digest where applicable;
3. create/finalize the agreed Fuel Gold branch/tag strategy;
4. record the immutable Gold tag such as `fuel-gold-YYYY-MM-DD`;
5. record database migration state;
6. record provider-profile versions included in Gold;
7. record exact fixture/test counts and results;
8. list any explicitly parked non-Gold future work;
9. update `GOLD_MODULES.md`;
10. replace the `NOT GOLD` status at the top of this file with the frozen commit/tag/artifact details.

Do not place Fuel Gold state in `DL_GOLD_MANIFEST.md` or under the DL Gold branch/tag.

---

# 9. Current parked/future scope

The following are not required to establish the BVD/Nationwide provider foundation unless explicitly reopened:

- unsupported third-party fuel-card vendors;
- speculative direct access to underlying EFS/Comdata/WEX rails for white-label customers;
- unverified provider APIs or data-sharing contracts;
- generic “any fuel statement” AI parsing;
- provider-specific mathematical semantics not yet proven by the semantic phase;
- automatic rounding tolerance without evidence;
- automatic lumper-to-load linking;
- currency conversion that rewrites immutable source currency/UOM.

Future providers follow the same approved-provider/profile footprint established by BVD and validated by Nationwide.
