# API request examples

These files are sample request payloads for manual testing and integration reference.

## Rules

- Examples must match the current public API schema on `main`.
- New Load examples should use `status: "draft"` unless a current product/API contract explicitly requires otherwise.
- Do not use examples to create Trip execution, custody, dispatch assignment, payroll, or other operational state indirectly through legacy Load statuses.
- Replace IDs, dates, rates, and business-specific values before using a sample against any environment.
- When the schema changes, update or remove the example in the same documentation pass; stale examples are worse than no example.

Current sample:

- `api_post_loads_sample.request.json` — example body for `POST /api/v1/loads` / `LoadCreate`.
