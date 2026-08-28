# TruckERP documentation

Start here for current human-readable architecture, engineering, operations, and product documentation.

## How to read these docs

TruckERP documentation has several different kinds of files. Treat them differently:

- **Canonical / current** — architecture locks, contracts, runbooks, operational rules, and active design documents. These are the source of truth for current work.
- **Generated / evidence** — schema dumps, fixtures, evaluation output, and proof artifacts. Keep them when they support tests or reproducible evidence.
- **Historical** — completed handoffs, superseded implementation reports, old forensic snapshots, and one-off notes. These belong under [`archive/`](archive/README.md) and are not current guidance.
- **Agent rules** — repository-enforced engineering and safety rules live under `.cursor/rules/` and must be checked when editing matching areas.

## Main navigation

**Master index:** [`DOCUMENTATION_MASTER_INDEX.md`](DOCUMENTATION_MASTER_INDEX.md) — curated map of the major current documentation spines.

### Engineering and platform

- [`ENGINEERING_PLAYBOOK.md`](ENGINEERING_PLAYBOOK.md) — canonical engineering playbook.
- [`ENGINEERING_CHECKLIST.md`](ENGINEERING_CHECKLIST.md) — short deploy/verify checklist.
- [`trucking_erp_blueprint.md`](trucking_erp_blueprint.md) — product and architecture blueprint.
- [`DATABASES_PLATFORM_AND_DEMO.md`](DATABASES_PLATFORM_AND_DEMO.md) — platform versus tenant database model.
- [`TENANT_SAFETY_EXECUTION_RUNBOOK.md`](TENANT_SAFETY_EXECUTION_RUNBOOK.md) — tenant safety operations.

### Load intake and parser

- [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md) — async Load Page parse-job design.
- [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) — current PDF parse paths and known gaps.
- [`TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md`](TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md) — Load Page/parser/trip-container boundaries.
- [`email/README.md`](email/README.md) — email intake documentation.

### Trip execution and custody

- [`TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`](TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md) — approved reading order for trip execution, custody, assignments, and related decisions.

### Historical material

- [`archive/README.md`](archive/README.md) — archive policy and historical snapshots.

## Documentation maintenance rule

Before adding another top-level document, first decide whether it belongs in an existing topic directory, the master index, generated evidence, or the archive. Avoid creating a new top-level handoff/report when an existing canonical document can be updated instead.
