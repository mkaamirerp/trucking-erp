# Decision 0003: Emergency Contacts
**Status:** Active  
**Context:** Emergency contact is not just a name. Must support multiple contacts, phone, relationship.

## Decision
Create `driver_emergency_contacts` table:
- `driver_id`
- `name`
- `phone`
- `relationship`
- `is_primary`
- `notes` (optional)
- `is_active` (soft deactivate)

## Notes
A temporary field `emergency_contact_name` may exist on drivers for initial testing, but the table is the final design.

