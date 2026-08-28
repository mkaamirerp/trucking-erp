# Decision 0002: Driver Phones

**Status:** **IMPLEMENTED — driver-scoped operational phone model; not universal person-contact authority.**

**Context:** A driver can have multiple phone numbers. The current code has a `driver_phones` table/model and driver-phone API surface.

## Decision

Driver-scoped phone records live in `driver_phones` with fields including:

- `driver_id`
- `phone`
- optional `label`
- optional `extension`
- `is_primary`
- `is_verified`
- `is_active`
- deactivation metadata / notes

## Current boundary

TruckERP is now **people-first**. `Person` / onboarding identity and contact data are broader company-person concerns, while `driver_phones` is a driver/operational extension tied to the dispatch-facing `drivers` row.

Do **not** interpret this ADR as saying every person's canonical contact information must live in `driver_phones`.

## Code truth

Current model: `app/models/driver_phone.py` (`DriverPhone`, table `driver_phones`).

Any future migration from driver-scoped phone records to a generalized people-contact model requires a separate explicit decision; do not silently repurpose this table.
