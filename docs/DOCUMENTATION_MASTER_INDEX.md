# TruckERP — documentation master index

**Purpose:** Single navigation map so design and operator docs are not lost in `docs/`.  
**Does not** replace underlying documents — always open the linked file for full detail.

**Docs landing page:** [`README.md`](./README.md) (this file is the **master tracker** for major design topics).

## Trust / precedence rule

When two documents conflict, prefer the **newer explicit lock or decision** and then check whether the older document has a SUPERSEDED / PARTIALLY SUPERSEDED banner. Historical implementation reports remain useful evidence, but they are not allowed to override a later product or architecture lock.

---

## Trip / dispatch control center — current product locks

| Title | Path | Status / purpose |
|------|------|------------------|
| **000 — Trip Container Is the Dispatch Control Center** | [`000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`](./000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md) | **Current product/UI identity lock.** Trip page = Trip Container = Dispatch Control Center. `DeprecatedDispatchPage` is legacy `Load.status` board / visual salvage only. |
| **001 — Trip Container Accordion Wireframe** | [`001_TRIP_CONTAINER_ACCORDION_WIREFRAME.md`](./001_TRIP_CONTAINER_ACCORDION_WIREFRAME.md) | **Design / wireframe only.** UI structure for the same Trip-backed Dispatch Control Center; not implementation truth. |
| **Trip execution & custody master index** | [`TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`](./TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md) | Approved execution/custody reading map. Read together with 000 and Decision 14 for current UI ownership and assignment slice state. |
| **Decision 14 — Trip Assignment Update Slice** | [`DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md`](./DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md) | **LOCKED** first post-cutover trip-assignment implementation slice; trip-level driver/truck/trailer assignment without reviving `Load.status = dispatched`. |

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
| **Load Rate Confirmation Semantic Parser Design** | [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md) | **Current parser design lock.** Evidence (not conclusions) + runtime tenant identity exclusion + OpenAI semantic result with provenance. The new evidence/exclusion contract is a design target; the live guarded parser already uses OpenAI but still carries older diagnostics until cutover. |
| OpenAI semantic extraction integration report | [`OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md`](./OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md) | **Historical / superseded as a current-state report.** Useful for original connectivity and Load Lab integration rationale; do not use its old “semantic extraction not implemented” statement as current parser truth. |

---

## Trip execution, custody, dispatch (decision spine)

| Document | When to read |
|----------|----------------|
| [`TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`](./TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md) | Approved reading order and supporting references for trip execution, custody, assignment, load workspace decisions **6–14**, and related DDL/payroll docs. |

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

*Add new cross-cutting design reports here under the appropriate section so they stay discoverable. When a later lock replaces an older document, stamp the older document explicitly instead of leaving two apparently-current truths.*
