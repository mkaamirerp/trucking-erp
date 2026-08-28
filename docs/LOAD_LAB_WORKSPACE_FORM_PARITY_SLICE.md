# Load Lab — workspace form parity slice (historical implementation report)

**Status:** **MERGED INTO CURRENT PARITY NOTE / HISTORICAL IMPLEMENTATION REPORT.**  
**Current truth:** [`LOAD_LAB_WORKSPACE_PARITY_NOTE.md`](./LOAD_LAB_WORKSPACE_PARITY_NOTE.md) now owns the Load Lab ↔ production Load Workspace boundary and the durable shipped parity facts from this slice.  
**Archive state:** Safe to classify for archive after reference checks; this file should not be maintained as a second parity source.

**Date:** 2026-04-20  
**Original scope:** Shared PDF/parse hydration helper; Load Lab renders the same `LoadWorkspaceForm` as production, read-only; no default operational load writes from this UI slice.

---

## Files changed in the slice

| File | Change |
|------|--------|
| `apps/web/src/loadWorkspace/applyLoadDocumentParseResponse.ts` | **New** — `extractedStopsToDraft`, `applyLoadDocumentParseResponse(res, callbacks)`; logic moved from `LoadWorkspacePage`. |
| `apps/web/src/pages/LoadWorkspacePage.tsx` | `onParseWorkspacePdf` calls the shared helper; removed local parse-mapping duplication. |
| `apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx` | Optional `readOnly?: boolean`; form can be frozen for proving/review surfaces. |
| `apps/web/src/pages/LoadLabPage.tsx` | Hydrates workspace-shaped state through the shared helper and renders `LoadWorkspaceForm` read-only; Lab metadata/JSON remains secondary. |
| `docs/LoadLabCleaner.md` | Recorded temporary Lab/UI divergence and cleanup debt. |

## Helper extracted

- **`applyLoadDocumentParseResponse`** — shared parse → workspace mapping for broker/contact snapshots, load ref, equipment/financial scalars, notes, and meaningful stops.
- **`extractedStopsToDraft`** — exported stop mapping used by the same shared path.

## Canonical form sections

The Lab slice rendered the same `LoadWorkspaceForm` production/manual sections in a read-only proving context rather than duplicating the load field model.

## Divergences recorded by the slice

1. `extracted.references[]` did not have a dedicated production form subsection and remained visible primarily through Lab/debug JSON.
2. Header/page chrome outside the shared form differed.
3. Production document-focus behavior was not duplicated in Lab.
4. Lab used manual/read-only section configuration rather than pretending to be every workspace mode.
5. Assignment/customs controls rendered but were disabled in the Lab review context.

## Verification used at the time

```bash
cd /home/admin/trucking_erp/apps/web && npm run build
```

The durable product rule from this implementation is now maintained in `LOAD_LAB_WORKSPACE_PARITY_NOTE.md`: **reuse the production form and shared hydration rules; do not build a second product Load editor in Lab.**
