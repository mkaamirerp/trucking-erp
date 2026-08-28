# Email-related documentation

This folder contains the **current email-intake safety and ownership lock**.

## Current document

- [`EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md`](./EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md) — current provider-neutral intake/review boundary, Load creation safety rules, and the relationship to the **one shared Document Parser pipeline with attached profiles**.

## Key rules

- Email Intake owns message/thread/attachment ingestion, relevance routing, review, and provenance.
- Email Intake calls the shared Document Parser for selected document semantics; it does **not** own a second Rate Confirmation parser.
- Rate Confirmation v2 is the first shipped Document Parser profile.
- `LoadWorkspaceForm` is the canonical production Load verification/edit surface.
- Passive email/PDF intake must not create Trips, dispatch assignments, custody, payroll, settlement, or other execution truth.
- The full A/B/C/D/E relevance classifier remains future work; do not document it as shipped.

## Related current docs

See **Load, email intake, documents, parser** in [`../DOCUMENTATION_MASTER_INDEX.md`](../DOCUMENTATION_MASTER_INDEX.md), especially:

- `../TruckERP_Shared_Document_Parsing_Architecture.md`
- `../CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`
- `../GMAIL_AUTOMATIC_INGESTION.md`
- `../BROKER_EMAIL_INTAKE_QR_DESIGN.md`

The older detailed mixed current/target report is preserved in `../archive/email/` for historical research only.
