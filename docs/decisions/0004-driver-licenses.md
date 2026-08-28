# Decision 0004: Driver Licenses (CA/US, endorsements, restrictions)

**Status:** **DESIGN-ONLY / NOT IMPLEMENTED AS THIS NORMALIZED TABLE SET.**

**Context:** License classes differ by country/jurisdiction (for example CA AZ/DZ/G and US CDL A/B/C), and endorsements/restrictions may be jurisdiction-aware.

## Historical proposed design

The early ADR proposed normalized tables:

1. `driver_licenses`
   - country
   - province/state
   - license number
   - license class
   - issue/expiry dates
   - primary/active state

2. `license_endorsements` + `driver_license_endorsements`

3. `license_restrictions` + `driver_license_restrictions`

## Current reality

Those normalized table names are **not implemented in the current repo**. Driver/onboarding documents and profile data exist through newer people-first onboarding/driver-extension work, but this exact relational design was never shipped.

The business requirement remains useful: license data must support CA/US jurisdiction differences and future endorsement/restriction handling. The exact schema must be decided in a current implementation slice against the people-first model; do not create these tables solely because this older ADR says "Decision."
