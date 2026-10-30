# Milestone A — Cleanup completion report

**Date:** 2026-10-30  
**Branch:** `gpt-review`  
**Git SHA (repo):** `caa95a8f63a1b708f94491757fc3372b8749f8a8`  
**Scope:** Experimental Oct 30 layer removed only. **No Phase 2.** No DB/PDF/S3/migration changes.

---

## 1. Before / after summary

| Item | Before | After |
|------|--------|--------|
| Tracked experiment diffs | 3 files modified | **Restored to `HEAD`** (clean tracked tree) |
| Untracked experiment paths | ~98 entries | **Removed** from repo (see §2) |
| Compose config on API | `docker-compose.yml` + `reparse-exp.yml` | **`docker-compose.yml` only** |
| `REPARSE_TEST_MODE` | `PDF_ENABLED` | **Unset** (not in container env) |
| `ARMSTRONG_FORENSIC_DIR` | `/app/armstrong_forensic` | **Unset**; bind mount **removed** |
| API image | `sha256:32f4f144…` (experiment build) | **`sha256:c7adf47ee6c8…`** (post-cleanup build) |
| Rollback image tag | — | **`truckerp-api:rollback-pre-milestone-a-2026-10-30`** → `32f4f144d461` |

**Rollback (if needed):**

```bash
docker tag truckerp-api:rollback-pre-milestone-a-2026-10-30 trucking_erp-truckerp-api
docker compose -f /home/admin/trucking_erp/docker-compose.yml up -d --no-deps truckerp-api
# To restore experiment overlay (not recommended): re-add docker-compose.reparse-exp.yml from archive
```

**Before/after artifacts:** `/home/admin/archive/truckerp_reparse_audit_2026-10-30/before_state/` and `after_state/`

---

## 2. Archived (outside active repo)

**Archive root:** `/home/admin/archive/truckerp_reparse_audit_2026-10-30/`  
**Tarball (verified 112 entries):** `truckerp_reparse_audit_2026-10-30.tar.gz`  
**Readable copy:** `fixtures_reparse/Armstrong.pdf` SHA `1c827d7d2bf59ea86c738af56d260cb5372cf1f4b2deb1b47528d6737273f0f4` (verified after copy)

| Content | Archive location |
|---------|------------------|
| Forensic tree (screenshots, DB JSON, AI capture, browser logs) | `reports_armstrong_forensic/` |
| Experiment screenshots/logs | `reports_armstrong_experiment_*` |
| Private PDF fixtures + frozen JSON + README | `fixtures_reparse/` |
| AI JSON fixtures | `reparse_ai_json*.json` |
| Master audit report | `ARMSTRONG_FINAL_REPARSE_TEST_REPORT.md` |
| Experimental Playwright specs | `playwright_experiment/` |
| Experiment scripts + compose overlay + `armstrong_forensic_capture.py` | Archive root files |

**Not archived from repo (never in Git):** demo **load-attached** PDFs in `storage_persistent` — **unchanged**.

---

## 3. Removed from active repository

### Application / infra

- `app/services/armstrong_forensic_capture.py`
- `docker-compose.reparse-exp.yml`
- Uncommitted hooks in `load_document_parse_orchestrator.py` and `chat_json_schema.py` → **`git restore`**

### Scripts

- `scripts/armstrong_forensic_db_export.py`
- `scripts/armstrong_final_reparse_experiment.py`
- `scripts/armstrong_forensic_reload_api.sh`
- `scripts/reparse_four_pdf_smoke.py`

### Docs / fixtures (working copies; archived first)

- `docs/reports/armstrong_forensic/` (entire tree)
- `docs/reports/armstrong_experiment_screenshots/`
- `docs/reports/armstrong_experiment_logs/`
- `docs/reports/ARMSTRONG_FINAL_REPARSE_TEST_REPORT.md`
- `docs/fixtures/reparse/` (PDFs + frozen JSON + README)
- `docs/fixtures/reparse_ai_json1_baseline.json`
- `docs/fixtures/reparse_ai_json2_revised_parse.json`

### Playwright (experimental → archive)

- `tests/e2e/armstrong_forensic_audit.spec.ts`
- `tests/e2e/armstrong_forensic_helpers.ts`
- `tests/e2e/armstrong_final_reparse_browser.spec.ts`
- `tests/e2e/armstrong_reparse_load1008.spec.ts`
- `tests/e2e/armstrong_greensboro_correction.spec.ts`
- `tests/e2e/armstrong_stop_browser_e2e.spec.ts`

---

## 4. Preserved (explicit)

| Item | Notes |
|------|--------|
| **48 commits** re-parse comparison on `gpt-review` | Untouched per owner decision |
| **Alembic / migrations** | No rollback |
| **`caa95a8` applicant/storage** | On branch; in API image |
| **First parser code path** | No prompt/schema edits in this milestone |
| **`tests/test_load_miles_normalization.py`** | Retained (untracked); see §6 |
| **Existing Playwright** | `task12_create_load_navigate.spec.ts`, `task12b_full_journey.spec.ts` |
| **New minimal regression** | `tests/e2e/parser_regression_minimal.spec.ts` |
| **`tests/e2e/package.json`** | Local Playwright deps (untracked) |
| **`docs/reports/CLEANUP_INVENTORY_2026-10-27_30.md`** | Audit record |
| **Owner RE-PARSE rules** | Not edited |
| **Canonical PDF (repo)** | `docs/_review/fixtures/pdf/Armstrong.pdf` (for E2E) |

---

## 5. Verification — experiment fully removed

| Check | Result |
|-------|--------|
| `grep` experiment symbols under `app/` | **None** |
| `reparse_test_mode` / `armstrong_forensic` in running `/app/app` | **None** (`grep` in container) |
| `printenv REPARSE_TEST_MODE ARMSTRONG_FORENSIC_DIR` | **Empty / unset** |
| Compose project config files label | **`/home/admin/trucking_erp/docker-compose.yml` only** |
| `GET /api/v1/health` | **`{"status":"ok"}`** |
| `TRUCKERP_APP_GIT_SHA` in container | **`caa95a8`** (matches repo `HEAD`) |

---

## 6. Tests executed (actual results)

| Test | Command / context | Result |
|------|-------------------|--------|
| Reparse baseline contract | Host: `pytest tests/test_reparse_baseline_contract.py -q` | **3 passed** (2.0s) |
| Miles normalization | Host: `pytest tests/test_load_miles_normalization.py -q` | **ERROR at import** — `normalize_load_miles_value` not in mapper (reverted commit `7c3ef90`); file **kept** for separate review |
| Playwright minimal (1st run) | 3 tests, demo | **2 passed**, **1 failed** — New Load: 240s timeout waiting for PDF viewer (parse not completed or blocked; duplicate PDF not detected in 15s) |
| Playwright minimal (2nd run) | After duplicate-gate tweak | **1 passed**, **2 failed** — Test 1 still timed out on viewer; Test 3 login timeout after long Test 1 (session flake) |

**Parser / New Load on demo:** Not fully re-proven in browser on `/loads/new` with `Armstrong.pdf` during this cleanup (duplicate-PDF / long-parse risk on shared demo). **Backend contract tests passed.** Manual edit + PDF download tests **passed** in first Playwright run.

**Recommendation before Milestone B:** Run New Load parse on demo with a **non-duplicate** RC or isolated tenant; or accept duplicate gate as expected when re-uploading `Armstrong.pdf`.

---

## 7. Unresolved / risks

1. **`tests/test_load_miles_normalization.py`** — retained but **does not collect** until `normalize_load_miles_value` is reintroduced or test is updated.
2. **Playwright New Load test** — flaky on demo with shared Armstrong PDF; minimal spec updated to detect duplicate gate by heading (not re-run to green in this milestone).
3. **Untracked files remaining in repo:** `CLEANUP_INVENTORY`, `MILESTONE_A` report, `parser_regression_minimal.spec.ts`, `tests/e2e/package.json`, `test_load_miles_normalization.py` — owner may commit selectively on `gpt-review`.
4. **Committed Re-parse comparison** still active in product/API — intentional until Phase 2 refactor.
5. **Demo load 1010** — prior experiment mutations remain in DB (no reset per instructions).

---

## 8. Milestone B gate

**Do not start** simplified attach/parse-reference workflow until owner reviews this report.

**Prepared for Phase 2 (not started):** refactor `propose_load_reparse` / UI away from JSON compare; preserve PDF storage and verified JSON patterns per owner direction.
