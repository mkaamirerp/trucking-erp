# Decision 0004: Driver Licenses (CA/US, endorsements, restrictions)
**Status:** Active  
**Context:** License classes differ by country (CA: AZ/DZ/G, US: CDL A/B/C). Endorsements and restrictions are jurisdiction-aware.

## Decision
Use normalized license tables:
1) `driver_licenses` (one driver can have multiple)
- country (CA/US)
- province_state
- license_number
- license_class
- issue_date (optional)
- expiry_date
- is_primary
- is_active

2) Endorsements:
- `license_endorsements` (code, description, country, optional province_state)
- `driver_license_endorsements` join table

3) Restrictions:
- `license_restrictions` (code, description, country, optional province_state)
- `driver_license_restrictions` join table (or embedded later)

## Implications
- UI will offer country-specific class/endorsement lists
- Compliance reporting depends on this structure

