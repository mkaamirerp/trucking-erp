# TruckERP — `docs/` overview

Start here for human-readable design and engineering documentation.

**Master tracker:** [`DOCUMENTATION_MASTER_INDEX.md`](DOCUMENTATION_MASTER_INDEX.md) — maps major topics (email/load intake, trips, parser, platform).

---

## Email intake (quick link)

| Title | Path |
|------|------|
| **Email Intake Filtering and Load Intake Safety** | [`email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md`](email/EMAIL_INTAKE_FILTERING_AND_LOAD_INTAKE_SAFETY.md) |

Cross-provider design/report for filtering email intake before Load Intake — see that file for current behavior, target A/B/C/D/E routing, signals, human review, and safety boundaries.

## Load Page parser (quick link)

| Title | Path |
|------|------|
| **Async Load Page Parse Job Design** | [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md) |

Design note for async Load Page PDF parsing (job + poll) without changing `LoadDocumentParseResponse` or hydration — see the file for scope and safety boundaries.

More email- and parser-related docs: [`email/README.md`](email/README.md) and **Load, email intake** in [`DOCUMENTATION_MASTER_INDEX.md`](DOCUMENTATION_MASTER_INDEX.md).
