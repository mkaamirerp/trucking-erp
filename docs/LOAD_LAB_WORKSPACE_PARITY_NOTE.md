# Load Lab ↔ Load Workspace parity

**Status:** **CURRENT PRODUCT BOUNDARY + SHIPPED PARITY NOTE — refreshed 2026-08-28.**  
**Product lock:** **Load Lab is a proving / debug / regression surface. `LoadWorkspaceForm` is the production load form.** Lab must not become a second product Load implementation.  
**Merged history:** The durable implementation facts from `LOAD_LAB_WORKSPACE_FORM_PARITY_SLICE.md` are consolidated here; that implementation report is now historical/archive-ready.

**Related current truth:**

- [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md)
- [`TruckERP_Shared_Document_Parsing_Architecture.md`](./TruckERP_Shared_Document_Parsing_Architecture.md)
- [`TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](./TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md)
- [`LoadLabCleaner.md`](./LoadLabCleaner.md)

---

## 1. Product rule

There is one production load-editing experience:

```text
LoadWorkspacePage
  → LoadWorkspaceForm
```

Load Lab may show the same production form for comparison and review, but Lab-specific metadata, JSON, diagnostics, experiments, run history, confidence panels, or promote/reject tooling do **not** create a second canonical load-editing model.

> **Same production form and hydration rules; different proving/debug context.**

---

## 2. What is already shared / shipped

### Same parser DTO family

Lab and product workflows use the `LoadDocumentParseResponse` / `LoadParseExtractedFields` contract family for workspace-shaped parse results. That DTO is a **hydration contract**, not the persisted `Load` row schema.

### Shared parse → workspace hydration helper

The April parity slice extracted the production parse-application logic into:

```text
apps/web/src/loadWorkspace/applyLoadDocumentParseResponse.ts
```

The helper owns the workspace-shaped mapping that had previously lived inline in `LoadWorkspacePage`, including parsed broker/contact snapshots, load reference, financial/equipment values, notes, and meaningful stops through `extractedStopsToDraft`.

The product Load Page calls that shared helper rather than maintaining a separate mapping list.

### Same production form rendered in Lab

`LoadLabPage` renders the same:

```text
apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx
```

for workspace-shaped review. In Lab it is used **read-only** with production/manual section visibility and Lab/debug context alongside it.

This was the important parity correction: Lab should not invent a second set of load fields or a parallel editor just because it is a test surface.

---

## 3. What remains intentionally different

These differences do **not** violate parity because they belong to Lab/debug context rather than the production Load model:

1. **Lab run metadata / JSON / diagnostics** — persisted extraction-run details, confidence, contradictions, raw JSON, semantic-mode comparisons, and other proving tools may remain Lab-only.
2. **Read-only behavior** — Lab may freeze `LoadWorkspaceForm` controls. Production edit/save behavior belongs to `LoadWorkspacePage`.
3. **Page shell / header chrome** — status/title/navigation outside `LoadWorkspaceForm` can differ; the canonical field groups should not fork.
4. **Document focus behavior** — production workspace may focus/highlight source-document text; Lab can use a no-op or debug-oriented document viewer.
5. **Mode coverage** — Lab commonly renders the manual/read-only section configuration. It does not need to pretend to be intake, payroll, or every future workspace mode.
6. **`extracted.references[]` UX** — references may still appear in Lab JSON when the production workspace has no dedicated editable references subsection. Do not invent a Lab-only production field UI to close that gap.
7. **Lab persistence / promote tooling** — if Lab stores runs or exposes explicit review/promote actions, those are proving-surface controls. They do not redefine normal Load create/update semantics.

---

## 4. Rules for future changes

### Must

- Reuse `LoadWorkspaceForm` for production-shaped load review instead of copying its field groups into Lab.
- Reuse the shared parse → workspace hydration helper instead of maintaining a Lab-only mapping list.
- Keep parser semantics in the canonical parser/profile, not in Lab UI components.
- Keep Lab-specific diagnostics clearly secondary to the production-shaped form.
- Treat `LoadDocumentParseResponse` as candidate/hydration data and the normal Load save payload/model as the operational persistence contract.

### Must not

- Create a second “final load form” in `LoadLabPage`.
- Add Lab-only business meanings that alter what a parsed Rate Confirmation field means in production.
- Make a Lab debug field silently become a production Load field without a normal product/schema decision.
- Use Lab success as permission to bypass production workspace review/save rules.

---

## 5. Historical implementation report

`LOAD_LAB_WORKSPACE_FORM_PARITY_SLICE.md` records the April 20 implementation details that introduced the shared hydration helper and read-only `LoadWorkspaceForm` rendering in Lab.

Those facts are now captured here as the current parity rule. The slice report should be treated as **historical implementation evidence**, not a second parity source of truth.

---

## 6. One-line test

When deciding whether a Lab change is correct, ask:

> **If we removed Load Lab tomorrow, would the production Load Page and canonical parser still contain the real business rule?**

If the answer is no, the rule is probably being implemented in the wrong place.
