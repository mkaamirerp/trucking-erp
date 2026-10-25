# Settlement rate — owner decision (Amir, 2026-10-24)

**Status:** Historical settlement proposal, **superseded in part** by the later owner instruction to copy the RC rate into a blank `customer_rate` on Save/Create Load. Only storage/default behavior is approved now; downstream payroll, invoicing, settlement, and margin usage will be decided later. Sections below describe the earlier proposal and are **not implementation authorization**.

**Scope:** How broker revenue on a load relates to what an owner-operator (or settlement engine) uses as “gross” for that load. Complements load commercial fields in [`.cursor/rules/owner-product-rules.mdc`](../../.cursor/rules/owner-product-rules.mdc) and parser rules in [`TruckERP_Rate_Confirmation_AI_Handoff_Contract_v2_FULL.json`](../../app/contracts/TruckERP_Rate_Confirmation_AI_Handoff_Contract_v2_FULL.json) (`customer_rate_guardrail`).

**Related investigation:** [`SETTLEMENT_RATE_PAYROLL_LOAD_CHAIN_REPORT_2026-10-24.md`](./SETTLEMENT_RATE_PAYROLL_LOAD_CHAIN_REPORT_2026-10-24.md).

---

## 1. Broker rate (`loads.rate`)

- **`loads.rate` = broker rate:** what the broker pays the **company**. Company revenue / gross on the rate confirmation.
- **Does not change** when the settlement rate changes.
- Used for **company** revenue reporting, broker reconciliation, and commercial truth on the load.

## 2. Settlement rate (`loads.customer_rate`)

- **UI label (future):** “Settlement rate (blank = same as broker rate)”.
- **DB column and API field name remain `customer_rate`** (no rename).
- **Meaning:** the amount the **driver is settled on** for that load (owner-operator gross per load, or flat/percent basis input — not company revenue).

## 3. Effective settlement rate (single computation)

- **Formula:** `effective_settlement_rate = customer_rate` if **NOT NULL**, else `rate`.
- **Computed in ONE shared place** in application code (to be chosen at implementation time; must not be duplicated in parsers, dashboards, and payroll).
- **Never** copy `rate` into `customer_rate` to mean “same as broker” — only **NULL** means “same as broker rate”. Parser contract already forbids auto-copy (`customer_rate_guardrail`).
- **Explicit zero:** an explicit `customer_rate = 0` is **zero** settlement for that load (not “fall back to broker rate”). **Owner to confirm** this is the desired production rule before UI/validation hardening.

## 4. Company gross vs driver gross (example)

Weekly loads with broker rates **2200 / 2000 / 3000**:

| Concept | Amount |
|--------|--------|
| **Company gross** (sum of broker `rate`) | **7200** |
| First load settled at **2000** (settlement rate), others at broker rate | Driver gross **7000** |
| Spread | **200** company profit on that load |

## 5. Owner-operator pay (target model)

- **Gross:** sum of **effective settlement rates** for loads in the settlement window (example **7000**).
- **Minus:** company **dispatch fee** % (or per-mile, per driver — configured in backend / compensation setup).
- **Minus:** fuel, tolls, ELD, and other deductions per compensation and charge rules.

## 6. Company drivers

- Paid **hourly** (often city/local) or **per mile** (often long-haul).
- **Load broker/settlement amounts do not drive** their pay in this model.

## 7. Driver kinds (today)

- Two **employment relationship** types in onboarding: **company driver** vs **owner operator** (`driver_person_extensions.employment_relationship_type`).
- Each has its own **gross calc type** / rate model in **driver compensation setup** (`compensation_profiles.gross_calc_type`, legacy `pay_profiles` for manual pay entries).

## 8. Finalized pay runs (immutability)

- **Settled amounts are a SNAPSHOT** at pay-run **finalize**.
- Changing `loads.rate` or `loads.customer_rate` **after** finalize must **not** silently change amounts on a **FINALIZED** pay run.

## 9. RBAC and reporting (deferred)

- **Who may edit settlement rate and when:** decided later by RBAC.
- **Settlement / profitability reports:** separate later module (out of scope for this decision).

---

## Implementation notes (non-binding)

- Until the shared “effective settlement rate” helper exists, treat **`sum(Load.rate)`** in dashboards as **broker revenue**, not driver settlement gross.
- UI relabel of `customer_rate` is a **frontend-only** change; API and migrations keep `customer_rate`.
