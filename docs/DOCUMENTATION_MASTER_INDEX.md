# TruckERP — documentation master index

**Purpose:** Single navigation map so design and operator docs are not lost in `docs/`.  
**Does not** replace underlying documents — always open the linked file for full detail.

**Docs landing page:** [`README.md`](./README.md) (this file is the **master tracker** for major design topics).

---

## Load, email intake, documents, parser

| Title | Path | Description |
|------|------|-------------|
| **Email Intake Filtering and Load Intake Safety** | [`email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md`](./email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md) | Cross-provider design/report for filtering email intake before Load Intake. Defines current behavior, target A/B/C/D/E classifier routing, broker/domain/reference signals, human review, and hard safety boundaries preventing email intake from creating final loads, trips, dispatch, assignments, payroll, custody, or driver packages. |
| **Async Load Page Parse Job Design** | [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](./load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md) | Design note for moving the real Load Page PDF parser from a blocking synchronous request to an async parse job with POST job creation, worker execution, GET polling, SHA256 reuse, and unchanged LoadDocumentParseResponse hydration. Preserves parser behavior and prevents parse jobs from creating loads, trips, dispatch, assignments, payroll, custody, or driver packages. |
| Gmail automatic ingestion (definition of done) | [`GMAIL_AUTOMATIC_INGESTION.md`](./GMAIL_AUTOMATIC_INGESTION.md) | Gmail Pub/Sub + watch **definition of done** and proof checklist. |
| Broker / email intake — QR design | [`BROKER_EMAIL_INTAKE_QR_DESIGN.md`](./BROKER_EMAIL_INTAKE_QR_DESIGN.md) | QR-derived intake metadata (lineage, audit, broker/load linkage). |
| Trip container — Load Page + parser integration map | [`TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md`](./TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md) | Load Page vs parser vs Lab; canonical `LoadWorkspaceForm` boundaries. |
| Current PDF load paths and gaps | [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) | Where PDFs are parsed today (workspace vs email thread vs Lab) and gaps. |

---

## Trip execution, custody, dispatch (separate spine)

| Document | When to read |
|----------|----------------|
| [`TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`](./TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md) | **Approved** reading order and supporting references for trip execution, custody, assignment, load workspace decisions **6–13**, and related DDL/payroll docs. |

---

## Engineering and platform

| Document | When to read |
|----------|----------------|
| [`ENGINEERING_PLAYBOOK.md`](./ENGINEERING_PLAYBOOK.md) | Required before new modules/routes/models; tenant and ops guardrails. |
| [`ENGINEERING_CHECKLIST.md`](./ENGINEERING_CHECKLIST.md) | Short deploy/verify checklist. |
| [`trucking_erp_blueprint.md`](./trucking_erp_blueprint.md) | Canonical product/architecture blueprint. |
| [`DATABASES_PLATFORM_AND_DEMO.md`](./DATABASES_PLATFORM_AND_DEMO.md) | Platform vs tenant DB mental model. |
| [`db_schema/README.md`](./db_schema/README.md) | Generated schema dumps (regeneration instructions). |

---

## Cursor / AI rules (repo)

Operational and architecture locks for agents and humans live under **`.cursor/rules/`** (e.g. Gmail delta ingestion, tenant migrations, SSM guards). This index lists **`docs/`** markdown only; open `.cursor/rules` when editing matching paths.

---

*Add new cross-cutting design reports here under the appropriate section so they stay discoverable.*
