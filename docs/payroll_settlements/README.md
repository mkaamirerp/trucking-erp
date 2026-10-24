# Payroll / Settlements

Driver pay, owner-operator settlement, pay runs, and settlement liability/payment.

## Locked decisions

| Document | Purpose |
|----------|---------|
| [`SETTLEMENT_RATE_OWNER_DECISION_2026-10-24.md`](./SETTLEMENT_RATE_OWNER_DECISION_2026-10-24.md) | Broker `rate` vs settlement `customer_rate`, effective rate, O/O vs company driver, finalize immutability |
| [`SETTLEMENT_RATE_PAYROLL_LOAD_CHAIN_REPORT_2026-10-24.md`](./SETTLEMENT_RATE_PAYROLL_LOAD_CHAIN_REPORT_2026-10-24.md) | Read-only load → pay run chain, current code behavior, snapshot options |

## Related

- [`PAYROLL_OO_FUEL_SETTLEMENT_LINKAGE.md`](./PAYROLL_OO_FUEL_SETTLEMENT_LINKAGE.md) — fuel deduction timing vs settlement
- [`HR_PAYROLL_ONBOARDING_LOGIC_ANCHOR.md`](./HR_PAYROLL_ONBOARDING_LOGIC_ANCHOR.md) — onboarding / compensation entry points
- Load commercial semantics: [`../load_trip/MASTER.md`](../load_trip/MASTER.md), [`.cursor/rules/owner-product-rules.mdc`](../../.cursor/rules/owner-product-rules.mdc)
