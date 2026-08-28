# TruckERP — documentation master index

**Purpose:** Single navigation map so design and operator docs are not lost in `docs/`.  
**Does not** replace underlying documents — always open the linked file for full detail.

**Docs landing page:** [`README.md`](./README.md) (this file is the **master tracker** for major design topics).

## Trust / precedence rule

When two documents conflict, prefer the **newer explicit lock/decision and the current code**. Historical reports remain useful evidence, but they do not override a later product, architecture, or shipped-state lock.

---

## Trip / Dispatch Control Center — current product and shipped-state docs

| Title | Path | Status / purpose |
|------|------|------------------|
| **000 — Trip Container Is the Dispatch Control Center** | [`000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`](./000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md) | **Current product/UI identity lock.** Trip = Trip Container = Dispatch Control Center. Current UI is in transition: `/trips/container` has the new Trip-backed control-center slice, `/trips/:id` remains the detailed Trip workspace, and `/dispatch` is legacy `Load.status` compatibility only. |
| **001 — Trip Container Accordion Wireframe** | [`001_TRIP_CONTAINER_ACCORDION_WIREFRAME.md`](./001_TRIP_CONTAINER_ACCORDION_WIREFRAME.md) | **Design contract + first implementation slice shipped.** Defines the accordion/IA contract used by the new Trip Container UI; some future sections remain placeholders. |
| **Trip execution & custody master index** | [`TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`](./TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md) | Approved shipped-state reading map for Trip execution, custody, assignment, and Decisions 6–14. |
| **Decision 14 — Trip Assignment Update Slice** | [`DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md`](./DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md) | **LOCKED + SHIPPED.** `PUT /trips/{id}/assignment` commits Trip-level driver/truck/trailer assignment without reviving `Load.status = dispatched`. |

---

## Load, email intake, documents, parser

| Title | Path | Description |
|------|------|-------------|
| **Email Intake Filtering and Load Intake Safety** | [`email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md`](./email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md) | Cross-provider filtering and safety boundaries before Load Intake. |
| **Async Load Page Parse Job Design** | [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](./load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md) | Future async job + polling transport for the product Load Page parser; does not redefine parser semantics. |
| Gmail automatic ingestion | [`GMAIL_AUTOMATIC_INGESTION.md`](./GMAIL_AUTOMATIC_INGESTION.md) | Gmail Pub/Sub + watch definition of done and proof checklist. |
| Broker / email intake — QR design | [`BROKER_EMAIL_INTAKE_QR_DESIGN.md`](./BROKER_EMAIL_INTAKE_QR_DESIGN.md) | QR-derived intake metadata, lineage, audit, and broker/load linkage. |
| **Current PDF load paths and gaps** | [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) | **Current reality map.** Product Load Page + Email Intake review use the public Rate Confirmation v2 parser; Load Lab is a separate proving surface; OCR execution remains missing. |
| **Load Lab ↔ Load Workspace parity** | [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md) | **Current product boundary.** Load Lab is proving/debug/regression; `LoadWorkspaceForm` is the production form. Shared hydration/form parity is shipped; Lab must not become a second Load product. |
| Trip container — Load Page + parser integration map | [`TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md`](./TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md) | Load Page / parser / Trip boundary map; check against newer parser and Trip locks when using. |
| **Load Rate Confirmation Semantic Parser Design** | [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md) | **Implemented Rate Confirmation v2 profile contract.** Tenant exclusion + field rules + page-separated text → OpenAI → mechanical validation → existing Load hydration DTO. |
| **Shared Document Parsing Architecture** | [`TruckERP_Shared_Document_Parsing_Architecture.md`](./TruckERP_Shared_Document_Parsing_Architecture.md) | **Architecture lock.** Shared acquisition/semantic ownership plus durable safety principles; Rate Confirmation v2 is the first shipped production profile. |
| **OpenAI semantic extraction integration report** | [`OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md`](./OPENAI_SEMANTIC_EXTRACTION_INTEGRATION_REPORT.md) | **Historical / superseded.** Original connectivity/rollout rationale only. |

### Load Lab evidence / cleanup (not product parser authority)

- [`LOAD_LAB_BASELINE_6PDF.md`](./LOAD_LAB_BASELINE_6PDF.md) — frozen regression/evaluation evidence; keep as evidence, not architecture.
- [`LoadLabCleaner.md`](./LoadLabCleaner.md) — cleanup ledger for temporary/historical Lab bridges; entries must be re-audited against parser v2 before being treated as current conditions.

Historical Lab pipeline and implementation reports should not be added back to this current index merely because they contain the word “current.”

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

Operational and architecture locks for agents and humans live under **`.cursor/rules/`**. This index lists `docs/` markdown only; open `.cursor/rules` when editing matching paths.

---

*Add new cross-cutting design reports here under the appropriate section. When a newer lock or shipped implementation supersedes an older report, mark the older document explicitly rather than leaving two apparently-current truths.*
