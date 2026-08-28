# Decision 0001: Driver Ownership / Category
**Status:** Active  
**Context:** Fleets need to distinguish company drivers vs owner-operators for payroll/settlements and reporting.

## Decision
Use a string category field (not boolean):
- `driver_category`: `company` | `owner_operator`

## Rationale
- Boolean cannot scale (leased-on, contractor, etc.)
- Clear input to payroll module

## Implications
- Payroll/settlements will branch logic based on `driver_category`
- UI may hide it but backend must store it

