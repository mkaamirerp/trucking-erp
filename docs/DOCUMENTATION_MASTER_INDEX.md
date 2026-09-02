# TruckERP — documentation master index

**Purpose:** Single navigation map for current design/operator truth. Always open the linked document for full detail.

## Trust / precedence rule

When documents conflict, prefer **current code + newer explicit locks/decisions**. Historical reports remain evidence but do not override current architecture.

---

## Trip / Dispatch Control Center

| Title | Path | Status / purpose |
|---|---|---|
| **Trip Container Operational Rules and Architecture Lock** | [`trip-foundation.md`](./trip-foundation.md) | Canonical Load vs Trip vs TripLoad vs custody meaning and business rules. |
| **000 — Trip Container Is the Dispatch Control Center** | [`000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`](./000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md) | Current product/UI identity lock; route convergence is still transitional. |
| **001 — Trip Container Accordion Wireframe** | [`001_TRIP_CONTAINER_ACCORDION_WIREFRAME.md`](./001_TRIP_CONTAINER_ACCORDION_WIREFRAME.md) | Design contract + first implementation slice shipped. |
| **Trip execution & custody master index** | [`TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`](./TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md) | Shipped-state reading map for Trip execution/custody/assignment and Decisions 6–14. |
| **Decision 11 — Load.status target model** | [`DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`](./DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md) | Load commercial/readiness status ownership and legacy-board migration boundary. |
| **Decision 14** | [`DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md`](./DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md) | LOCKED + SHIPPED Trip assignment slice. |

---

## Document Parser / Load intake

| Title | Path | Description |
|---|---|---|
| **Shared Document Parsing Architecture** | [`TruckERP_Shared_Document_Parsing_Architecture.md`](./TruckERP_Shared_Document_Parsing_Architecture.md) | **Primary architecture lock: one shared Document Parser engine/pipeline with attached profiles.** Rate Confirmation is first shipped; Fuel/Toll document profiles attach to the same engine. |
| **Load Rate Confirmation Semantic Parser Design** | [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md) | Implemented Rate Confirmation profile contract. |
| **Current PDF load paths and gaps** | [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) | Current route/integration reality. |
| **Load Lab ↔ Load Workspace parity** | [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md) | Current product boundary: Lab is proving/debug; `LoadWorkspaceForm` is production. |
| **Email Intake Filtering and Load Intake Safety** | [`email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md`](./email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md) | Cross-provider intake filtering and safety. |
| **Async Load Page Parse Job Design** | [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](./load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md) | Future execution/transport model; does not redefine parser semantics. |
| Gmail automatic ingestion | [`GMAIL_AUTOMATIC_INGESTION.md`](./GMAIL_AUTOMATIC_INGESTION.md) | Gmail Pub/Sub/watch definition of done. |
| Multi-document candidate contract | [`MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md`](./MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md) | Future grouping/merge contract. |

### Load Lab evidence / cleanup

- [`LOAD_LAB_BASELINE_6PDF.md`](./LOAD_LAB_BASELINE_6PDF.md) — frozen regression evidence; not architecture.
- [`LoadLabCleaner.md`](./LoadLabCleaner.md) — cleanup ledger; re-audit entries against current shared-parser/profile truth.
- [`archive/README.md`](./archive/README.md) — historical implementation/evaluation reports and superseded pipeline records.

---

## Engineering and platform

| Document | When to read |
|---|---|
| [`ENGINEERING_PLAYBOOK.md`](./ENGINEERING_PLAYBOOK.md) | Engineering/tenant/ops guardrails. |
| [`ENGINEERING_CHECKLIST.md`](./ENGINEERING_CHECKLIST.md) | Deploy/verify checklist. |
| [`trucking_erp_blueprint.md`](./trucking_erp_blueprint.md) | Product/architecture blueprint. |
| [`DATABASES_PLATFORM_AND_DEMO.md`](./DATABASES_PLATFORM_AND_DEMO.md) | Platform vs tenant DB model. |
| [`db_schema/README.md`](./db_schema/README.md) | Generated schema dumps. |

---

## Cursor / AI rules

Repository-enforced operational/architecture locks live under `.cursor/rules/`; check matching rules before editing protected areas.

---

**Maintenance rule:** Prefer updating an existing canonical doc over creating another top-level implementation report. Move superseded reports to `archive/` after their durable rules are consolidated.
