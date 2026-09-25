# TruckERP Fuel Card Adjustments

**Status:** Design / future implementation. Not part of BVD Implementation 1 source-review acceptance.

**Related architecture:** `docs/FUEL_CARD_MODULE_DESIGN.md`

**Execution plan:** `docs/FUEL_CARD_IMPLEMENTATION_PLAN.md`

**Implementation checklist:** `docs/FUEL_CARD_ADJUSTMENTS_TODO.md`

---

# 1. Purpose

Fuel Card Adjustments handle **provider-authorized corrections made after an original fuel-card charge already exists in TruckERP**.

Typical example:

```text
BVD original charge        950.00
Company disputes discount / fuel price with BVD
BVD agrees and corrects     920.00
Provider adjustment         -30.00
```

This workflow is between the **fuel-card provider** and the **fleet/company account** (for example IK Logistics).

It is **not a driver dispute workflow** and it is **not an owner-operator dispute workflow**.

Driver or owner-operator relationships may matter later only if a separate downstream allocation/settlement rule consumes the corrected company fuel cost.

---

# 2. Non-negotiable accounting rule

The original provider transaction is immutable.

TruckERP must never rewrite the historical source transaction simply because BVD, WEX, Comdata, Nationwide, or another provider later issues a correction.

```text
ORIGINAL PROVIDER CHARGE
        ↓
immutable source/history

PROVIDER CORRECTION
        ↓
new linked adjustment record

EFFECTIVE COST
        = original charge + all accepted provider adjustments
```

If an old accounting/settlement period is already closed or paid, TruckERP records the provider adjustment in the current period rather than silently rewriting the closed history.

---

# 3. Fuel menu / workflow entry

Provide a dedicated workflow:

```text
Fuel
 └── Fuel Card Adjustments
      ├── New Adjustment
      ├── Pending
      ├── Completed
      └── Adjustment History
```

The primary user is a tenant/company admin or other RBAC-authorized finance/fuel reviewer.

---

# 4. Guided adjustment search

The workflow should begin with **search**, not a long manual form.

The company owner may only know one fact, for example:

```text
Invoice 112765
```

First screen:

```text
Fuel Card Adjustment

Search provider records

Invoice / Auth Code / Card / Amount / Date / Unit
[ 112765                                      ]

[ Search ]
```

Search should support progressively narrowing the dispute using available provider evidence.

Searchable identifiers should include, where available:

- provider;
- invoice number;
- provider transaction/auth code;
- fuel-card/account number;
- unit number;
- transaction date/date range;
- original amount;
- merchant/site;
- provider credit/rebill reference.

The user should **not** be forced to know every identifier before TruckERP helps find the disputed charge.

---

# 5. Guided questions after invoice match

If invoice `112765` is found, show the provider invoice summary first, then ask what is being disputed.

Example:

```text
Invoice 112765 found

Provider: BVD
Invoice Date: ...
Card(s): ...
Transactions: ...
Invoice Total: ...

What is the issue?

○ Entire invoice
○ One transaction
○ Fuel price
○ Discount
○ Tax
○ Quantity
○ Duplicate charge
○ Incorrect product
○ BVD credit
○ BVD rebill
○ Other
```

The next question depends on the answer.

If the user chooses `One transaction`, `Fuel price`, `Discount`, `Tax`, `Quantity`, or another transaction-level issue, TruckERP should present the matching invoice transactions and let the user select the disputed transaction.

Example:

```text
Which transaction?

Unit | Card | Auth | Date | Site | Amount
...
```

This is a guided investigation flow, not a single giant adjustment form.

---

# 6. Confirm the original transaction before adjustment

After narrowing to the disputed record, show the exact provider evidence already stored in TruckERP.

Example:

```text
FOUND TRANSACTION

Provider:        BVD
Invoice:         972201
Card:            4237111
Auth Code:       A204040667-TA
Date:            2026-07-23 02:17:56
Unit:            1100
Site:            BOWMANVILLE
QTY:             719.50
Billed Price:    2.2390
Pre Tax:         1,425.63
HST:               185.33
Discount:            0.00
Final Amount:    1,610.96 CN

[ This is the transaction ] [ Search again ]
```

Do not create an adjustment against a guessed transaction.

---

# 7. Capture what the provider corrected

Once the original charge is confirmed, ask what BVD/provider changed.

Adjustment reasons should include at minimum:

```text
FUEL_PRICE_CORRECTION
DISCOUNT_CORRECTION
TAX_CORRECTION
QUANTITY_CORRECTION
DUPLICATE_CHARGE
INCORRECT_PRODUCT
PROVIDER_CREDIT
PROVIDER_REBILL
OTHER
```

Show original provider values beside corrected provider values.

Example:

```text
                         ORIGINAL       CORRECTED
QTY                       719.50          719.50
Billed Price               2.2390          2.1990
Pre Tax Amount           1,425.63        1,396.85
HST                        185.33          181.59
Discount                     0.00           20.00
Final Amount             1,610.96        1,558.44
```

TruckERP computes the adjustment delta:

```text
original amount       1,610.96
corrected amount      1,558.44
--------------------------------
provider adjustment     -52.52 CN
```

The provider correction may be either a credit or an additional charge.

---

# 8. Provider evidence for the correction

The adjustment must retain evidence of what the provider agreed to change.

Capture where available:

```text
provider adjustment / credit reference
provider adjustment date
corrected invoice / credit memo / rebill number
provider case/reference number
notes
attachment / provider email / credit memo / corrected statement
source import / API payload reference
```

Provider API/CSV/PDF evidence remains immutable and auditable.

---

# 9. Confirmation gate

Before recording the adjustment, show an explicit final confirmation.

Example:

```text
BVD FUEL CARD ADJUSTMENT

Original transaction:
Invoice 972201
Auth A204040667-TA
Card 4237111

Original amount        1,610.96 CN
Corrected amount       1,558.44 CN
Adjustment               -52.52 CN

Reason:
Fuel price / discount correction

This will NOT modify the original BVD source record.

[ Cancel ] [ Record Adjustment ]
```

No silent edit is allowed.

---

# 10. Conceptual adjustment record

Final schema is intentionally not locked by this design document, but the adjustment model must preserve the following concepts:

```text
id
tenant_id
provider
original_provider_record_id / source record reference
original_import_id / source document reference
invoice_number
card_or_account_reference
provider_transaction_id / auth_code
unit_number snapshot if useful for search/audit
transaction_date snapshot
adjustment_reason
original_amount
corrected_amount
delta_amount
currency
provider_reference
provider_adjustment_date
evidence_storage_ref / source reference
notes
status
created_by
created_at
approved_by nullable
approved_at nullable
```

Important:

- `original_amount` is a historical snapshot for the adjustment;
- `corrected_amount` is the provider-authorized corrected amount;
- `delta_amount = corrected_amount - original_amount` for the relevant effective charge basis;
- the original provider source row remains unchanged;
- later financial posting must preserve the link from adjustment back to the original provider transaction and provider correction evidence.

Do not infer final table names/migrations from this conceptual list without reviewing the canonical Fuel/GL design at implementation time.

---

# 11. Effective-cost view

TruckERP should be able to show the company a simple history:

```text
Jul 23   BVD Fuel Charge          1,610.96
Sep 25   BVD Adjustment             -52.52
         ↳ adjusts Jul 23 transaction
-------------------------------------------
Effective company fuel cost       1,558.44
```

Multiple provider adjustments may exist against the same original transaction.

Therefore effective amount is conceptually:

```text
original provider amount
+ accepted adjustment 1
+ accepted adjustment 2
+ ...
= current effective provider cost
```

Do not collapse the chain into a destructive overwrite.

---

# 12. Open vs closed financial history

Two cases must be handled differently.

## 12.1 Original charge not yet financially finalized

If the original charge has not yet entered a closed/finalized financial period, downstream company cost may use the effective corrected amount once the provider adjustment is accepted.

Original provider evidence remains unchanged.

## 12.2 Original charge already finalized / closed

Do not reopen or silently rewrite the closed record.

Record the provider adjustment as a new financial adjustment in the appropriate current period, linked back to the original provider charge.

Exact GL/settlement posting mechanics remain part of the later canonical financial phase and must follow TruckERP's no-silent-money-edit rules.

---

# 13. API / CSV / PDF correction sources

Provider corrections may arrive through different channels:

```text
API revised transaction / adjustment event
CSV export / adjustment file
revised invoice
credit memo
rebill
provider email / case confirmation
manual admin entry backed by provider evidence
```

Preferred source hierarchy remains:

```text
usable authorized API
    -> structured provider export / CSV
        -> digital PDF / provider document
            -> manual evidence-backed entry
```

The provider source itself does not get overwritten when a later source disagrees. TruckERP stores the new adjustment evidence and links it to the original transaction.

---

# 14. Provider-source conflict

If BVD/provider sends conflicting correction evidence, do not silently choose one.

Examples:

```text
API corrected amount: 920.00
CSV corrected amount: 920.00
credit memo amount:   950.00
```

or

```text
credit memo references invoice A
manual entry references invoice B
```

Flag for review before financial acceptance.

Potential status:

```text
PROVIDER_SOURCE_CONFLICT
```

---

# 15. RBAC / audit

Fuel adjustments move money and require explicit authorization.

At implementation time define permissions for at least:

```text
fuel.adjustment.view
fuel.adjustment.create
fuel.adjustment.approve
```

Consider separating create and approve for larger fleets.

Every adjustment must retain:

- tenant;
- user identity;
- timestamps;
- reason;
- provider evidence/reference;
- original provider record link;
- approval status/history where required.

No cross-tenant lookup or adjustment is allowed.

---

# 16. Idempotency / duplicate protection

Provider adjustments may be received more than once through API retries, duplicate CSV uploads, revised statements, or repeated manual entry.

Implementation must define an idempotency strategy using provider identifiers/evidence where available.

TruckERP must prevent the same provider credit from being applied twice.

---

# 17. Reversal / correction of a TruckERP adjustment

If a TruckERP user records an adjustment incorrectly, do not delete or silently edit an already-approved financial adjustment.

Use an audited reversal/correcting adjustment according to the financial state of the record.

Draft/unapproved adjustment edit rules may be more permissive, but approved history remains auditable.

---

# 18. Out of scope for the current BVD review milestone

This adjustment workflow is **not part of BVD Implementation 1 source extraction/review acceptance**.

Do not pull it into the current BVD PDF mirror/review work.

It belongs to later Fuel operationalization after provider source fidelity is accepted.

Current BVD review work remains:

```text
source fidelity
side-by-side review
append-only field correction overlay
source review completion
```

Fuel Card Adjustments are a separate later workflow for **provider-authorized post-charge corrections**.

---

# 19. Implementation reference

See:

`docs/FUEL_CARD_ADJUSTMENTS_TODO.md`

for the implementation checklist and sequencing.
