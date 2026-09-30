# Fuel → Settlement boundary

**Purpose:** Split **Fuel-owned** financial logic (implement now) from **Settlement-owned** consumption (implement later).

**Related:**

- `docs/FUEL_CARD_MODULE_DESIGN.md` — three clocks (provider vs Fuel Process vs settlement)
- `docs/FUEL_BVD_IMPLEMENTATION_1.md` — Fuel Process boundary and `finalized_at`
- `app/services/fuel_financial_responsibility.py` — Fuel-owned responsibility + pricing orchestration
- `app/services/fuel_oo_pricing.py` — O/O unit-price modes (Decimal)

---

## A. Fuel-owned logic — implement now

Fuel must determine **before Settlement exists**:

| Concern | Owner | Implementation |
|---------|--------|----------------|
| Charge **category** (Segment B) | Fuel | `fuel_transaction_classify` + persistence |
| **Financial responsibility** (`COMPANY_EXPENSE`, `DRIVER_DEDUCTION`, `OWNER_OPERATOR_DEDUCTION`, `REVIEW_REQUIRED`) | Fuel | `fuel_financial_responsibility.resolve_fuel_financial_responsibility` |
| Historical **unit ownership / payee** at transaction time | Fuel | `fuel_historical_resolution` |
| O/O **fuel unit pricing** (four locked modes) | Fuel | `fuel_oo_pricing.calculate_oo_fuel_charge` / `price_fuel_transaction_for_oo` |
| **Settlement deduction candidate** (eligible later, not consumed) | Fuel | `fuel_transactions.settlement_deduction_candidate` (`NULL` = not evaluated; `FALSE`/`TRUE` after refresh) |
| **Settlement deduction basis amount** (Fuel-owned recoverable amount) | Fuel | `fuel_transactions.settlement_deduction_basis_amount` (`NULL` = N/A or not determined) |
| **Responsible party context** | Fuel | `owner_operator_payee_id` for O/O deductions; `driver_id` on the transaction for company **DRIVER_DEDUCTION** — identifies the responsible driver/person context only; **Payroll/Settlement** resolves People-first payee/engagement (do not treat `driver_id` as the accounting payee id) |
| O/O **pricing basis** (pre-tax unit extension) | Fuel | `oo_charge_unit_price`, `owner_operator_charge_amount` (= qty × unit price when calculated), `oo_pricing_*` |
| Provider source amounts / taxes | Fuel (preserve only) | `principal_amount`, `provider_fee_amount`, `total_amount`, tax columns — never rewritten for deductions |
| **Financial audit** | Fuel | Append-only `fuel_transaction_financial_event` (not Settlement) |

**Integration timing (current code):**

1. **Classification** runs after canonical Process via `best_effort_backfill_classifications_for_import` (post-commit).
2. **Financial responsibility refresh** runs after every classification persist (`apply_classification_result` → `refresh_fuel_financial_responsibility_for_transaction_row`).

**Not Fuel Process:** provider paid, payroll paid, settlement generated, settlement period boundaries.

**LOCKED — CASH_ADVANCE recoverable basis (Fuel-owned):**

```text
settlement_deduction_basis_amount = principal_amount + provider_fee_amount
```

(on the **same** canonical transaction row — only the fee directly attributable to that cash advance, not unrelated statement/card fees).

Example: principal `100.00` + fee `3.00` → basis `103.00`. Applies when financial responsibility is **DRIVER_DEDUCTION** or **OWNER_OPERATOR_DEDUCTION** and candidate is **TRUE**. Do **not** use `owner_operator_charge_amount` for cash advance.

**NOT LOCKED (do not infer in Payroll/Settlement):**

| Topic | Status |
|-------|--------|
| **O/O FUEL settlement tax treatment** (final tax-inclusive deduction from `owner_operator_charge_amount`) | **NOT_LOCKED** (`TAX_TREATMENT_FOR_SETTLEMENT = NOT_LOCKED`) — Fuel does **not** set `settlement_deduction_basis_amount` for O/O FUEL |

**`owner_operator_charge_amount` (locked Fuel meaning):** O/O contractual **pre-tax product extension** (`quantity × oo_charge_unit_price`). Not provider billed total, not provider taxes, not cash advance basis, not a final Settlement line amount.

---

## B. Settlement-owned logic — implement later (this doc)

Do **not** build in the Fuel milestone:

- Settlement **generation**
- Settlement **periods** / company closing calendars
- **Settlement line** creation consuming Fuel candidates
- Anti-double-deduction enforcement in Settlement
- Reversal / adjustment chains
- Settlement **number**, **payment state**
- Fuel UI **✓** and clickable settlement link (derived from real settlement lines only)

---

## C1. Source transaction remains immutable

`fuel_transactions` is the canonical Fuel source transaction.

Settlement must **reference** the Fuel transaction. Settlement must **not** rewrite the Fuel transaction to “mark” money deductions (no `settled = true` column on `fuel_transactions`).

Conceptual future relation (field names illustrative unless settlement schema already defines equivalents):

```text
FuelTransaction
    id
      |
      v
SettlementLine
    source_type = FUEL_TRANSACTION
    source_id   = fuel_transaction.id
    amount
      |
      v
Settlement
    settlement_number
    payee_id
    period_start
    period_end
    status
```

Do **not** implement these tables in the Fuel milestone.

---

## C2. Settlement status is derived from downstream evidence

Fuel must **not** expose a manually editable “settled” checkbox on transactions.

Future Fuel history/detail derives settlement usage from an **actual settlement line** referencing that exact `fuel_transaction.id`.

When consumed by a generated/approved settlement, Fuel may display:

- ✓
- **Settlement #XXXX** (clickable → settlement detail for verification)

---

## C3. “Settled” does not mean provider paid

Fuel UI settlement indicator means:

> this Fuel transaction was included in a driver / O/O **settlement** (deduction or charge allocation).

It does **not** mean:

- provider invoice paid
- credit card paid
- settlement itself fully paid

Settlement **payment** status remains owned by the Settlement module.

---

## C4. Settlement eligibility is per transaction

Do **not** decide settlement visibility only from “company driver vs owner-operator” at person level.

Eligibility is **transaction-specific**. Future decision chain:

```text
Fuel transaction
    → category
    → unit ownership at transaction date
    → responsible payee
    → agreement / deduction policy
    → settlement eligibility
```

---

## C5. Company driver rules (future policy)

For company-owned truck / company driver (indicative defaults; full policy TBD):

| Category | Typical treatment | Settlement UI |
|----------|-------------------|-----------------|
| Normal FUEL | Company expense; not deducted from driver | No settlement checkmark/link |
| Normal DEF | Company expense; not deducted from driver | No settlement checkmark/link |
| CASH_ADVANCE | Driver received company money; payroll/settlement relevant | ✓ + settlement # when consumed |

Other categories follow future policy — do not hardcode all behaviors here.

---

## C6. Owner-operator rules (future policy)

For owner-operated units:

- **CASH_ADVANCE** — settlement relevant.
- **FUEL** — may be settlement-deductible if O/O agreement says O/O pays fuel.
- Other categories (e.g. TOLL, PRODUCT_PURCHASE, REPAIR_OR_SERVICE, PARKING) may be deductible per **agreement**, not assumed globally.

Owner **agreement / policy** controls eligibility.

---

## C7. O/O truck with another driver

An owner-operator may own a unit while another driver operates it.

Settlement responsibility follows **unit ownership / responsible payee / agreement**, not automatically the driver snapshot on the transaction.

Historical ownership at **transaction date** must eventually be respected.

---

## C8. Anti-double-deduction

A single Fuel transaction must not be consumed by two active/final settlement deductions for:

```text
source_type = FUEL_TRANSACTION
source_id   = fuel_transaction.id
```

unless an explicit **reversal**, **adjustment**, or **void/reissue** chain exists.

Enforcement belongs in the future settlement engine — not in Fuel Process.

---

## C9. Future Fuel history / compact transaction settlement status (NOT implemented)

**Do not build** this column in Fuel until the Settlement module exists and can emit real settlement lines.

### Meaning of the indicator

| UI | Meaning |
|----|---------|
| *(empty)* | Not settlement-relevant (e.g. company **FUEL** / **DEF** on company expense — no fake status) |
| **Pending** | Settlement-relevant **candidate** (`settlement_deduction_candidate = TRUE`) but **no** settlement line yet references this `fuel_transaction.id` |
| **✓ SET-10452** (clickable) | An actual settlement line references this exact `fuel_transaction.id`; link opens **read-only** settlement / invoice detail |

The **✓** means **included/consumed by Payroll/O/O Settlement** — not provider paid, not Fuel invoice paid, not settlement payment cleared.

### Eligibility (Fuel-owned, already persisted)

- Use `fuel_transactions.settlement_deduction_candidate` and financial responsibility — do not infer from person type alone.
- Non-candidates must **not** show **Pending**.

### Examples (future only)

```text
O/O settlement-relevant FUEL (not yet on a settlement):
  Sep 12  FUEL  441.80  Pending

After consumption:
  Sep 08  FUEL  425.70  ✓ SET-10452

Company driver company FUEL:
  Sep 08  FUEL  425.70  (no column / no status)

Cash advance (settlement-relevant):
  Sep 09  CASH_ADVANCE  100.00  Pending
  → later: ✓ SET-20113
```

### Relation to compact Recent Activity table

The **Recent Activity expanded transaction table** (`BvdTransactionRowsTable`) shows **source money only** today (discount + applicable taxes). A future **Settlement** column may be added beside operational columns under this rule — **not** in the current Fuel milestone.

Do **not** implement checkmarks, **Pending**, or links until Settlement generation and `settlement_line → fuel_transaction.id` evidence exist.
