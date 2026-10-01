# Fuel Review, History, Search, and Payroll-Link Architecture Lock

**Status:** Architecture lock / amendment.

**Scope:** TruckERP Fuel module as one provider-neutral business module. BVD, Nationwide, WEX, Comdata, and future providers are source adapters into the same Fuel domain; this design is **not BVD-only**.

**Precedence:** Where this document conflicts with older Fuel wording that treats a parser mistake as permanent immutable provider evidence, this document takes precedence for the current staged-review → Process workflow. The **original provider file/payload** is the immutable source evidence. Parser output is a temporary machine interpretation until human review and Process.

Related documents:

- `docs/FUEL_CARD_MODULE_DESIGN.md`
- `docs/FUEL_CARD_IMPLEMENTATION_PLAN.md`
- `docs/PAYROLL_OO_FUEL_SETTLEMENT_LINKAGE.md`

---

# 1. Core boundary: one Fuel module, many providers

TruckERP Fuel is one business module.

Provider-specific code is responsible for reading provider-specific evidence:

```text
BVD PDF/API
Nationwide PDF/API
WEX API/export
Comdata/Corpay API/export
future provider
        ↓
provider adapter/profile
        ↓
Fuel staging/review
        ↓
Fuel canonical transaction/history
```

Do **not** design search, history, settlement traceability, dispute workflow, or canonical transaction identity around BVD-only terms.

BVD fields such as `Express Code`, BVD card sections, and BVD-specific control labels remain provider-specific source evidence. The Fuel module exposes provider-neutral search and history over accepted permanent Fuel transactions.

---

# 2. Original provider document is the immutable source truth

The immutable evidence is the original provider file/payload.

Example:

```text
Original PDF says Unit # = 1025
Parser reads Unit #      = 125
Human compares against PDF and changes 125 -> 1025
```

The provider did **not** say `125`. `125` is a parser mistake.

Therefore:

```text
ORIGINAL PDF / API PAYLOAD
    immutable source evidence

PARSER OUTPUT
    temporary machine interpretation

HUMAN REVIEWED VALUE
    accepted structured interpretation of the source
```

Do not permanently represent a known parser mistake as though it were provider truth.

---

## Screen roles (ingestion vs processed operational record)

**Ingestion / review screen** (upload, staging, PDF side-by-side, parser output, reconciliation gates, human corrections **before** Process):

- Provider adapters (BVD PDF/API, future CSV/API/manual).
- Temporary/admin workspace — **not** the long-term place operators search old driver/unit/charge history.

**Process succeeds** → accepted permanent `fuel_bvd` → canonical `fuel_transactions`.

**Processed Fuel record / history** (Fuel Home Recent activity expand, full stored detail, future global history):

- Permanent operational admin workspace: search, filter, unit/driver/card, provider references, categories/reasons, amounts, dates, disputes, settlement trace (later), source/PDF drill-down.
- Must represent **all accepted charge rows** for that import (e.g. card `TRANSACTION` + `EXPRESS_TRANSACTION`), not a subset.
- Control rows such as `EXPRESS_SUBTOTAL` are **not** charges and are not shown as line items.

Do **not** redesign the ingestion/review screen into a history screen.

The permanent audit trail must be able to answer:

- which original document/payload was processed;
- who reviewed it;
- when it was reviewed;
- what accepted structured values were processed;
- which gates passed;
- which canonical Fuel transactions were created.

---

# 3. Staging is temporary machine interpretation

Before Process, the staged record may retain both:

```text
Extracted value: 125
Current reviewed value: 1025
```

This is useful for the review screen and parser debugging while the stage is open.

The parser interpretation does not become permanent merely because it existed first.

If the user closes/discards the stage before Process, the temporary parser interpretation is discarded according to the staging lifecycle.

---

# 4. Human review is the final accepted parse

Business rule:

> **Parser = first interpretation. Human review against the original provider document = final accepted interpretation.**

The human is not editing the provider PDF. The human is correcting TruckERP's interpretation of that PDF.

Example:

```text
PDF:               1025
Parser stage:       125
Human reviewed:    1025
```

After Process, accepted permanent structured data must show:

```text
Unit # = 1025
```

not a stale parser value plus an overlay required forever to reconstruct the business truth.

---

# 5. Inline review editing is required

Review corrections must happen **inline in the row/field the user is looking at**.

Wrong UX:

```text
parsed rows at top
...
large correction form at bottom
transaction #27
field selector
old value
new value
```

Required UX:

```text
Date | Unit | Driver | Product | Final
       125
        ↑ click
       [1025]
```

The reviewer should not have to locate a transaction number in a separate correction form.

Inline editing must support the reviewable provider fields already defined for that provider profile.

---

# 6. Every edit reruns logic using the latest reviewed values

The first gate/reconciliation run may use parser values because no human correction exists yet.

After any human edit, all applicable gates must use the **latest reviewed/effective staging values**.

Example:

```text
Parser reads Unit = 125
    ↓
run gates using 125
    ↓
human changes 125 -> 1025
    ↓
save reviewed stage
    ↓
rerun gates using 1025
```

If the reviewer edits again:

```text
125 -> 1025 -> 1026
```

then `1026` is the current gate input.

No stale earlier value may win.

Do **not** rerun the parser merely because the reviewer edited a field.

---

# 7. Gates that must use reviewed/effective stage data

After a review edit, all relevant validation must consume the same current reviewed dataset, including:

- source reconciliation;
- card/account controls;
- product controls;
- Express/group controls;
- invoice control totals;
- row/date diagnostics;
- duplicate/source-row checks;
- canonical projection preview/gate;
- any Process eligibility rule.

Authoritative provider money controls remain exact `Decimal` gates.

Derived arithmetic from displayed quantity/rate precision remains diagnostic, not a replacement for provider final amounts.

---

# 8. Process promotes one accepted dataset

At Process time, TruckERP builds one accepted/effective source dataset.

That same dataset is used for:

```text
permanent accepted provider-structured rows
        +
FuelSourceControl evidence
        +
canonical fuel_transactions
        +
canonical money gate
```

Do not persist contradictory permanent views such as:

```text
permanent source row Unit = 125
canonical FuelTransaction Unit = 1025
```

After Process both permanent structured representations should agree on the accepted reviewed value:

```text
permanent accepted source Unit = 1025
FuelTransaction unit snapshot  = 1025
```

The immutable original PDF/payload remains available as the ultimate provider evidence.

---

# 9. Money correction example

Example:

```text
PDF Final Amount:      1025.00
Parser extracted:       125.00
```

Initial parser-based reconciliation may fail.

Human compares against the PDF and edits inline:

```text
125.00 -> 1025.00
```

TruckERP reruns all financial gates using `1025.00`.

If accepted values reconcile, Process persists:

```text
accepted source final amount       1025.00
FuelTransaction.total_amount       1025.00
```

The known parser mistake `125.00` must not continue driving financial logic after review.

---

# 10. Permanent review/audit meaning

Permanent audit should record human/business actions, for example:

- original source document reference/hash;
- provider and provider invoice/statement identity;
- reviewed by;
- reviewed at;
- processed by;
- processed at;
- review/gate outcome;
- permanent accepted data;
- later classification history;
- downstream settlement linkage when applicable.

A parser mistake may be kept temporarily for stage review or technical diagnostics, but should not be described as "provider supplied value" when the original document proves otherwise.

Any existing permanent correction tables must be audited before removal or repurposing. Do not drop schema blindly. If a permanent table is needed for **post-Process amendments**, that is a separate business use from preserving pre-Process parser mistakes.

---

# 11. Processed source is read-only

After Process:

- accepted provider-structured data is read-only;
- original source PDF/payload is retained and viewable;
- canonical classification may remain editable as operational metadata under its own audit rules;
- money/source changes require an explicit future adjustment/amendment process, not silent mutation.

This preserves the distinction between:

```text
SOURCE REVIEW
    correcting parser interpretation before Process

OPERATIONAL CLASSIFICATION
    describing what an accepted charge means

POSTED FINANCIAL ADJUSTMENT
    future audited correction after financial use
```

---

# 12. Fuel History is transaction-first

Once many statements are processed, Recent Activity is not enough.

Fuel History / Advanced Search should search permanent canonical `fuel_transactions` first, then allow drill-down to:

```text
FuelTransaction
      ↓
FuelSourceBatch / provider invoice
      ↓
accepted provider source row
      ↓
original PDF/payload
      ↓
linked O/O settlement/payroll line when present
```

This allows disputes to start from whichever clue the driver/O/O/admin remembers.

---

# 13. Basic search bar

A normal Fuel History search bar should understand common identifiers such as:

- unit number;
- driver name/snapshot;
- provider invoice number;
- provider transaction/auth code;
- card/account number;
- provider reference (for example BVD Express #);
- provider reason text;
- category;
- amount;
- provider name.

Example searches:

```text
1103
838710
E345296820
5359948
lumper fee
203.00
BVD
```

---

# 14. Advanced Search dimensions

Advanced Search should organize filters into four user concepts.

## 14.1 WHO

- Unit #
- Driver
- O/O / payee (after ownership/payee linkage exists)
- resolved truck (future)

## 14.2 WHEN

- Month
- Calendar week within month
- Custom date range
- Provider statement period
- transaction date range

## 14.3 SOURCE

- Provider
- Provider Invoice / Statement #
- Card / Account #
- Auth # / provider transaction identity
- Provider Reference / Express #
- Product
- Provider Reason
- Currency
- Amount range
- Classification/category/status

## 14.4 DOWNSTREAM

- O/O Settlement / Payroll Statement #
- settlement status
- downstream allocation status

Fuel displays downstream references for dispute tracing; Payroll/Settlement owns the settlement rules themselves.

---

# 15. Month/week selector

Many fleets process fuel weekly, while drivers/O/Os often remember only the month and approximate week.

Selecting a month should expose friendly calendar-week choices using actual date ranges.

Example:

```text
January 2026
Week 1   Jan 1 - Jan 7
Week 2   Jan 8 - Jan 14
Week 3   Jan 15 - Jan 21
Week 4   Jan 22 - Jan 28
Week 5   Jan 29 - Jan 31
```

Leap-year handling must come from real calendar dates, not hardcoded month lengths.

Example:

```text
February 2028
Week 1   Feb 1 - Feb 7
Week 2   Feb 8 - Feb 14
Week 3   Feb 15 - Feb 21
Week 4   Feb 22 - Feb 28
Week 5   Feb 29 - Feb 29
```

The UI label may say `Week 1`, `Week 2`, etc., but the backend query uses the actual date range.

Calendar-week search is a **Fuel History convenience filter**. It does not decide which Payroll/O/O settlement receives the charge.

---

# 16. Provider statement periods are separate from calendar weeks

A provider may bill on a weekly period that does not align to calendar Week 1/2/3/4/5.

Therefore Advanced Search should also support the provider's actual statement periods where known.

Example choices:

```text
Calendar weeks
    January Week 2: Jan 8 - Jan 14

Provider statement periods
    BVD: Jan 7 - Jan 13
```

Do not pretend all providers use the same weekly boundaries.

---

# 17. Distinguish document numbers explicitly

Do not label every external/downstream identifier simply `Invoice Number`.

At minimum distinguish:

```text
Provider Invoice / Statement
    e.g. BVD 838710

TruckERP Fuel Batch / Import
    internal source batch/import identity

O/O Settlement / Payroll Statement
    e.g. 01245
```

A user should be able to search by any of these, but the UI must state what kind of document number it is.

Recommended search pattern:

```text
Document Type: [Provider Invoice | O/O Settlement | Payroll Statement | ...]
Document #:   [01245]
```

---

# 18. Fuel does not own Payroll assignment logic

Fuel owns the accepted charge and its provenance.

Payroll/O/O Settlement owns:

- pay period/work period;
- hold period;
- settlement collection window;
- assignment of eligible charges to a settlement;
- finalization;
- carry-forward after closure;
- payment/partial-payment rules.

Fuel must not duplicate those rules.

Fuel only needs the resulting traceability:

```text
This FuelTransaction was attached to O/O Settlement / Payroll Statement 01245
```

See `docs/PAYROLL_OO_FUEL_SETTLEMENT_LINKAGE.md`.

---

# 19. Settlement/statement reference in Fuel is a link, not copied ownership logic

Fuel History should show a linked settlement/statement reference when Payroll has consumed the charge.

Preferred relationship:

```text
FuelTransaction
    ↓ explicit business link
Settlement/Pay line
    ↓
Settlement / Statement
```

Do not make Fuel independently invent or manage a settlement number.

Do not rely on an unvalidated copied text field if a real settlement-line relationship exists.

Exact schema should be audited against current Payroll/Settlement models before adding a new link table.

The relationship should be capable of supporting future adjustment/carryover/partial-allocation realities rather than assuming a simplistic one-time text assignment.

---

# 20. Dispute drill-down

For an O/O dispute, Fuel should be able to show both source and settlement sides.

Example:

```text
Fuel Charge
Provider:              BVD
Provider Invoice:      838710
Auth #:                 E345296820
Provider Ref/Express #: 5359948
Fuel Date:              2025-12-11
Unit:                   1103
Provider Reason:        lumper fee
Category:               LUMPER
Amount:                 203.00 USD

Source
[Open Original Provider PDF]

Settlement
O/O Statement #:        01245
Settlement Period:      ...
Deducted/Allocated:      203.00 USD
[Open Settlement]

Audit
[Source Review]
[Classification History]
[Settlement Link History]
```

If not yet assigned:

```text
Settlement: Not yet assigned
```

Fuel provides the navigation; Payroll owns the settlement state.

---

# 21. Search result design

Search results should be individual charges, not only invoice rows.

Example:

| Fuel Date | Unit | Provider | Provider Invoice | Category | Amount | O/O/Payroll Statement |
| --- | --- | --- | --- | --- | ---: | --- |
| Jan 11 | 1103 | BVD | 838710 | LUMPER | 203.00 USD | 01245 |
| Jan 12 | 1103 | BVD | 838710 | FUEL | 558.30 USD | 01245 |
| Jan 14 | 1103 | BVD | 839102 | FUEL | 311.84 USD | 01246 |

Every row should drill into the full transaction/source/settlement chain.

---

# 22. Search totals and currencies

Advanced Search should show totals for the result set, grouped by category and currency where useful.

Example:

```text
Unit 1103 / January Week 2

USD
Fuel       1,955.42
DEF           84.17
Lumper       203.00
Toll         275.00
Other        103.00
------------------
Total      2,620.59

CAD
Fuel         612.40
------------------
Total        612.40
```

Do not combine USD and CAD into one total unless an explicit FX policy is later implemented.

---

# 23. Search by unit must preserve historical truth

Fuel search uses the unit snapshot accepted on the transaction at the time of the charge.

Later Fleet resolution may additionally expose:

- resolved truck;
- ownership at transaction date;
- O/O/payee at transaction date.

Do not rewrite historical Fuel unit snapshots merely because the truck/unit assignment changes later.

---

# 24. Company-driver vs O/O boundary

Fuel History applies to all accepted Fuel transactions.

The O/O settlement deduction workflow is different:

- O/O charges may be routed to O/O settlement according to responsibility rules;
- company-driver fuel is generally not a driver deduction merely because a driver name/unit exists.

The detailed settlement timing/hold/carry-forward logic belongs to Payroll/Settlement, not Fuel.

---

# 25. Export direction

Advanced Search should later support CSV/export for disputes and reconciliation.

Export should use accepted permanent canonical data and include traceability fields such as:

- transaction date;
- unit;
- provider;
- provider invoice;
- provider auth/reference;
- category;
- currency;
- amount;
- linked O/O/Payroll statement where present.

Export does not replace source-document access.

---

# 26. Non-negotiable Fuel invariants

1. Fuel is provider-neutral; providers are adapters.
2. Original PDF/API payload is immutable source evidence.
3. Parser output is temporary until reviewed/accepted.
4. Human review against the original source is authoritative before Process.
5. Review editing is inline.
6. Every edit reruns gates on latest reviewed/effective values.
7. Process promotes one accepted dataset consistently.
8. Permanent accepted source and canonical `fuel_transactions` must agree.
9. Source reconciliation and classification remain separate concerns.
10. Fuel History is transaction-first and searchable by multiple dispute clues.
11. Provider Invoice and O/O/Payroll Statement numbers are different identities.
12. Fuel displays downstream settlement links but does not own settlement timing rules.
13. Search week/month filters are real date ranges and leap-year safe.
14. Provider statement periods remain separate from calendar-week search.
15. Multi-currency totals stay separate without explicit FX policy.
16. Original PDF/payload and linked settlement/statement must be one-click drill-down targets for disputes.

---

# 27. Implementation follow-up

Before implementing this amendment, audit current code for:

- stage inline edit path;
- stage/effective values used by reconciliation;
- Process persistence behavior;
- use of permanent `fuel_bvd_field_correction`;
- construction of `FuelTransaction.provider_raw`;
- any code that assumes permanent provider rows equal parser-first output;
- existing Fuel history/search endpoints;
- existing Payroll/Settlement line relationships that can link back to `fuel_transactions`.

Do not create duplicate tables until existing models have been inspected.
