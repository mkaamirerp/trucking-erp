# TruckERP Entity Field / Type-Ahead Standard

This is a project-wide UX rule for TruckERP.

## Core rule

Whenever a form field represents an existing database-backed business entity, use a searchable type-ahead/select field rather than a traditional large dropdown.

Examples include:
- Broker
- Broker Contact
- Customer
- Driver
- Truck
- Trailer
- Facility / shipper / receiver
- Other managed master-data entities where selection of an existing record matters

Do NOT apply this rule to ordinary scalar fields such as rate, miles, weight, load/reference number, dates, times, free-text notes, etc.

## Required interaction

1. There must be ONE user-facing field for the entity.
2. On click/focus, show up to the top/relevant/recent 10 records immediately.
3. As the user types, results must update live based on the entered text.
4. The user chooses the correct record from the result list.
5. Keyboard navigation may support Up/Down + Enter, but selection is the confirmation action.
6. Do not require Excel-style Tab-to-accept behavior.
7. On touch devices the same field must work by tap and selection.
8. Do not load or display hundreds/thousands of records in a traditional select dropdown.

## Stored value vs displayed value

The visible field displays the human-readable entity name.

The application stores the corresponding entity ID/reference internally.

Backend/parser snapshot fields may exist for extraction, audit, matching, or diagnostics, but they must NOT create duplicate user-facing fields.

Example for Broker:

Backend may retain:
- broker_id
- broker_name_snapshot
- broker_mc_number_snapshot
- broker_dot_number_snapshot

User sees only:
- Broker

## Parser / automatic resolution

When AI/document parsing provides strong identity evidence and TruckERP can resolve it to an existing database record, automatically select that record in the same entity field.

For Broker:
- MC/DOT exact identity resolution may automatically populate broker_id.
- broker_name_snapshot remains source evidence.
- Do not expose Broker + Broker Name as two normal user-facing fields.

If automatic identity resolution does not produce a trusted record:
- leave the single entity field available for user search/selection
- do not invent or force a database relationship from snapshot text alone

## Reusability

Do not create custom autocomplete behavior separately on each page.

Use/reuse a shared TruckERP type-ahead/search-select component and consistent API/query behavior wherever practical.

Behavior should be consistent throughout the ERP:

focus -> top 10 -> type -> live search -> select -> store entity ID.

## Existing-data rule

The field must remain usable even when the desired entity is not in the initial top 10. Typing must search beyond those initial records.
