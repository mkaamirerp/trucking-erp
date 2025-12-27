# Decision 0002: Driver Phones
**Status:** Active  
**Context:** Drivers can have multiple numbers (primary, secondary, emergency, work). Single phone column is insufficient.

## Decision
Phones live in a separate table (`driver_phones`) with:
- phone number fields
- label/type (mobile/home/work)
- `is_primary`
- `is_active` (soft deactivate)

## Implications
- Driver record may keep a legacy `phone` field for MVP UI, but canonical phones are in `driver_phones`
- Enforce only one active primary phone per driver (later validation)

