# TruckERP — Historical File Proliferation Audit

**Investigation window:** 2026-07-01 through 2026-10-18 (HEAD `e3e7634` on `gpt-review`)  
**Repository:** `/home/admin/trucking_erp`  
**Method:** Read-only Git history (`git log --since=2026-07-01 --diff-filter=A`), per-file first-add attribution (`git log --diff-filter=A -1 -- <path>`), import/caller sampling, and cross-check against integrity docs (`docs/load_trip/MASTER.md`, `docs/LOAD_INTEGRITY_AUDIT_AND_REMEDIATION_PLAN.md`).  
**Not committed by agent** — owner review required before merging this document.

---

## Module-by-module file trees (see the idea first)

**Snapshots**

| Label | Git commit | Date | `app/**/*.py` count |
|--------|------------|------|---------------------|
| **Pre-summer baseline** (“~June 2026”) | `964708ee` | 2026-05-12 | **272** |
| **October 2026 — `gpt-review` HEAD** | `e3e7634` | 2026-10-18 | **420** |
| **Δ** | | | **+148** net (**154** added, **6** removed since baseline) |

*There were no commits on this branch between 2026-05-12 and 2026-08-12; “June” here is the last tree before the summer expansion.*

### At a glance (by module)

| Module | Pre-summer files | Oct 2026 files | ← NEW |
|--------|-----------------:|---------------:|------:|
| **Loads (core)** | 4 | 5 | 1 |
| **Load Workspace (DW-1)** | 0 | 10 | 10 |
| **Load Parser** | 25 | 31 | 10 |
| **Load POD (I14)** | 0 | 3 | 3 |
| **Load / Trip custody & stops** | 0 | 6 | 6 |
| **Loads (core service unchanged)** | 4 | 4 | 0 |
| **Fuel** | 0 | 66 | 66 |
| **Tolls** | 0 | 13 | 13 |
| **RBAC (AuthZ pilot)** | 0 | 20 | 20 |
| **Trips / Dispatch** | 11 | 13 | 2 |
| **Document Platform** | 0 | 8 | 8 |
| **Shared utils** | 15 | 16 | 1 |
| **Shared core** | 8 | 10 | 2 |
| **Login / Auth** | 8 | 9 | 1 |

---

### Loads (core) — 4 → 5 files

**Pre-summer**

```
models/load.py
routers/loads.py
schemas/load.py
services/loads.py
```

**October 2026 — gpt-review**

```
models/load.py
routers/loads.py
schemas/load.py
services/loads.py
constants/load_integrity.py          ← NEW
```

*Commercial CRUD still lives in the same four files; integrity constants and I8 money parsing were added elsewhere (`utils/load_commercial_money.py`).*

---

### Load Parser — 25 → 31 files (+10 ← NEW)

**Pre-summer**

```
models/load_lab.py
routers/load_lab.py
schemas/load_document_parse.py
schemas/load_lab.py
schemas/load_lab_semantic.py
services/load_document_parse_adapter.py
services/load_document_parse_guarded.py
services/load_document_parse_openai.py
services/load_document_parse_orchestrator.py
services/load_document_product_parser.py
services/load_lab.py
services/load_lab_broker_contact_email_diagnostics.py
services/load_lab_broker_matrix.py
services/load_lab_diagnostics.py
services/load_lab_grounding.py
services/load_lab_reference_extract.py
services/load_lab_review.py
services/load_lab_semantic.py
services/load_lab_truckerjson_prompt.py
… (+ scripts under app/scripts/load_lab_*)
```

**October 2026 — gpt-review** (only **← NEW** lines listed; all pre-summer files above still present unless removed)

```
schemas/load_document_parse_semantic.py              ← NEW
services/load_document_parse_rate_con.py             ← NEW
services/load_parser_mechanical_validation.py        ← NEW
services/load_parser_openai_handoff_v2.py            ← NEW
services/load_parser_pdf_acquisition.py              ← NEW
services/load_parser_pdf_ocr.py                      ← NEW
services/load_parser_pdf_safety.py                   ← NEW
services/load_parser_rate_con_field_rules.py         ← NEW
services/load_parser_semantic_to_product.py          ← NEW
services/load_parser_tenant_identity_exclusion.py    ← NEW
```

*Several mid-2026 parser files were **removed or folded** (e.g. older `load_document_parse_contact_candidates.py`); net is +6 services/schemas, not a clean +10 stack.*

---

### Load Workspace (DW-1) — 0 → 10 files (all ← NEW)

**Pre-summer:** *(none)*

**October 2026**

```
models/load_commercial_evidence.py                   ← NEW
models/load_workspace_draft.py                       ← NEW
routers/load_workspace_drafts.py                     ← NEW
schemas/load_workspace_draft.py                      ← NEW
services/load_workspace_draft.py                     ← NEW
services/load_workspace_draft_document.py            ← NEW
services/load_workspace_draft_lifecycle.py           ← NEW
services/load_workspace_draft_mapper.py              ← NEW
services/load_workspace_draft_promotion.py           ← NEW
services/load_workspace_draft_storage.py             ← NEW
```

---

### Shared utils — 15 → 16 files

**Pre-summer:** `audit.py`, `password.py`, `jwt_auth.py`, … (15 files under `app/utils/`)

**October 2026** — one addition:

```
utils/load_commercial_money.py                       ← NEW
```

---

### Fuel — 0 → 66 files (all ← NEW)

**Pre-summer:** *(no `app/**/fuel*` application modules)*

**October 2026** — full tree (every file new in this window):

```
deps/fuel_rbac.py
models/fuel.py
routers/fuel.py
schemas/fuel.py
schemas/fuel_provider_profile.py
services/fuel_ai_contract.py
services/fuel_ai_handoff.py
services/fuel_ai_mechanical_validation.py
services/fuel_bvd_canonical_projection.py
services/fuel_bvd_column_map.py
services/fuel_bvd_completed_basic.py
services/fuel_bvd_correction_validate.py
services/fuel_bvd_document_identity.py
services/fuel_bvd_effective.py
services/fuel_bvd_extraction.py
services/fuel_bvd_import.py
services/fuel_bvd_review.py
services/fuel_bvd_source_reconciliation.py
services/fuel_bvd_stage.py
services/fuel_canonical.py
services/fuel_charge_categories.py
services/fuel_classification_persistence.py
services/fuel_classification_workflow.py
services/fuel_controls.py
services/fuel_dashboard_stats.py
services/fuel_digital_pdf_express.py
services/fuel_digital_pdf_extract.py
services/fuel_digital_pdf_nationwide_table.py
services/fuel_digital_pdf_table_geometry.py
services/fuel_digital_pdf_types.py
services/fuel_financial_responsibility.py
services/fuel_financial_responsibility_refresh.py
services/fuel_historical_resolution.py
services/fuel_ingestion.py
services/fuel_manual_canonical_projection.py
services/fuel_manual_entry_constants.py
services/fuel_manual_entry_stage.py
services/fuel_manual_entry_validation.py
services/fuel_manual_receipt_ai.py
services/fuel_manual_receipt_extract.py
services/fuel_manual_receipt_mask.py
services/fuel_manual_receipt_ocr.py
services/fuel_manual_receipt_parse.py
services/fuel_money.py
services/fuel_nationwide_canonical_projection.py
services/fuel_nationwide_card_total.py
services/fuel_nationwide_completed_basic.py
services/fuel_nationwide_correction_validate.py
services/fuel_nationwide_effective.py
services/fuel_nationwide_extraction.py
services/fuel_nationwide_import.py
services/fuel_nationwide_review.py
services/fuel_nationwide_source_reconciliation.py
services/fuel_nationwide_stage.py
services/fuel_oo_pricing.py
services/fuel_parse_preview.py
services/fuel_processed_read.py
services/fuel_provider_adapter.py
services/fuel_provider_catalog.py
services/fuel_provider_connections.py
services/fuel_provider_profile.py
services/fuel_reason_normalize.py
services/fuel_reconciliation.py
services/fuel_review.py
services/fuel_source_duplicate_gate.py
services/fuel_transaction_classify.py
```

---

### RBAC (AuthZ pilot) — 0 → 20 files (all ← NEW)

```
authz/__init__.py
authz/catalog.py
authz/coverage.py
authz/decision.py
authz/enforce.py
authz/loader.py
authz/matrix.py
authz/modules/__init__.py
authz/modules/admin.py
authz/modules/assets.py
authz/modules/dispatch.py
authz/modules/fuel.py
authz/modules/loads.py
authz/modules/payroll.py
authz/modules/people.py
authz/modules/tolls.py
authz/prospective.py
authz/registry.py
authz/routes.py
authz/shadow.py
authz/spec.py
```

*(20 paths; `modules/dispatch.py` is AuthZ matrix slice, not the legacy dispatch board.)*

---

### Tolls — 0 → 13 files (all ← NEW)

```
models/toll.py
routers/tolls.py
schemas/toll.py
services/toll_csv_intake.py
services/toll_file_history.py
services/toll_file_upload.py
services/toll_manual_entry.py
services/toll_pdf_corrections.py
services/toll_pdf_effective.py
services/toll_pdf_review.py
services/toll_process.py
services/toll_provider_catalog.py
services/toll_wvpa_pdf.py
```

---

*Other modules (POD, custody, document platform, trips): see git diff `964708ee..e3e7634 -- app/` or §Executive summary below.*

---

## Executive summary (numbers)

| Metric | Count | Notes |
|--------|------:|-------|
| **Unique paths first added** (all types, Jul 1 → present) | **661** | Deduped by path; oldest add in window per path |
| **Production `app/**/*.py` added** | **154** | All still present on disk (0 deleted) |
| **A — Genuinely new feature / module expansion** | **~125–135** | **Verified inference:** Fuel (~61), AuthZ pilot (~21), Tolls, Load parser/Lab, DW-1/I14/custody/trip slices |
| **B — Primarily fix / regression / security / validation** | **6–14** | **6 proven** by first-add commit subject `fix*`; **+8** high-confidence manual (see §B) |
| **C — Workaround / parallel while legacy remains** | **~10–14** | **8** `document_platform/**` + service shims; parser pipeline splits |
| **E — Uncertain without owner context** | **~28** | Trip/custody/POD/DL-adjacent; commit subject does not say fix/feat clearly |
| **D — Tests** (`tests/**` added) | **~140–142** | Reported separately |
| **D — Migrations** (`alembic_*/versions/*`) | **~37–38** | Reported separately |
| **D — Documentation** (`docs/**` added) | **~79** | Many are **doc tree moves** (`R100`/`R096`), not new prose |
| **Frontend** (`apps/web/**` added) | **~213** | Mostly new UI surfaces (Fuel, workspace, trips); not classified B/C here |
| **Scripts** (`scripts/**` added) | **~10** | Includes `demo_clone_runner.py` (test isolation tooling) |
| **Paths added then deleted** (any type) | **57** | Excluded from “still exists” tables; does not inflate app_py (0 app py deleted) |
| **Renames in window** | **Large doc-only** | e.g. `c05c66c` docs consolidation — **not counted as new modules** |

### Headline answer (owner question)

- **How many new application Python files in the period?** **154**
- **How many for genuinely new functionality?** **~80–90%** of app additions (**~125–135**), dominated by **Fuel** and **AuthZ**, not by one-off bug utilities.
- **How many primarily for fixes?** **At least 6** with explicit `fix` first-add commits; **up to ~14** including hardening/integrity/security files where the *first commit* used `feat`/`refactor`/`fuel:` but the *stated intent* is defect remediation (manual §B).
- **Suspected workaround/duplicate files?** **~10–14**, centered on **`document_platform`** and **parser/OpenAI/PDF indirection** (legacy `app/services/*` shims retained).

---

## Methodology and limits

1. **Addition detection:** `git log --since=2026-07-01 --diff-filter=A` — a file counts once (first add in window).
2. **Renames:** `git log --diff-filter=R` — bulk **docs** renames under `docs/_review/`; application Python renames in window are **sparse**; no mass `loads.py` → new file rename pattern found.
3. **Classification:** Commit **subject is insufficient alone** (e.g. DW-1 workspace files sometimes appear in commits titled `fix(test): …`). Per-file `git log --diff-filter=A -1` is authoritative for **introducing commit**.
4. **Inference** is labeled explicitly; uncertain rows are **E**, not guessed as B.

---

## Breakdown by module (154 `app/**/*.py` first-added)

| Module area | Approx. new `app` `.py` files | Dominant pattern |
|-------------|-------------------------------:|------------------|
| Fuel | 61 | New module (BVD, Nationwide, AI handoff, review UI backends) — **A** |
| Login/Auth + RBAC (`authz/`, password reset) | ~22 | Casbin pilot + auth hardening — **A** / **B** (reset links) |
| Tolls | ~14 | New module foundation — **A** |
| Load Parser / Lab | ~30+ | Pipeline split (semantic, mechanical, rate con, OCR) — **A** / **C** |
| Loads / workspace / integrity | ~25 | DW-1, I14 POD, custody, integrity constants — **A** / **B** |
| Trips / Dispatch / custody | ~12 | Trip completion, stop execution, custody — **A** / **E** |
| Shared core (`core/`, `utils/`, `document_platform/`) | ~12 | Guards, concurrency, platform extraction — **B** / **C** |
| People / DL | ~4 | Preprocess/OpenCV tests-adjacent — **E** |
| Payroll / Finance / Assets | ~2 | Minor |

---

## Category B — Fix-oriented new files (evidence table)

### Tier 1 — First-add commit subject starts with `fix` (verified)

| # | File | Exists | Intro commit | Date | Message | Problem | Prior owner | Why new file | Docs | Callers / original | Duplicate? | Later commits |
|---|------|--------|--------------|------|---------|---------|-------------|--------------|------|-------------------|------------|---------------|
| 1 | `app/utils/load_commercial_money.py` | Yes | [`0448545`](https://github.com/mkaamirerp/trucking-erp/commit/044854565df4c7322d1cbb4706db1a12288b60cb) | 2026-10-18 | fix(load): Decimal … (I8) | Float money at API/parser boundary (MASTER I8) | `app/schemas/load.py`, `app/services/loads.py` (I26 audit helpers) | Shared coerce across schemas, mapper, parser, mechanical validation | MASTER I8; LOAD_INTEGRITY plan §8 | Imported by `schemas/load.py`, `load_document_parse.py`, `load_workspace_draft_mapper.py`, `load_parser_semantic_to_product.py`, `load_parser_mechanical_validation.py` | `loads.py` still owns persistence/audit; **parallel money rules** | `e3e7634` non-finite guards |
| 2 | `app/core/integration_db_guard.py` | Yes | [`55bb0d14`](https://github.com/mkaamirerp/trucking-erp/commit/55bb0d1464012b33b27a3f128971772444b4b92c) | 2026-09-06 | fix(tests): isolate integration suite from demo tenant | Integration tests could mutate `tenant_demo` | Ad-hoc test env checks | Central fail-closed guard for test DB URLs | `tests/support/integration_isolation.py` | `integration_isolation`, many `tests/test_*` | Production paths unchanged; **test-only safety layer** | Multiple test-hardening commits |
| 3 | `app/constants/load_integrity.py` | Yes | [`4356514`](https://github.com/mkaamirerp/trucking-erp/commit/4356514735…) | 2026-10-14 | fix(load): I2 stop sync, I10 board bucket, I9 audit hooks | Integrity constants for board/audit/stop policy | Inline constants in services/routers | Named constants for locked integrity IDs | MASTER I2/I9/I10 | Imported by load/trip/board code paths | `loads.py` / dispatch still own behavior | Follow-on integrity commits |
| 4 | `app/services/fuel_bvd_column_map.py` | Yes | [`d6e4d8f5`](https://github.com/mkaamirerp/trucking-erp/commit/d6e4d8f569…) | 2026-09-25 | fix(fuel): harden BVD extraction fidelity | BVD column / extraction defects | Monolithic fuel parse services | Split mapping for fidelity fixes | Fuel module docs | Fuel BVD review pipeline | BVD logic also in other `fuel_*` files | Ongoing fuel fixes |
| 5 | `app/services/fuel_digital_pdf_extract.py` | Yes | [`d6e4d8f5`](https://github.com/mkaamirerp/trucking-erp/commit/d6e4d8f569…) | 2026-09-25 | fix(fuel): harden BVD extraction fidelity | Same as above | Same | Extract path separated from table geometry | Fuel docs | Nationwide/BVD ingest | Overlaps `document_platform` PDF extract | Refactors in fuel commits |
| 6 | `app/services/password_reset_links.py` | Yes | [`3225303c`](https://github.com/mkaamirerp/trucking-erp/commit/3225303c43…) | 2026-10-06 | fix: secure password reset links and JWT secrets | Auth security defect | Logic in `auth` routers/utils | Dedicated helper for origin-safe reset URLs | Auth backlog docs | Auth router/services | Old inline link building may remain elsewhere | Security follow-ups |

### Tier 2 — Manual B (fix intent; first commit **not** `fix*`)

| File | Intro commit (abbrev) | Classification rationale |
|------|------------------------|---------------------------|
| `app/services/load_parser_mechanical_validation.py` | `bb60d06` refactor(load-parser): separate semantic… | Post-model validation for parser hallucinations/tenant leakage — **validation defect layer**; not a greenfield feature |
| `app/services/load_parser_pdf_ocr.py` | `7df3513` checkpoint(load-parser): preserve production Load Gold runtime | OCR path extracted during parser remediation — **C/B border**; treat as **B** for parser correctness |
| `app/core/concurrency/draft_conflicts.py` | `dfd6333` Add load workspace draft CRUD slice… | Optimistic concurrency / 409 shaping for drafts — **defect prevention** for DW-1 race conflicts |

*Tier 2 count: 3 files — owner may reclassify to C or A.*

---

## Category C — Parallel / workaround (flagged)

| File(s) | Intro | Problem | Legacy still present? | Evidence |
|---------|-------|---------|---------------------|----------|
| `app/document_platform/**` (8 `.py` modules) | `22bf997`–`3f37829` mix of fix(dl) / docs(architecture) / refactor | DL PDF/OpenAI extraction refactor | **Yes** — `app/services/openai_chat_json_schema.py`, `app/services/pdf_text_extract.py` are **thin re-export shims** (comments point to `document_platform`) | `grep document_platform` across fuel/load/toll services |
| `app/services/openai_chat_json_schema.py` | Pre-July or shim-only growth | Compatibility facade | Implementation in `document_platform/capabilities/openai/chat_json_schema.py` | 26-line shim vs 191-line implementation |
| `app/services/pdf_text_extract.py` | Shim | Same pattern for PDF text | `document_platform.capabilities.pdf.text_extract` | Same |
| `load_workspace_draft_storage.py` vs `load_workspace_draft.py` | DW-2 vs DW-1 slices | Two storage foundations (documented DW-1/DW-2) | Both active in tree | `MASTER` / DW docs; not necessarily “abandoned” but **parallel** |
| Parser stack: `load_document_parse_rate_con.py`, `load_parser_semantic_to_product.py`, `load_lab_semantic.py`, mechanical validation | Multiple feat/refactor commits | Successive parser generations | **DeprecatedDispatchPage**-style pattern in parser: old paths kept for gold/runtime | Load parser README, MASTER I18–I22 |

**C count (conservative):** **8** `document_platform` Python modules + **2–4** shim/split patterns ≈ **10–12**.

---

## Category D — Tests, migrations, documentation (separate totals)

| Type | Approx. count | Notes |
|------|-------------:|-------|
| `tests/**` | 140–142 | Includes integration isolation, load integrity, fuel, parser, demo clone tests |
| Alembic versions | 37–38 | Tenant + platform; many tied to **features** (DW-1, I14, fuel), not “fix files” |
| `docs/**` | 79 new paths | **Inflated by renames** (`docs/` → `docs/_review/`, module folders); not 79 new audits |

**Examples (fix-related test files, not counted in app B):**

- `tests/test_load_money_audit_atomicity_issue26.py` — I26 audit atomicity (regression guard)
- `tests/test_load_commercial_money_issue8.py` — I8 money parsing
- `tests/test_demo_clone_runner.py` — disposable DB clone safety
- `scripts/demo_clone_runner.py` — operational test tooling (not `app/`)

---

## Category E — Uncertain (investigate with owner)

28 `app/**/*.py` files **not** matching bulk Fuel/AuthZ/Toll/Parser/DW-1 prefixes and **without** `fix` first-add subject. Examples:

- `app/services/load_custody.py`, `load_custody_transitions.py`, `models/load_custody_event.py` — trip/custody **feature** or integrity? (Likely **A**, commit `feat(trips)` / `feat(custody)`).
- `app/services/applicant_dl_opencv.py`, `applicant_dl_preprocess.py` — first add under `test(dl):` commit — **test-driven DL geometry** (**E** / test adjunct).
- `app/constants/custody.py`, `routers/terminals.py` — trip completion slice (**A**).

Full list available via:

```bash
git log --since=2026-07-01 --diff-filter=A --name-only --pretty=format: -- 'app/**/*.py' | sort -u
```

---

## Architectural risks (owner review)

1. **Fuel surface explosion (~61 new service modules in ~3.5 months)** — highest file velocity; risk of overlapping BVD/Nationwide/AI paths and duplicate Decimal/money rules (contrast with single `load_commercial_money.py` debate).
2. **Load domain scatter** — commercial truth still centered on `app/services/loads.py` + `schemas/load.py`, but integrity/parser/workspace/POD/custody each added **sibling modules**; hard for newcomers to find “the owner.”
3. **`document_platform` + service shims** — classic **C** pattern: two ways to call OpenAI/PDF extract; refactors incomplete while imports remain split.
4. **Parser generational stack** — mechanical validation, semantic schema, rate con v2, lab semantic, OCR; MASTER lists I18–I22 still open — risk of **gold-runtime checkpoints** (`checkpoint(load-parser)`) ossifying parallel paths.
5. **AuthZ pilot (`app/authz/*`)** — parallel authorization model vs legacy RBAC; not defect-fix proliferation but **long-term merge or retire** decision required.
6. **Small `app/utils/*` growth** — only **`load_commercial_money.py`** in window today; pattern risk if each integrity issue (I8, I9, …) adds a util instead of extending `loads.py` / `schemas/load.py`.
7. **Misleading commit subjects** — e.g. workspace draft files must not be classified as “test fixes” from commit title alone; **per-file `git log --diff-filter=A -1` required** for audits.

---

## Recommendations (documentation only — no code changes in this audit)

1. Adopt a **“extend the owner file first”** rule for Load commercial domain (`loads.py`, `schemas/load.py`) before new `app/utils/load_*`.
2. Schedule **document_platform shim retirement** — single import path for PDF/OpenAI capabilities.
3. Maintain this audit’s **Tier 1 B table** as a living list when `fix*` commits add new `app/` files.
4. Re-run counts after merging `gpt-review` → `main` with:  
   `git log --since=2026-07-01 --diff-filter=A --name-status -- 'app/'`

---

## Appendix — Commands used

```bash
git log --since='2026-07-01' --diff-filter=A --name-status --pretty=format:'%H|%ai|%s'
git log --since='2026-07-01' --diff-filter=A --format='%H|%ai|%s' -1 -- <path>
git log --since='2026-07-01' --diff-filter=R --name-status --oneline
```

---

*Report prepared locally. **STOP — not committed or pushed** per investigation charter.*
