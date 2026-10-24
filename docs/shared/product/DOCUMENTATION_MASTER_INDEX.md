# TruckERP — documentation master index

**Purpose:** Single navigation map for current design/operator truth. Always open the linked document for full detail.

## Trust / precedence rule

**Load / Trip / TripLoad / Dispatch / Custody:** [`load_trip/MASTER.md`](../../load_trip/MASTER.md) is the canonical architecture **and** remediation/work-order document.

**Operator workflow (dispatch home, load-first assignment, workspace promote → ready):** [`.cursor/rules/owner-product-rules.mdc`](../../../.cursor/rules/owner-product-rules.mdc) **overrides** `MASTER.md`. Do **not** STOP solely for workflow conflicts between those two — implement per owner product rules and update `MASTER.md` when directed.

When any other document conflicts with the master on **non-workflow** architecture: **STOP and report**.

For other domains, prefer **current code + newer explicit locks/decisions**. Historical reports remain evidence but do not override current architecture.

| **Owner product rules (workflow)** | [`.cursor/rules/owner-product-rules.mdc`](../../../.cursor/rules/owner-product-rules.mdc) | Dispatch home, loads-first assign, Create load → ready, Mark ready scope |

---

## Trip / Dispatch / Load–Trip architecture

| Title | Path | Status / purpose |
|---|---|---|
| **Load / Trip Master Architecture** | [`load_trip/MASTER.md`](../../load_trip/MASTER.md) | Load/Trip/TripLoad/Dispatch/custody architecture + work order (workflow overrides: owner-product-rules). |

Former Decision 6–14, Phase3L, Trip Container 000/001, integrity tracker, trip-number rule, and related foundation/index MDs were consolidated into that master and removed.

---

## Document Parser / Load intake (parser domain — not a second Trip architecture)

| Title | Path | Description |
|---|---|---|
| **Shared Document Parsing Architecture** | [`TruckERP_Shared_Document_Parsing_Architecture.md`](./TruckERP_Shared_Document_Parsing_Architecture.md) | **Primary architecture lock: one shared Document Parser engine/pipeline with attached profiles.** Rate Confirmation is first shipped; Fuel/Toll document profiles attach to the same engine. |
| **Load Rate Confirmation Semantic Parser Design** | [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md) | Implemented Rate Confirmation profile contract. Defers Load/Trip lifecycle to the Load/Trip master. |
| **Current PDF load paths and gaps** | [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) | Current route/integration reality. |
| **Load Lab ↔ Load Workspace parity** | [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md) | Lab is proving/debug; `LoadWorkspaceForm` is production. |
| **Email Intake Filtering and Load Intake Safety** | [`email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md`](./email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md) | Cross-provider intake filtering and safety. |
| **Async Load Page Parse Job Design** | [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](./load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md) | Future execution/transport model; does not redefine Trip semantics. |
| Gmail automatic ingestion | [`GMAIL_AUTOMATIC_INGESTION.md`](./GMAIL_AUTOMATIC_INGESTION.md) | Gmail Pub/Sub/watch definition of done. |
| Multi-document candidate contract | [`MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md`](./MULTI_DOCUMENT_LOAD_CANDIDATE_CONTRACT.md) | Future grouping/merge contract. |

### Load Lab evidence / cleanup

- [`LOAD_LAB_BASELINE_6PDF.md`](./LOAD_LAB_BASELINE_6PDF.md) — frozen regression evidence; not architecture.
- [`LoadLabCleaner.md`](./LoadLabCleaner.md) — cleanup ledger.
- [`archive/README.md`](./archive/README.md) — historical implementation/evaluation reports.

---

## Payroll / Settlements

| Title | Path | Status / purpose |
|---|---|---|
| **Settlement rate (owner decision)** | [`payroll_settlements/SETTLEMENT_RATE_OWNER_DECISION_2026-10-24.md`](../../payroll_settlements/SETTLEMENT_RATE_OWNER_DECISION_2026-10-24.md) | Broker `loads.rate` vs settlement `customer_rate`; effective rate; O/O pay; finalize snapshots (Amir, 2026-10-24) |
| **Settlement rate — payroll/load chain report** | [`payroll_settlements/SETTLEMENT_RATE_PAYROLL_LOAD_CHAIN_REPORT_2026-10-24.md`](../../payroll_settlements/SETTLEMENT_RATE_PAYROLL_LOAD_CHAIN_REPORT_2026-10-24.md) | Read-only investigation: load → trip → pay run, current payroll behavior, snapshot options |
| Payroll / O/O fuel linkage | [`payroll_settlements/PAYROLL_OO_FUEL_SETTLEMENT_LINKAGE.md`](../../payroll_settlements/PAYROLL_OO_FUEL_SETTLEMENT_LINKAGE.md) | Fuel deduction timing vs settlement module |
| Module index | [`payroll_settlements/README.md`](../../payroll_settlements/README.md) | Navigation |

---

## Other domains

See module-specific docs (Fuel, Tolls, Onboarding, etc.). They must **not** redefine Load/Trip status or dispatch authority — defer to [`load_trip/MASTER.md`](./load_trip/MASTER.md).
