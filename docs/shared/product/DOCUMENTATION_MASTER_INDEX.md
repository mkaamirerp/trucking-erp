# TruckERP — documentation master index

**Purpose:** Single navigation map for current design/operator truth. Always open the linked document for full detail.

## Trust / precedence rule

**Load / Trip / TripLoad / Dispatch / Custody:** [`load_trip/MASTER.md`](./load_trip/MASTER.md) is the **sole** canonical architecture **and** remediation/work-order document. When any other document conflicts with that master on those domains: **STOP and report**.

For other domains, prefer **current code + newer explicit locks/decisions**. Historical reports remain evidence but do not override current architecture.

---

## Trip / Dispatch / Load–Trip architecture

| Title | Path | Status / purpose |
|---|---|---|
| **Load / Trip Master Architecture** | [`load_trip/MASTER.md`](./load_trip/MASTER.md) | **Only** Load/Trip/TripLoad/Dispatch/custody architecture + implementation work order + absorbed appendices. |

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

## Other domains

See module-specific docs (Fuel, Tolls, Onboarding, Settlements, etc.). They must **not** redefine Load/Trip status or dispatch authority — defer to [`load_trip/MASTER.md`](./load_trip/MASTER.md).
