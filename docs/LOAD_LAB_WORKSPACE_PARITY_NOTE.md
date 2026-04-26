# Load Lab ↔ Load workspace parity (grounded note)

**Date:** 2026-04-20  
**Scope:** Product direction lock — no second “final” load editing model in Lab. This note is **code-grounded** (repo paths cited); it is **not** a promise that UI parity is already shipped.

---

## What already aligns with the real Load workspace contract

1. **Backend candidate shape** — Lab persists successful semantic output as **`LoadDocumentParseResponse`** (`app/schemas/load_document_parse.py`), the same Pydantic model returned by **`POST /api/v1/loads/parse-document`** (`app/routers/loads.py`). Stops in that schema are documented to align with **`LoadStopWrite`** geometry (`LoadParseStopItem` docstring in `load_document_parse.py`).

2. **Workspace already consumes that DTO** — **`LoadWorkspacePage`** applies PDF parse results by reading **`res.extracted`**, **`res.raw_text`**, **`res.warnings`**, and mapping stops through **`extractedStopsToDraft`** (`apps/web/src/pages/LoadWorkspacePage.tsx`, `onParseWorkspacePdf`). That is the **canonical client-side hydration path** from parse DTO → workspace draft state today.

3. **Lab-only overlays** — Run metadata, **`normalized_package`**, **`lab_confidence`**, **`contradictions`**, **`lab_review_*`**, OpenAI metadata, and raw JSON debug panels are **audit/review** structures. They are **not** a second operational load row shape and do not replace **`LoadWritePayload`** / **`Load`**.

---

## What currently diverges from “same form experience”

1. **UI surface** — **`LoadLabPage`** (`apps/web/src/pages/LoadLabPage.tsx`) is a **dedicated** route with JSON previews, review banners, and pipeline controls. It does **not** mount **`LoadWorkspaceForm`** (`apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx`), which is the **canonical editable load form** shared by manual / detail / intake modes.

2. **DTO vs persist payload** — **`LoadDocumentParseResponse`** is the **hydration** contract (extracted block + raw text + parse warnings). The **save** contract for real loads is **`LoadWritePayload`** / server **`Load`** (`buildLoadPersistPayload` in `apps/web/src/loadWorkspace/loadWorkspaceShared.ts`). Fields such as **`broker_id`**, **`load_number`**, **`status`**, fleet/driver/trailer IDs, **`hazmat_flag`**, **`pallet_case_count`**, **`broker_contact_extension_snapshot`**, and structured **notes** are part of workspace persistence, not fully represented in the parse DTO. Lab correctly does **not** pretend the parse DTO is the full load row.

3. **Hydration completeness vs workspace PDF parse** — Workspace **`onParseWorkspacePdf`** applies many **`extracted`** scalars and stops; it does **not** map **`extracted.references[]`** into a separate references UI (no `references` handling in that callback as of this note). Any future “full parity” should mean **one shared apply function** used by both workspace PDF parse and Lab, not two diverging copy/paste lists.

4. **Docs drift** — Older text in **`LOAD_LAB_FIRST_MIGRATION_CUT.md`** allowed “no direct reuse of `LoadWorkspaceForm` for v1.” That was a **scope shortcut**, not a product principle. It is now **explicit debt** relative to the parity lock (see cleaner ledger).

---

## Smallest next step (no promote, no operational writes)

**Goal:** Same field groups the operator knows, **read-only** in Lab, **zero** default write to **`loads`**.

1. **Extract** the parse → workspace field application from **`onParseWorkspacePdf`** into a shared helper, e.g. **`applyLoadDocumentParseToWorkspaceDraft(...)`** in `apps/web/src/loadWorkspace/` (inputs: extracted + options such as whether to resolve broker identity; outputs: partial state patch or setter callbacks). **`LoadWorkspacePage`** keeps current behavior by calling that helper.

2. **On `LoadLabPage`**, when **`parse_response`** exists: mount **`LoadWorkspaceForm`** (or a thin wrapper) with **`visibleSections`** / **`editableSections`** set so the **same sections** render as production, but **editing disabled** (or all handlers no-op), plus existing **lab-only** panels **below or beside** the form. Broker dropdown resolution can stay **read-only** (snapshots only) in the first cut to avoid implying a save.

3. **Optional follow-up:** map **`extracted.references`** into whatever the workspace uses for reference UX **once** that path exists in the shared helper so Lab and workspace stay aligned.

This delivers **“normal load page + lab/debug context”** without implementing **promote** or any **POST/PATCH load** from Lab.

---

## References

- `docs/LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md` — updated with explicit workspace parity lock.
- `docs/LOAD_LAB_FIRST_MIGRATION_CUT.md` — first-cut scope vs long-term parity.
- `docs/LoadLabCleaner.md` — ledger entry for temporary UI divergence.
