# Load Parser — Duplicate Load / Revised Rate Confirmation

**Status:** TODO — design approved; not implemented.
**Scope:** Tenant-scoped load import and Load Lab. Do not change the locked PDF + JSON semantic AI parsing architecture.

## Purpose
Prevent accidental duplicate loads while allowing a revised rate confirmation (RC) to update an existing load through explicit review. A broker's barcode is an optional duplicate-detection signal only, not a shipment status or BOL/POD matching mechanism.

## Detection
- Extract a machine-readable barcode locally where available, without AI, as optional metadata.
- Check existing loads/documents within the current tenant for the same broker + barcode, and independently for the same broker + broker load number.
- A barcode is not guaranteed to equal the broker load number, be present, or remain unchanged on revisions. Never rely on barcode alone.
- Match only within the authenticated tenant; never leak another tenant's records.
- When a possible match exists, pause creation and show the existing load reference and broker in a modal. Do not silently create a new load or overwrite an existing one.

## Modal
**Title:** Possible Duplicate Load

**Message:** This load already exists in TruckERP. Is this a revised rate confirmation or a duplicate document?

**Actions:**
1. **Revised RC** — parse the incoming RC, compare proposed fields with the existing load, show a field-by-field change review, and require explicit authorized confirmation before applying changes to the *same* load. Retain original PDF, new PDF, prior values, and audit/revision history. Never silently alter financial amounts, stops, appointments, or dispatched work.
2. **Ignore** — dismiss and abandon this import; make no changes to the existing load.

## Guardrails
- Treat a matching barcode/load number as a *possible* duplicate, not automatic rejection.
- A revised RC can retain the same barcode; a different barcode can still refer to the same load.
- Preserve the original load identity and its audit trail; no second load for an approved revision.
- Validate permissions and any operational/financial locks before applying changes. Block or escalate unsafe changes rather than silently mutating dispatched or settled records.
- Never use the broker barcode to infer tracking/status updates or to match BOL/POD documents that lack it.
- Keep the existing digital-PDF semantic flow: original PDF + canonical JSON field rules/instructions + tenant exclusion + structured output schema; no duplicated locally flattened PDF text in the AI semantic prompt.
- Barcode extraction is optional local preprocessing/validation, not an AI prompt replacement.

## Acceptance tests
- Same tenant, same broker and load number: modal appears, no duplicate created.
- Same tenant, matching broker barcode: modal appears even if number extraction is uncertain.
- Revised RC: differences displayed, explicit confirmation required, same load updated with revision history.
- Ignore: no load/document/financial mutation.
- Same load number under different tenants: no cross-tenant collision or disclosure.
- Same number under different brokers: no false duplicate.
- Missing/undecodable barcode: normal broker-load-number duplicate check still works.
- Changed barcode on a revised RC: matching broker load number still triggers modal.
- Financial/operationally locked load: unauthorized changes blocked.
- Parser regression: original PDF + JSON instructions flow unchanged.

## Reference example
C.H. Robinson rate confirmation #570774771 (user-supplied example). Its barcode is broker-internal metadata and is useful to TruckERP only as an optional duplicate signal. Do not store the private sample PDF in the repository.
