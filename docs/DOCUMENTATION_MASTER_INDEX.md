# TruckERP — documentation master index

**Purpose:** Curated navigation map for the current authoritative documentation. This index does not replace the underlying documents.

**Docs landing page:** [`README.md`](./README.md)

Historical handoffs, superseded implementation reports, and one-off snapshots belong under [`archive/`](./archive/README.md) and are not current production guidance.

---

## Load, email intake, documents, parser

| Title | Path | Description |
|------|------|-------------|
| **Email Intake Filtering and Load Intake Safety** | [`email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md`](./email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md) | Cross-provider filtering and safety boundaries before Load Intake. |
| **Async Load Page Parse Job Design** | [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](./load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md) | Async parse-job design preserving the existing LoadDocumentParseResponse/hydration contract. |
| Gmail automatic ingestion | [`GMAIL_AUTOMATIC_INGESTION.md`](./GMAIL_AUTOMATIC_INGESTION.md) | Gmail Pub/Sub + watch definition of done and proof checklist. |
| Broker / email intake — QR design | [`BROKER_EMAIL_INTAKE_QR_DESIGN.md`](./BROKER_EMAIL_INTAKE_QR_DESIGN.md) | QR-derived intake metadata, lineage, audit, and broker/load linkage. |
| Trip container — Load Page + parser integration map | [`TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md`](./TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md) | Load Page vs parser vs Lab boundaries. |
| Current PDF load paths and gaps | [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) | Where PDFs are parsed today and known gaps. |

---

## Trip execution, custody, dispatch

| Document | When to read |
|----------|--------------|
| [`TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`](./TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md) | Approved reading order for trip execution, custody, assignment, load workspace decisions, DDL, and payroll-related trip docs. |

---

## Engineering and platform

| Document | When to read |
|----------|--------------|
| [`ENGINEERING_PLAYBOOK.md`](./ENGINEERING_PLAYBOOK.md) | Required engineering and tenant/ops guardrails. |
| [`ENGINEERING_CHECKLIST.md`](./ENGINEERING_CHECKLIST.md) | Short deploy/verify checklist. |
| [`trucking_erp_blueprint.md`](./trucking_erp_blueprint.md) | Canonical product/architecture blueprint. |
| [`DATABASES_PLATFORM_AND_DEMO.md`](./DATABASES_PLATFORM_AND_DEMO.md) | Platform vs tenant DB mental model. |
| [`TENANT_SAFETY_EXECUTION_RUNBOOK.md`](./TENANT_SAFETY_EXECUTION_RUNBOOK.md) | Tenant-safe operational execution. |
| [`db_schema/README.md`](./db_schema/README.md) | Generated schema dumps and regeneration instructions. |

---

## Historical documentation

Archived material is retained for reasoning history and incident context, but must not override current runbooks, locks, contracts, or `.cursor/rules/`.

See [`archive/README.md`](./archive/README.md).

---

## Cursor / AI rules

Operational and architecture locks for agents and humans live under **`.cursor/rules/`**. Check the matching rules before editing protected areas such as tenant migrations, SSM/config, login/security, onboarding, Gmail ingestion, or the Load PDF parser.

---

## Maintenance rule

Prefer updating an existing canonical document over creating another top-level implementation report or handoff. Add a new item here only when it represents a durable documentation spine that future work should actively consult.
