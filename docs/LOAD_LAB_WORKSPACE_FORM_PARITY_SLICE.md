# Load Lab — workspace form parity slice (implementation report)

**Date:** 2026-04-20  
**Scope:** Shared PDF/parse hydration helper; Load Lab renders the same `LoadWorkspaceForm` as production, **read-only**; no promote, no operational load writes.

## Files changed

| File | Change |
|------|--------|
| `apps/web/src/loadWorkspace/applyLoadDocumentParseResponse.ts` | **New** — `extractedStopsToDraft`, `applyLoadDocumentParseResponse(res, callbacks)` (logic moved from `LoadWorkspacePage`). |
| `apps/web/src/pages/LoadWorkspacePage.tsx` | `onParseWorkspacePdf` calls `applyLoadDocumentParseResponse`; removed local `extractedStopsToDraft` and inline broker/stop/notes mapping; dropped unused imports (`matchBrokerContactFromParsed`, `filterMeaningfulParsedStops`, `resolveBrokerIdentity`, `LoadDocumentParseStop`). |
| `apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx` | Optional `readOnly?: boolean`; wraps form in `<fieldset disabled={readOnly}>`. |
| `apps/web/src/pages/LoadLabPage.tsx` | Loads broker/driver/customs lists; resets workspace-shaped state per run; hydrates from `detail.parse_response` via shared helper; renders **`LoadWorkspaceForm`** (`mode="manual"`, `readOnly`, `SECTION_CONFIG.manual.visible`, `editableSections={[]}`); lab metadata/JSON moved to **aside** panel. |
| `docs/LoadLabCleaner.md` | Ledger: read-only fieldset bridge; JSON-first entry marked **deferred** (panels secondary). |

## Helper extracted

- **`applyLoadDocumentParseResponse`** — `async (res: LoadDocumentParseResponse, cbs: ApplyLoadDocumentParseCallbacks) => ApplyLoadDocumentParseSummary`  
  - Mirrors prior `onParseWorkspacePdf` mapping: broker name, MC/DOT → `resolveBrokerIdentity` + `listBrokerContacts` + `matchBrokerContactFromParsed`, contact snapshots, load ref, equipment/financial scalars, internal notes (`raw_text` + optional customs broker line), meaningful stops → `extractedStopsToDraft`.  
- **`extractedStopsToDraft`** — exported from the same module (was previously local to `LoadWorkspacePage`).

## Does Load Lab show the same canonical form sections?

**Yes, for the same `visibleSections` as manual workspace:** `SECTION_CONFIG.manual.visible` → **HeaderIdentity** (in config; header UI may still live outside the form in workspace — see divergence), **Parties**, **Stops**, **Equipment** (freight + financials blocks), **Assignment**, **Documents** (customs), **Notes** (internal notes; operational notes timeline off in Lab).

Rendering uses the **same** `LoadWorkspaceForm` component and props pattern as `LoadWorkspacePage` (manual mode).

## What remains divergent

1. **`extracted.references[]`** — Still **not** mapped into a dedicated “references” subsection of the form (workspace PDF path never did). Shown as **JSON** in the Lab aside (`Structured references (parse DTO)`).
2. **Header chrome** — `LoadWorkspacePage` may show status/load title **outside** the form; Lab does not duplicate that shell — form still includes load number in **Financials** like the workspace form.
3. **Document panel / `focusDoc`** — Lab uses a no-op `focusDoc`; workspace PDF parse still highlights lines in the side document viewer.
4. **Intake / detail modes** — Lab only uses **manual** section config + read-only; no intake proposed styling, no payroll/audit modes.
5. **Assignment / Documents UX** — Same components render, but **fieldset disabled** freezes assignment and customs controls; customs confirm button path is irrelevant in Lab.

## Verification

```bash
cd /home/admin/trucking_erp/apps/web && npm run build
```

Optional deploy: `/home/admin/trucking_erp/scripts/reload_nginx_web.sh` after `npm run build`.
