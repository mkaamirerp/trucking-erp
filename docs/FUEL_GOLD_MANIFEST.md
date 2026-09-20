# Fuel Gold Manifest

**Status:** NOT GOLD.

There is currently no frozen Fuel Gold branch/tag documented here. Do not treat the existence of Fuel code, passing unit tests, parsed BVD/Nationwide fixtures, or a deploy as Gold by itself.

**Architecture source of truth:** `docs/FUEL_CARD_MODULE_DESIGN.md`  
**Execution plan:** `docs/FUEL_CARD_IMPLEMENTATION_PLAN.md`

---

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
[ ] native raw values are strings in ordered JSONB arrays
[ ] source evidence is immutable/append-only
[ ] review/correction is append-only
[ ] unknown BVD layout/field/structure changes cause review/reject
[ ] field-completeness tests pass
[ ] structural-completeness tests pass
[ ] document-level BVD regression fixtures pass
```

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

# 3. Native-evidence database gates

Before Gold, the database model must enforce the source-evidence rules in the architecture.

Required concepts:

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
- ordered/repeated native JSONB fields;
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
