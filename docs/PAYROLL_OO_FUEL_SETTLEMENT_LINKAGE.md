# Payroll / O/O Settlement — Fuel Charge Linkage and Hold-Period Rules

**Status:** Logic/design lock for future Payroll/O/O settlement implementation.

**Purpose:** Define which parts of fuel-charge timing and dispute traceability belong to Payroll/O/O Settlement rather than the Fuel module.

Related documents:

- `docs/FUEL_REVIEW_HISTORY_SEARCH_ARCHITECTURE_LOCK.md`
- `docs/settlements/FUEL_SETTLEMENT_HANDOFF.md` — **authoritative for current Fuel-milestone** settlement consumption UI, `fuel_transactions` settlement-candidate fields, and financial-responsibility boundaries already implemented on `feat/fuel-card`
- `docs/HR_PAYROLL_ONBOARDING_LOGIC_ANCHOR.md`
- `docs/PAYROLL_TRIP_TRACING.md`

**Documentation authority:** This file is the locked **future Payroll/O/O** design (hold periods, carry-forward, settlement assignment, timing). It does **not** override `docs/settlements/FUEL_SETTLEMENT_HANDOFF.md` for Fuel-owned behavior that is already shipped. Where both apply, Fuel source money and classification remain Fuel-owned per `FUEL_SETTLEMENT_HANDOFF.md`; Payroll timing/assignment rules in this document apply when Settlement is built.

---

# 1. Ownership boundary

Fuel owns:

- accepted provider transaction;
- original provider source linkage;
- provider invoice/statement identity;
- transaction date;
- unit/driver snapshots;
- accepted charge amount;
- classification;
- later unit/ownership resolution inputs;
- searchable transaction history.

Payroll/O/O Settlement owns:

- pay/work period;
- weekly/biweekly cycle;
- configured hold period;
- charge-collection/cutoff window;
- settlement assignment;
- settlement finalization;
- carry-forward after prior settlement closes;
- payment/partial payment;
- settlement statement number;
- settlement adjustments/reversals.

Fuel must not duplicate Payroll's settlement calendar or assignment engine.

---

# 2. This logic primarily concerns O/O settlement deductions

The scenario discussed here is primarily owner-operator settlement behavior.

A company driver generally does not become personally responsible for company fuel merely because the driver's name or unit appears on the transaction.

Therefore:

```text
Fuel transaction exists for all applicable trucks
        ↓
ownership / responsibility resolution
        ↓
if O/O-responsible charge
        -> O/O settlement routing

if company expense
        -> no driver fuel deduction merely from driver association
```

The exact responsibility engine is a later module boundary, but Payroll must not assume every Fuel transaction with a driver is deductible from that driver.

---

# 3. Real-world distinction: transaction week vs settlement week

A fuel purchase date and the statement on which the charge is deducted are not always the same week.

Example:

```text
Driver leaves Monday
fuels twice during the trip
returns toward home next Tuesday
fuels again Tuesday
```

Depending on when provider data arrives and the fleet's hold policy, the Tuesday fuel may be attached to a later settlement even though its transaction date is Tuesday.

TruckERP must preserve both truths:

```text
Fuel transaction date
        != necessarily
Settlement period / statement where deduction appears
```

Never rewrite the Fuel transaction date to make it match the settlement date.

---

# 4. Fleets often hold settlement one or two weeks

Real fleets may intentionally delay O/O settlement for one or two weeks so late-arriving fuel, tolls, cash advances, lumper charges, and similar expenses are collected before finalization.

Therefore do not use the simplistic rule:

```text
week ended -> next charge always goes to next settlement
```

Instead, settlement configuration must support a hold/collection policy.

Conceptually:

```text
settlement_frequency = WEEKLY | BIWEEKLY | ...
hold_weeks = 0 | 1 | 2 | ...
```

Exact schema/names can be finalized when Payroll is implemented.

---

# 5. Work period and collection window are different

Example:

```text
Work Period
Jan 1 - Jan 7

Configured hold
1 week

Collection window continues through
Jan 14
```

A fuel transaction dated Jan 6 that becomes available to TruckERP on Jan 11 may still belong to the Jan 1-Jan 7 settlement because that settlement is intentionally being held for charges.

Conceptual lifecycle:

```text
WORK PERIOD
Jan 1 - Jan 7
        ↓
COLLECTING / HOLD
Jan 8 - Jan 14
        ↓
REVIEW READY
        ↓
FINALIZED
        ↓
PAID / PARTIALLY PAID
```

A two-week hold simply extends the collection window according to tenant policy.

---

# 6. Three clocks must remain distinct

At minimum preserve these concepts:

## 6.1 Transaction date

When the fuel/charge actually occurred according to accepted provider evidence.

Example:

```text
Fuel date = Jan 6
```

## 6.2 Source/process availability

When TruckERP received/reviewed/processed the provider transaction.

Example:

```text
Processed = Jan 11
```

## 6.3 Settlement assignment

Which O/O settlement statement ultimately contains the deduction.

Example:

```text
O/O Statement 01245
```

These must never be collapsed into one date.

---

# 7. Assignment rule while original settlement is still collectible

When an O/O-responsible Fuel transaction is accepted, Payroll/Settlement should first determine the settlement/work period to which the transaction economically belongs according to transaction date and tenant policy.

Then ask whether that settlement is still open for charge collection.

If the original settlement is still in an eligible state such as:

```text
OPEN
COLLECTING
REVIEW
```

then an eligible late-arriving charge may still attach to that original work-period settlement.

Example:

```text
Fuel date:          Jan 6
Processed:          Jan 11
Work period:        Jan 1-Jan 7
Hold through:       Jan 14
Settlement status:  COLLECTING

Result:
attach to Jan 1-Jan 7 settlement
```

---

# 8. Finalized means closed to silent automatic mutation

Once a settlement has been FINALIZED, normal late charge ingestion must not silently reopen or rewrite it.

Example:

```text
Fuel date:           Jan 6
Processed:           Jan 20
Jan 1-Jan 7 statement finalized Jan 14
```

Result:

```text
Do NOT reopen finalized statement.
Carry eligible charge forward to the next eligible open settlement.
```

Preserve the original transaction date (`Jan 6`).

The later settlement should be able to explain that this is a prior-period charge/carry-forward.

---

# 9. Carry-forward provenance

When a charge cannot be placed on its original settlement because that settlement is finalized, preserve why it moved.

Conceptual provenance values may include:

```text
CURRENT_PERIOD
ORIGINAL_PERIOD_STILL_COLLECTING
PRIOR_PERIOD_CLOSED_CARRY_FORWARD
MANUAL_ADJUSTMENT
REVERSAL
```

Exact enum names may change later, but the business reason must remain auditable.

A future UI should be able to show:

```text
Fuel purchased: Jan 6
Original work period: Jan 1-Jan 7
Original settlement finalized before charge arrived
Deducted on: Statement 01246
Reason: prior period closed / carried forward
```

---

# 10. Payroll owns hold policy

Hold policy is a Payroll/O/O settlement configuration, not a Fuel setting.

Examples:

```text
Weekly pay / hold 1 week
Weekly pay / hold 2 weeks
Biweekly pay / hold 1 cycle
```

Small fleets may also deliberately delay payment or partially pay a settlement; those are Payroll/Settlement behaviors.

Fuel should not try to reproduce those rules just to decide where a charge belongs.

---

# 11. Settlement finalization and payment remain separate

Do not assume FINALIZED means fully PAID.

Existing TruckERP direction supports concepts such as:

- due amount;
- finalized liability;
- partial payment;
- carryover/unpaid balance;
- later adjustments/chargebacks.

Therefore Fuel linkage must point to the actual settlement/line relationship rather than deriving truth from a payment date alone.

---

# 12. Fuel charge linkage to settlement must be explicit

For dispute traceability, Payroll should preserve an explicit business link from a settlement line/allocation back to the originating `fuel_transaction`.

Conceptually:

```text
FuelTransaction
    ↓
SettlementLine / PayEntry / allocation
    ↓
O/O Settlement / Payroll Statement
```

Do not rely only on a copied free-text statement number inside Fuel.

Before creating a new junction table, audit the current Payroll/Settlement schema to determine whether an existing settlement/pay line can own `fuel_transaction_id` or structured source metadata.

---

# 13. Do not assume the relationship is forever one-to-one

Future real-world behavior may include:

- partial deduction;
- carry-forward balance;
- reversal;
- adjustment;
- chargeback;
- split allocation under an explicit business rule.

Therefore avoid a design that can only represent:

```text
FuelTransaction.settlement_number = "01245"
```

and nothing else.

The authoritative relationship should be allocation/line based, with Fuel History able to derive the current statement reference(s).

---

# 14. Provider invoice and O/O settlement statement are different identities

Never overload one `invoice_number` concept.

Example:

```text
Provider Invoice
BVD 838710

O/O Settlement / Payroll Statement
01245
```

A fuel transaction can belong to provider invoice `838710` and later appear as a deduction on O/O statement `01245`.

Both references must remain available for disputes.

---

# 15. Fuel dispute navigation requirement

Once Payroll attaches a Fuel transaction to a settlement, Fuel History must be able to show the downstream statement and open it.

Required dispute chain:

```text
Original Provider PDF
        ↓
Provider Invoice 838710
        ↓
FuelTransaction
        ↓
Settlement line/allocation
        ↓
O/O Statement 01245
```

From Fuel transaction detail, an authorized owner/admin should eventually have:

```text
[Open Original Provider PDF]
[Open O/O Statement 01245]
```

Payroll owns the statement; Fuel provides cross-module navigation.

---

# 16. Settlement-side dispute detail

The linked settlement view should be able to show enough context to answer:

- which fuel transaction was deducted;
- provider invoice/reference;
- unit;
- fuel transaction date;
- original accepted amount;
- amount allocated/deducted on this statement;
- carry-forward reason if applicable;
- category;
- settlement period;
- statement number;
- payment/finalization status.

This is particularly important for O/O disputes.

---

# 17. Search by settlement statement number

Fuel History should support downstream search by O/O settlement/payroll statement number because this is how an O/O or owner may report a dispute.

Example user report:

> "Statement 01245 has the wrong fuel charge."

Fuel History can search `01245` and return linked Fuel transactions.

This does not make Fuel the owner of statement numbering. Fuel resolves the search through the Payroll/Settlement relationship.

---

# 18. Search by fuel week vs settlement period

Fuel History may provide a calendar month/week search based on the Fuel transaction date.

Payroll may provide a different settlement period based on tenant payroll configuration.

These are intentionally separate.

Example:

```text
Fuel transaction date: Jan 6
Fuel History calendar week: January Week 1
Settlement statement: 01245
Settlement work period: Jan 1-Jan 7
Hold through: Jan 14
```

Or, after carry-forward:

```text
Fuel transaction date: Jan 6
Fuel History calendar week: January Week 1
Actual deduction statement: 01246
Reason: original statement finalized
```

Do not rewrite Fuel history to match Payroll period labels.

---

# 19. Weekly month labels are not Payroll truth

UI labels such as:

```text
January Week 1
January Week 2
January Week 3
January Week 4
January Week 5
```

are useful Fuel History search conveniences based on actual calendar date ranges.

They must not be used as the authoritative settlement-assignment algorithm.

Payroll determines settlement eligibility using its own configured periods/hold state.

Leap-year handling belongs to calendar/date computation, not special hardcoded Payroll branches.

---

# 20. Company driver rule

Do not route a Fuel transaction to driver deduction solely because `driver_name_snapshot` exists.

For company-driver/company-truck cases, the charge may remain a company expense.

O/O settlement deduction requires ownership/responsibility resolution according to later Fuel/Fleet/Payroll rules.

---

# 21. Late-charge example — original settlement still open

```text
Work period:          Jan 1-Jan 7
Hold policy:          1 week
Collection cutoff:    Jan 14
Fuel transaction:     Jan 6
Provider data ready:  Jan 11
Settlement status:    COLLECTING
```

Expected:

```text
attach charge to Jan 1-Jan 7 settlement
```

Reason:

The fleet intentionally holds the settlement so charges can arrive.

---

# 22. Late-charge example — original settlement closed

```text
Work period:          Jan 1-Jan 7
Hold policy:          1 week
Settlement finalized: Jan 14
Fuel transaction:     Jan 6
Provider data ready:  Jan 20
```

Expected:

```text
original statement remains unchanged
charge moves to next eligible open settlement
original fuel date remains Jan 6
carry-forward reason preserved
```

---

# 23. Search/trace example

An O/O says:

> "My January fuel is wrong. I think Statement 01245 has the problem."

Owner/admin can search Fuel History by:

```text
Unit = 1103
Month = January
or
O/O Statement = 01245
```

Then inspect a charge:

```text
Provider:          BVD
Provider Invoice:  838710
Fuel Date:         Jan 6
Unit:              1103
Amount:            450.00
O/O Statement:     01245
Allocated Amount:  450.00
```

From there:

```text
Open provider PDF
Open O/O statement
```

This is the required dispute traceability.

---

# 24. Data ownership rule

One canonical source per concern:

```text
Fuel owns FuelTransaction truth.
Payroll owns Settlement/Statement truth.
The relationship links them.
```

Do not duplicate complete settlement logic or mutable statement truth into Fuel.

Do not duplicate accepted Fuel money into Payroll without a source reference back to the originating Fuel transaction.

---

# 25. Non-negotiable Payroll/O/O invariants

1. Transaction date and settlement period are separate truths.
2. Work period and hold/collection window are separate concepts.
3. Hold policy belongs to Payroll/O/O Settlement.
4. Fleets may hold weekly settlement one or two weeks to collect charges.
5. A late charge may still attach to its original work period while that settlement is collectible.
6. A FINALIZED settlement is not silently reopened by normal Fuel ingestion.
7. Charges arriving after finalization carry forward to the next eligible open settlement with provenance.
8. Fuel transaction date never changes because of carry-forward.
9. O/O statement number and provider invoice number remain distinct.
10. Payroll preserves an explicit traceable relationship back to `fuel_transaction`.
11. Fuel can display/search the resulting statement reference but does not own settlement assignment logic.
12. Company-driver fuel is not automatically a driver deduction.
13. Partial payment/adjustment/carryover must not be blocked by a simplistic copied settlement-number field.
14. Owners/admins must be able to navigate both directions during a dispute.

---

# 26. Implementation audit before schema changes

Before implementing this document, inspect current:

- `PayPeriod`;
- `PayEntry`;
- `PayRun` / `PayRunItem`;
- O/O settlement/liability models;
- settlement line/allocation models;
- partial payment/carryover behavior;
- existing source/reference fields;
- current FuelTransaction downstream fields;
- current `downstream_module`, acknowledgment, and gate fields;
- any existing explicit business-object links.

Then decide whether the correct implementation is:

- `fuel_transaction_id` on an existing settlement/pay line;
- an existing generic source-reference mechanism;
- or a dedicated allocation/link table.

Do **not** create a duplicate link table until this audit is complete.
