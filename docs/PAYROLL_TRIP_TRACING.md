# Payroll trip / load tracing (pay run line items)

## What gets stored

When a pay run is **generated**, each `PayRunItem` may include `metadata_json` used only for **tracing and UI/export** (not for payroll calculation or ownership).

- **`reference_code`** — Always copied from `PayEntry.reference_code` when it is non-empty after trim. This is the portable tracing string operators can rely on in pay-run screens and CSV exports.
- **`load_id`, `trip_number`, `dispatch_trip_id`** — Optional enrichments from the tenant **`loads`** read-model when a load can be resolved for that entry.

## Transitional resolution rule (current implementation)

**This is an interim convention, not the final design.**

Trip-related fields are filled only when:

1. `PayEntry.reference_code` is **entirely numeric** (after trim), and  
2. that value equals a **`loads.id`** for the same tenant.

In that case, the generator attaches `load_id`, and from that row `trip_number` and `active_dispatch_trip_id` (as `dispatch_trip_id`) when present.

`reference_code` is a **general-purpose** field (broker refs, memos, etc.). Many valid values are not load IDs. **Do not assume** “numeric `reference_code` means load id” in product logic or documentation beyond this transitional bridge.

## Intended direction (follow-up)

Tighten tracing without overloading `reference_code`:

- Resolve loads/trips using **trip_number** (and/or other explicit keys) when entries are keyed that way.
- Prefer an **explicit** link from pay entries to business objects (e.g. load id or dispatch trip id on `pay_entries`, or structured metadata) **after** tracing rules are agreed — not as a speculative schema change.

## Issue / exception linkage (Phase B)

Explicit `dispatch_trip_id` on notes or other exception artifacts is **out of scope** until product needs it; Phase A continues to rely on load payload / read-model for trip display.

## Related product decisions (non-payroll)

Future **driver-facing pay display**, **settlement basis** vs **broker/ratecon accounting truth**, and **what the driver sees** on the dispatch package may interact with pay-run **tracing** and exports. See **`DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md`** (**draft**, **not locked**) — especially **financial visibility** and **two pay branches** — before assuming tracing metadata should expose broker gross or internal-only amounts.

## Related code

- `app/routers/pay_runs.py` — `generate_pay_run`, `_pay_run_item_metadata`
- `apps/web/src/pages/PayRunDetailPage.tsx` — trip / reference columns and CSV export
