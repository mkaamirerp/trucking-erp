# Email-related documentation

Index of email ingestion, intake, and broker-mail design docs (links only).

---

## Design / safety

| Title | Document |
|------|----------|
| **Email Intake Filtering and Load Intake Safety** | [`EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md`](./EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md) |

**Summary:** Cross-provider design/report for filtering email intake before Load Intake. Defines current behavior, target A/B/C/D/E classifier routing, broker/domain/reference signals, human review, and hard safety boundaries preventing email intake from creating final loads, trips, dispatch, assignments, payroll, custody, or driver packages.

---

## Related (`docs/` root)

See **Load, email intake** in [`../DOCUMENTATION_MASTER_INDEX.md`](../DOCUMENTATION_MASTER_INDEX.md) for Gmail automatic ingestion, QR intake, Load Page/parser map, and PDF paths.
