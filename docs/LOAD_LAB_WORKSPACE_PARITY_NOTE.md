# Load Lab ↔ Load Workspace parity

**Status:** **CURRENT PRODUCT BOUNDARY + SHIPPED PARITY NOTE — refreshed 2026-08-28.**  
**Product lock:** **Load Lab is a proving / debug / regression surface. `LoadWorkspaceForm` is the production load form.** Lab must not become a second product Load implementation.  
**Merged history:** Durable implementation facts from [`archive/LOAD_LAB_WORKSPACE_FORM_PARITY_SLICE.md`](./archive/LOAD_LAB_WORKSPACE_FORM_PARITY_SLICE.md) are consolidated here.

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

Parser semantics belong to the shared Document Parser and the active document profile, not to Lab UI code.

---

## 2. What is already shared / shipped

### Same parser DTO family

Lab and product workflows use the `LoadDocumentParseResponse` / `LoadParseExtractedFields` contract family for workspace-shaped parse results. That DTO is a hydration contract, not the persisted `Load` row schema.

### Shared parse → workspace hydration helper

The parity slice extracted production parse application into:

```text
apps/web/src/loadWorkspace/applyLoadDocumentParseResponse.ts
```

The production Load Page uses that helper for parsed broker/contact snapshots, load reference, financial/equipment values, notes, and meaningful stops.

### Same production form rendered in Lab

`LoadLabPage` renders the same `LoadWorkspaceForm` for workspace-shaped review, read-only with Lab/debug context alongside it.

---

## 3. What remains intentionally different

1. Lab run metadata / JSON / diagnostics.
2. Read-only behavior in Lab vs production edit/save behavior.
3. Page shell/header chrome.
4. Document-focus behavior.
5. Mode coverage.
6. `extracted.references[]` debug visibility when the production form has no dedicated editable references subsection.
7. Lab persistence/promote tooling, when present, as proving-surface controls only.

---

## 4. Rules for future changes

### Must

- Reuse `LoadWorkspaceForm` for production-shaped Load review.
- Reuse the shared parse → workspace hydration helper.
- Keep parser semantics in the shared Document Parser/profile, not Lab UI components.
- Keep Lab diagnostics secondary to the production-shaped form.
- Treat parse output as candidate/hydration data; normal Load save models remain operational persistence truth.

### Must not

- Create a second final Load form in `LoadLabPage`.
- Add Lab-only business meanings that alter production parser semantics.
- Turn Lab debug fields into production fields without a normal product/schema decision.
- Bypass normal production workspace review/save rules because an experiment passed in Lab.

---

## 5. Historical implementation evidence

[`archive/LOAD_LAB_WORKSPACE_FORM_PARITY_SLICE.md`](./archive/LOAD_LAB_WORKSPACE_FORM_PARITY_SLICE.md) records the April implementation details that introduced the shared hydration helper and read-only `LoadWorkspaceForm` rendering in Lab. It is historical evidence, not a second parity source.

---

## 6. One-line test

> **If we removed Load Lab tomorrow, would the production Load Page and shared Document Parser/profile still contain the real business rule?**

If the answer is no, the rule is probably being implemented in the wrong place.
