# Cleanup inventory — Oct 27–30, 2026 (Re-parse experiment + branch work)

**Purpose:** Phase 1 audit only. **No cleanup has been executed.** Phase 2 (simplified parser workflow) must not start until the owner approves actions below.

**Audit scope:** Git history `2026-10-27` … `2026-10-30`, working tree, untracked files, running `truckerp-api` container.

**Branch:** `gpt-review` @ **`caa95a8`** (synced with `origin/gpt-review` for that commit).

**Working tree (before any cleanup):**

- **3 modified tracked files** (experiment hooks; not committed)
- **~98 untracked paths** (fixtures, reports, Playwright, scripts)
- **Running API** built from **local tree including experiment code**, with **compose overlay** active

---

## Executive summary

| Layer | What happened | Cleanup stance |
|-------|----------------|----------------|
| **A. Oct 30 local experiment** | Armstrong audit, `REPARSE_TEST_MODE`, forensic capture, Playwright suite, compose overlay | **Remove from repo + restore container config** after approval |
| **B. Oct 27–30 committed on `gpt-review`** | Full **AI comparison Re-parse** product (48 commits, 57 unique paths), RC revision/snapshot migrations, UI dialog | **Not “blind delete”** — conflicts with new Phase 2 direction; **owner review** (replace in Phase 2 vs revert commits) |
| **C. Oct 30 `caa95a8`** | Applicant file pointer + storage hardening | **Preserve** — unrelated to Re-parse experiment |
| **D. Demo runtime** | Load **1010** mutated by experiments; storage local | **Do not reset DB/PDFs** per instructions |

**First parser (New Load):** Lives in existing parse orchestration / product parser paths on `gpt-review`. Experiment code does **not** replace it; removing **Category 1** does not remove first-parse behavior. **Proof after cleanup:** New Load parse unchanged at committed baseline once experiment diffs are reverted and API recreated **without** overlay.

---

## Running configuration (must fix on cleanup)

Evidence collected **2026-10-30**:

| Setting | Repository default | **Running `truckerp-api` now** |
|---------|-------------------|--------------------------------|
| Compose files | `docker-compose.yml` only | **`docker-compose.yml` + `docker-compose.reparse-exp.yml`** (label on container) |
| `REPARSE_TEST_MODE` | unset | **`PDF_ENABLED`** |
| `ARMSTRONG_FORENSIC_DIR` | unset | **`/app/armstrong_forensic`** |
| Bind mount | none for forensic | **`…/docs/reports/armstrong_forensic/capture` → `/app/armstrong_forensic`** |
| Image contents | Last `docker compose build` from worktree | Includes **uncommitted** orchestrator + anthropic forensic hooks |

**Proposed action after approved cleanup:**

1. Discard or revert Category 1 source changes.
2. Recreate API with **`docker compose -f docker-compose.yml up -d --no-deps truckerp-api`** (no overlay) and rebuild from approved commit tree.
3. Verify: `docker inspect truckerp-api` shows **only** `docker-compose.yml`; `printenv REPARSE_TEST_MODE` empty.

---

## Category 1 — Experimental code to remove

Remove from the **active codebase** and from **API image** (rebuild required). None of this is required for the **first** New Load parser.

| Path | Evidence | Purpose | Depends on | Proposed action |
|------|----------|---------|------------|-----------------|
| `app/services/armstrong_forensic_capture.py` | Untracked; Oct 30 | Writes sanitized JSON when `ARMSTRONG_FORENSIC_DIR` set | Called from uncommitted orchestrator + anthropic | **Delete** from repo |
| `app/services/load_document_parse_orchestrator.py` (uncommitted hunk) | `git diff` +129 lines | `reparse_test_mode()`, `JSON_ONLY` frozen JSON2, `_present_reparse_changes` experiment branch, `_experiment` payload, forensic `write_forensic` | `ground_reparse_changes` (production module) | **Revert** to `HEAD` (`git restore`) |
| `app/document_platform/capabilities/anthropic/chat_json_schema.py` (uncommitted) | `git diff` +24 lines | Forensic capture on every Anthropic JSON call | `armstrong_forensic_capture` | **Revert** to `HEAD` |
| `docker-compose.reparse-exp.yml` | Untracked Oct 30 | Env + volume for experiment | Used by running container | **Delete**; recreate container without it |
| `scripts/armstrong_forensic_reload_api.sh` | Untracked | Builds API with overlay + `REPARSE_TEST_MODE` | compose overlay | **Delete** |
| `scripts/armstrong_forensic_db_export.py` | Untracked | Read-only load bundle for audit | docker exec | **Delete** from repo (optional keep in **archive** tarball) |
| `scripts/armstrong_final_reparse_experiment.py` | Untracked | API-side Test 1 parse (bypasses UI) | product parser | **Delete** |
| `scripts/reparse_four_pdf_smoke.py` | Untracked | PDF smoke + optional `propose_load_reparse` | committed re-parse API | **Delete** (or archive); not needed for first parser |
| `tests/e2e/armstrong_forensic_audit.spec.ts` | Untracked | 5-test forensic Playwright | helpers, demo login | **Delete** |
| `tests/e2e/armstrong_forensic_helpers.ts` | Untracked | Screenshots, DB export from tests | docker | **Delete** |
| `tests/e2e/armstrong_final_reparse_browser.spec.ts` | Untracked | Test 1 browser | fixtures | **Delete** |
| `tests/e2e/armstrong_reparse_load1008.spec.ts` | Untracked | Re-parse popup on 1008 | `_review` PDF path | **Delete** |
| `tests/e2e/armstrong_greensboro_correction.spec.ts` | Untracked | First-parse promote Greensboro fix | `_review` Armstrong PDF | **Delete** from repo or move to archive (operator E2E, not product code) |
| `tests/e2e/armstrong_stop_browser_e2e.spec.ts` | Untracked | Stop browser E2E | — | **Delete** or archive |
| `tests/e2e/playwright.config.ts` (uncommitted) | `testMatch` line | Broaden test glob | — | **Revert** unless a minimal E2E remains approved |
| `tests/e2e/package.json`, `package-lock.json` | Untracked | Local Playwright install | — | **Delete** from repo if no approved E2E kept |
| `tests/e2e/test-results/` | Untracked | Playwright output | — | **Delete** (generated) |
| `docs/fixtures/reparse/frozen_armstrong_2000_parse.json` | Untracked | Mode B JSON2 | `JSON_ONLY` path | **Delete** from repo |
| `docs/fixtures/reparse_ai_json1_baseline.json` | Untracked | Experiment compare fixture | — | **Delete** from repo |
| `docs/fixtures/reparse_ai_json2_revised_parse.json` | Untracked | Source for frozen JSON2 | — | **Delete** from repo |
| `docs/fixtures/reparse/README.md` | Untracked | Points to smoke scripts | — | **Delete** or archive |

**Environment variables to clear everywhere:** `REPARSE_TEST_MODE`, `REPARSE_TEST_JSON2_PATH`, `ARMSTRONG_FORENSIC_DIR`, `REPARSE_FIXTURE_DIR` (scripts only).

---

## Category 2 — Generated tests, logs, reports (archive outside active project)

**Do not commit** to Git. Move to a **dated private archive** on the host (example: `/home/admin/archive/truckerp_reparse_audit_2026-10-30/`), then remove from `/home/admin/trucking_erp`.

| Path | Evidence | Contents | Proposed action |
|------|----------|----------|-----------------|
| `docs/reports/armstrong_forensic/` (71 files) | Oct 30 Playwright + capture mount | Screenshots, DB JSON exports, sanitized AI capture, browser logs | **Tar/archive** → remove from repo |
| `docs/reports/armstrong_experiment_screenshots/` | Oct 30 | `test1-after-parse.png` | **Archive** |
| `docs/reports/armstrong_experiment_logs/test1_first_parse_armstrong_1800.json` | Oct 30 script | API parse log | **Archive** |
| `docs/reports/ARMSTRONG_FINAL_REPARSE_TEST_REPORT.md` | Oct 30 | Master audit narrative | **Archive** (findings useful for Phase 2) |
| `docs/reports/CLEANUP_INVENTORY_2026-10-27_30.md` | This file | Inventory | **Keep in repo** until cleanup done, then optional move to archive |

### Private PDF fixtures (preserve, do not publish)

| Path | SHA-256 (reference) | Proposed action |
|------|---------------------|-----------------|
| `docs/fixtures/reparse/Armstrong.pdf` | `1c827d7d…` | **Copy to private archive**; **do not** commit; remove from repo tree |
| `docs/fixtures/reparse/Armstrong_TEST_rate_2000.pdf` | `73552d5e…` | Same |
| `docs/fixtures/reparse/BM2.pdf` | `3c78c6ad…` | Same |
| `docs/fixtures/reparse/JBHunt.pdf` | `c9b67a74…` | Same |

**Existing canonical copy:** `docs/_review/fixtures/pdf/Armstrong.pdf` (used by older tests) — **preserve**; confirm still present after cleanup.

---

## Category 3 — Existing production functionality to preserve

### First parser (New Load) — **keep unchanged** for Phase 2 scope

Committed on `gpt-review` (not experiment-local):

- `app/services/load_document_product_parser.py` / guarded parse pipeline (via orchestrator for workspace)
- `apps/web` New Load upload → parse → review → Create load
- `load_commercial_evidence.accepted_parse_json` on promote
- Owner rules: first parse sends PDF to AI ( `.cursor/rules/owner-product-rules.mdc` — **note:** RE-PARSE subsection will need owner update when Phase 2 lands)

**Experiment did not commit changes** to the first-parse contract; uncommitted hooks only **log** Anthropic calls when env set.

### Oct 30 security / storage (committed `caa95a8`) — **keep**

| Path | Purpose |
|------|---------|
| `app/core/storage.py` | Path traversal / safe read |
| `app/routers/driver_onboarding.py` | Applicant cannot rewrite file pointers |
| `tests/test_applicant_file_access.py`, `tests/test_storage.py` | Regression |

### Other Oct 27–30 committed work **not** experiment-local — **keep unless Phase 2 explicitly replaces**

| Path | Purpose |
|------|---------|
| `apps/web/src/utils/loadStops.ts` (+ test) | Route display city/state (588752f) |
| `apps/web/src/loadWorkspace/loadParseHydrationState*` | Customer rate / hydration locks (7ae9ec0) |
| `apps/web/src/loadWorkspace/DuplicateLoadParseGateDialog.tsx` | Same-PDF gate → re-parse on existing load |

---

## Category 4 — Uncertain / owner review required

These are **real product changes** on `gpt-review` (Oct 27–30), **not** the Oct 30 Armstrong experiment layer. Discontinuing **AI-to-AI Re-parse comparison** (Phase 2) affects this group; **do not** mass-delete without a replacement design.

### 4A — Committed Re-parse comparison stack (48 commits, 57 files)

**First commit in window:** `dd8efd3` (2026-10-27) — compare revised RC to saved load.

**Core backend**

| Path | Role |
|------|------|
| `app/services/load_document_parse_orchestrator.py` (committed) | `propose_load_reparse`: PDF re-parse + **`load_reparse_changes` AI compare** + signed proposal |
| `app/services/load_workspace_draft_document.py` | `validate_ai_reparse_changes`, `ground_reparse_changes`, `_supported_reparse_differences`, diff helpers |
| `app/services/load_document_parse_semantic_llm.py` | Compare / semantic paths touched in c23bb25 |
| `app/routers/loads.py` | `POST …/rate-confirmation-reparse`, `…/save` |
| `app/schemas/load_document_parse.py` | Reparse proposal / integrity schemas |
| `app/services/loads.py` | Revised PDF persistence, read paths |
| `app/authz/routes.py` | RBAC for reparse endpoints |

**Frontend**

| Path | Role |
|------|------|
| `apps/web/src/pages/LoadWorkspacePage.tsx` | Re-parse flow, save coupling |
| `apps/web/src/loadWorkspace/ReparseChangesDialog.tsx` | Comparison popup, Use new value |
| `apps/web/src/loadWorkspace/RateConfirmationPdfPanel.tsx` | RC display / revised docs |
| `apps/web/src/api.ts` | Client API |

**Tests (committed)**

| Path | Role |
|------|------|
| `tests/test_reparse_replacement.py` | Main re-parse behavior suite |
| `tests/test_reparse_baseline_contract.py` | Baseline contract |
| `tests/test_reparse_text_diff.py` | Text-diff experiment tests (commits reverted; **file may be stale**) |
| `tests/test_rate_confirmation_revision_*.py` | Revision acceptance/compare |
| `tests/test_verified_parse_reconcile.py` | Verified JSON reconcile |

**Reverted on branch (already removed behavior, files may remain):** one-shot text-diff LLM (`43d6f69` reverted by `3027129`), miles normalization import (`75bd638` reverted by `7c3ef90`), etc.

**Owner review question:** For Phase 2, should this stack be **surgically refactored** (remove compare AI; add attach + optional parse-only reference UI) or **reverted toward pre-`dd8efd3`** and re-implemented cleanly?

### 4B — Schema / migrations (high impact)

| Path | Role |
|------|------|
| `alembic_tenant/versions/rc01_rate_con_revision_*.py` | Rate confirmation **revision** tables |
| `alembic_tenant/versions/s1_load_approved_snapshot_*.py` | Approved commercial snapshot |
| `app/models/load_rate_confirmation_revision.py`, `load_approved_commercial_snapshot.py` | Models |
| `app/services/load_rate_confirmation_revision.py`, `load_approved_commercial_snapshot.py` | Services |
| `alembic_tenant/load_*_ddl.py`, `scripts/tenant_revision_plan.py` | Migration helpers |

**Owner review:** Phase 2 requires **billing-visible original + revised PDFs**. These migrations may still be needed for **document history** even if AI compare is removed. **Do not drop migrations** without tenant DB impact review.

### 4C — Documentation / rules vs new direction

| Path | Issue |
|------|--------|
| `.cursor/rules/owner-product-rules.mdc` § RE-PARSE (2026-10-28) | Describes **JSON1/JSON2 AI compare** popup — **conflicts** with Phase 2 simplified workflow |
| `docs/load_parser/README.md` | Updated in window; references re-parse / verification |
| `TODO.md` | RC verification acknowledgement TODO |

**Proposed action:** Owner updates rules/docs **after** Phase 2 design is agreed — not part of Category 1 delete.

### 4D — Untracked test helper (related to reverted miles commit)

| Path | Evidence | Proposed action |
|------|----------|-----------------|
| `tests/test_load_miles_normalization.py` | Untracked; references `normalize_load_miles_value` | **Owner review:** keep if miles normalization is still desired on `LoadUpdate`/reparse; else delete. Not part of Armstrong experiment. |

### 4E — Demo data

| Item | Evidence | Proposed action |
|------|----------|-----------------|
| Load **1010** | Forensic DB exports | **Do not delete**; may confuse future tests — document as audit artifact |
| Load **1008** | Prior re-parse experiments | **Preserve** |

---

## Git commit map (Oct 27–30, selective)

| Commits | Theme | Category |
|---------|-------|----------|
| `dd8efd3` … `c23bb25`, `7da2402`, … `0658ce9` | Re-parse compare + UI + save | **4A** |
| `43d6f69` … `3027129` | Text-diff / miles experiment **reverted** | **4A** (verify dead code/tests) |
| `588752f`, `7ae9ec0` | Stops display + customer rate hydration | **3** |
| `caa95a8` | Applicant/storage security | **3** |

Full list: `git log --since=2026-10-27 --until=2026-10-31 --oneline`

---

## Phase 2 impact preview (after cleanup — not started)

Align implementation to owner Phase 2 spec:

| Current (committed) | Target |
|---------------------|--------|
| Re-parse → PDF parse + **AI JSON compare** → popup applies fields | **Attach revised PDF** (no auto field change) + optional **same first parser** for **reference only** |
| `rate-confirmation-reparse` proposal/save drives field + PDF updates | Split: billing attachment API vs optional parse-for-reference UI |
| `ReparseChangesDialog` comparison table | Replace with attach + parse review UX (no JSON1/JSON2 compare) |

**Files likely touched in Phase 2 (for planning only):** Category **4A** backend + frontend + tests; **not** Category 1 experiment files.

**Out of scope for Phase 2 per owner:** new 18-test framework, `REPARSE_TEST_MODE`, global S3 migration.

---

## Recommended cleanup sequence (after owner approval)

1. **Archive** Category 2 to `/home/admin/archive/truckerp_reparse_audit_2026-10-30/` (tar `docs/reports/armstrong_*`, fixtures PDFs, forensic dir).
2. **Revert/delete** Category 1 paths; `git restore` on 3 modified tracked files.
3. **Rebuild & recreate** `truckerp-api` with **only** `docker-compose.yml`; confirm env vars unset.
4. **Verify first parser:** Playwright or manual — `/loads/new`, upload Armstrong from **private archive**, parse, confirm form hydrates (read-only DB optional).
5. **Record after state:** `git status`, `docker inspect` env, health check — attach to cleanup completion report.

**Explicitly forbidden in cleanup:** `git reset --hard` across 3 days of commits, `git clean -fd` without archive, tenant DB reset, deleting demo loads/PDFs, S3 config changes, production deploy.

---

## Cleanup completion proof (to fill after approved cleanup)

| Check | Before (2026-10-30 audit) | After (pending) |
|-------|---------------------------|-----------------|
| `git status --porcelain` count | ~101 lines | _TBD_ |
| `REPARSE_TEST_MODE` in container | `PDF_ENABLED` | _TBD: empty_ |
| Compose config files on container | 2 files (with overlay) | _TBD: 1 file_ |
| `reparse_test_mode` in `/app` image | present (local build) | _TBD: absent at `HEAD`_ |
| New Load parse smoke | not re-run in this audit | _TBD_ |

---

## Owner decisions requested

1. **Approve Category 1 removal + Category 2 archive paths** as listed?
2. **Phase 2 strategy for Category 4A:** refactor in place vs revert to pre-reparse baseline on `gpt-review`?
3. **Keep `tests/test_load_miles_normalization.py`?**
4. **Keep any Playwright spec** under `tests/e2e/` for Phase 3 verification, or run ad hoc commands only?
5. **Update `.cursor/rules/owner-product-rules.mdc` RE-PARSE section** as part of Phase 2?

**Stop:** Awaiting owner review of this inventory before executing cleanup or Phase 2 implementation.
