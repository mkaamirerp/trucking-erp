# TruckERP Fuel Card Adjustments — TODO

**Status:** TODO / future Fuel operationalization. Do not implement during BVD Implementation 1 source-review acceptance.

**Design:** `docs/FUEL_CARD_ADJUSTMENTS.md`

**Architecture:** `docs/FUEL_CARD_MODULE_DESIGN.md`

**Execution plan:** `docs/FUEL_CARD_IMPLEMENTATION_PLAN.md`

---

# Implementation sequence

## A. Search / guided-dispute workflow

- [ ] Add Fuel → Fuel Card Adjustments entry.
- [ ] Add New Adjustment / Pending / Completed / Adjustment History views.
- [ ] Start with a single broad search box.
- [ ] Search by invoice number, auth/provider transaction id, card/account, unit, amount, date/range, merchant/site, provider reference.
- [ ] Allow partial knowledge: user should not need every identifier up front.
- [ ] After invoice match, ask what is wrong: entire invoice / one transaction / fuel price / discount / tax / quantity / duplicate / product / provider credit / rebill / other.
- [ ] Dynamically narrow to the disputed transaction or invoice-level charge.
- [ ] Require explicit confirmation of the original provider record before adjustment creation.

## B. Provider correction capture

- [ ] Support adjustment reasons: FUEL_PRICE_CORRECTION, DISCOUNT_CORRECTION, TAX_CORRECTION, QUANTITY_CORRECTION, DUPLICATE_CHARGE, INCORRECT_PRODUCT, PROVIDER_CREDIT, PROVIDER_REBILL, OTHER.
- [ ] Show original values beside corrected provider-authorized values.
- [ ] Calculate original amount, corrected amount, currency, and signed delta.
- [ ] Support both provider credits and additional charges.
- [ ] Capture provider adjustment date, case/reference, credit memo/rebill/corrected invoice reference, notes, and evidence attachment/source reference.
- [ ] Add explicit final confirmation: original source will not be modified.

## C. Data model / persistence

- [ ] Inspect current canonical Fuel/GL models before naming any new table.
- [ ] Add a provider-adjustment entity linked to the immutable original provider transaction/source record.
- [ ] Preserve original amount snapshot, corrected amount, delta, currency, reason, provider reference, evidence reference, created/approved metadata.
- [ ] Allow multiple adjustments against one original transaction.
- [ ] Preserve the full adjustment chain; do not collapse into an overwrite.
- [ ] Add tenant isolation constraints.
- [ ] Add provider/source linkage constraints.
- [ ] Add idempotency / duplicate-credit protection.
- [ ] Define draft vs approved vs reversed status behavior.

## D. Accounting behavior

- [ ] If original charge is not financially finalized, use effective corrected cost downstream without mutating source evidence.
- [ ] If original charge is already in a closed/finalized period, create a new current-period adjustment; never rewrite closed history.
- [ ] Preserve traceability from company financial adjustment back to original provider transaction and correction evidence.
- [ ] Define GL posting only during the later canonical financial phase.
- [ ] Add audited reversal/correcting-adjustment flow for erroneous TruckERP adjustments.

## E. Provider-source handling

- [ ] Accept adjustment evidence from API, CSV/export, revised invoice, credit memo, rebill, provider case/email, or evidence-backed manual entry.
- [ ] Prefer usable authorized API over CSV/export, PDF, and manual entry.
- [ ] Store original provider payload/document evidence unchanged.
- [ ] Detect conflicts between API/CSV/PDF/manual correction evidence.
- [ ] Add PROVIDER_SOURCE_CONFLICT review state or equivalent.
- [ ] Block financial acceptance while provider correction evidence is unresolved.

## F. RBAC / audit

- [ ] Define `fuel.adjustment.view`.
- [ ] Define `fuel.adjustment.create`.
- [ ] Define `fuel.adjustment.approve`.
- [ ] Consider creator/approver separation for larger fleets.
- [ ] Audit tenant, user, reason, timestamps, evidence, original-record link, approval/reversal history.
- [ ] Prove cross-tenant search and adjustment creation are blocked.

## G. UI acceptance scenarios

- [ ] Search only `invoice 112765` and successfully narrow the dispute through guided questions.
- [ ] Search by auth code only.
- [ ] Search by card/account only.
- [ ] Search by unit + date.
- [ ] Search by approximate/original amount where supported.
- [ ] Correct fuel price and verify delta.
- [ ] Correct discount and verify delta.
- [ ] Record tax correction and verify delta.
- [ ] Record provider credit.
- [ ] Record provider rebill/additional charge.
- [ ] Show effective company cost as original charge + adjustment chain.
- [ ] Show provider evidence/reference from adjustment history.

## H. Test gates

- [ ] Original provider row/file/payload remains unchanged after adjustment.
- [ ] Same provider credit cannot be applied twice.
- [ ] Multiple legitimate adjustments can link to one original transaction.
- [ ] Credit delta sign is correct.
- [ ] Additional-charge delta sign is correct.
- [ ] Currency mismatch cannot silently pass.
- [ ] Unknown original transaction cannot be adjusted by guess.
- [ ] Provider-source conflict blocks acceptance.
- [ ] Closed financial history is not rewritten.
- [ ] Reversal preserves original adjustment audit trail.
- [ ] Tenant A cannot search/adjust Tenant B provider records.
- [ ] RBAC prevents unauthorized create/approve actions.

---

# Explicit boundaries

Do **not** attach this work to the current BVD mirror/review milestone.

Do **not** turn a provider adjustment into a driver-dispute or owner-operator-dispute workflow.

The primary relationship here is:

```text
Fuel-card provider
        ↕
Fleet / company account
        ↕
TruckERP company financial history
```

Any later driver/O-O allocation is a separate downstream business rule.

---

# Done definition

Fuel Card Adjustments are complete only when TruckERP can:

1. find a disputed provider invoice/transaction from minimal information;
2. guide the company user to the exact original charge;
3. capture the provider-authorized correction and evidence;
4. preserve the immutable original provider record;
5. compute and store the signed adjustment delta;
6. prevent duplicate application;
7. preserve audit/tenant/RBAC controls;
8. apply later financial effects without rewriting closed history;
9. show the complete original → adjustment(s) → effective-cost chain.
