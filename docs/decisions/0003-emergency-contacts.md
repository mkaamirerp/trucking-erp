# Decision 0003: Emergency Contacts

**Status:** **DESIGN-ONLY / NOT IMPLEMENTED.**

**Context:** Emergency contacts may need multiple contacts, phone, relationship, priority, notes, and activation state.

## Historical proposed design

A dedicated `driver_emergency_contacts` table was proposed with fields such as:

- `driver_id`
- `name`
- `phone`
- `relationship`
- `is_primary`
- optional `notes`
- `is_active`

## Current reality

No `driver_emergency_contacts` implementation exists in the current repo. The system's newer architecture is people-first, so any future emergency-contact implementation must first decide whether emergency contacts belong to the general `Person`/people domain or to a driver-specific extension.

This file records the original requirement, **not an approved schema task**. Do not create the table from this ADR alone.
