# PDF / Load Lab pipeline — repo cleanup (2026-04-27)

**Rules followed:** no new features; WIP parked in `git stash` (not deleted); `main` remains the source of truth for the PDF/semantic/Load Lab pipeline. No changes to `apps/web` theme, `docker-compose` certbot wiring, `app/routers/me.py`, or seed SQL on disk after cleanup.

## Summary

- **Kept (on `main`, clean working tree):** committed PDF/Load Lab code, schemas, services, tools, and documentation listed below.
- **Stashed:** all local modifications and the listed untracked paths that were not part of the committed pipeline (full stash message recorded below).
- **Deleted:** nothing was removed from the repository as part of this cleanup.

## Files stashed (review with `git stash show -p stash@{0}`)

Stash: **`stash@{0}`**  
Message: `WIP parked: PDF-pipeline-cleanup 2026-04-27 (web/theme, me, docker-compose, seeds, certbot, load-lab UI drafts, workspace load form)`

| Area | Paths |
|------|--------|
| Router | `app/routers/me.py` |
| Web app (broad) | `apps/web/` (all tracked changes + new files under that tree) |
| Compose | `docker-compose.yml` |
| Seed SQL | `app/scripts/seed_brokers_trucking_me.sql`, `app/scripts/seed_platform_global_booking_brokers_trucking_me.sql` |
| Certbot | `infra/certbot/` |

**Included in stash (untracked, now stored in stash only):** e.g. `apps/web/src/pages/LoadLabPage.tsx`, `apps/web/src/loadWorkspace/applyLoadDocumentParseResponse.ts`, `apps/web/src/theme/`, and other WIP under `apps/web/`.

**Restore later (when ready to continue WIP):**  
`git stash pop` (or `git stash apply stash@{0}`) — resolve conflicts on `main` if the branch has moved.

## Files kept (representative — committed on `main`)

**Backend — semantic / parse / critical contract**

- `app/services/load_lab_semantic.py` — default `truckerjson` + `critical_v1_1` path, merge, post-AI repairs.
- `app/services/load_lab_truckerjson_prompt.py` — full-form + high-risk instruction overlay.
- `app/services/critical_extraction_v11_*.py`, `app/services/critical_extraction_v11_guardrails.py`, `app/services/critical_extraction_v11_map.py`
- `app/services/load_document_parse.py` — pypdf/regex parse path
- `app/services/load_lab_*.py` (diagnostics, reference extract, review, broker matrix, grounding, contact email diagnostics, etc.)
- `app/services/extraction_field_learning.py` (Load Lab learning snapshots)
- `app/routers/load_lab.py`
- `app/schemas/load_document_parse.py`, `app/schemas/load_lab_semantic.py`, `app/schemas/critical_extraction_v11.py`, related load schemas

**Tools**

- `tools/run_load_lab_contract_pair_eval.py`  
- `app/scripts/compare_load_lab_contracts_eval.py` (if present on branch)

**Docs & JSON (examples / contracts)**

- `docs/CRITICAL_EXTRACTION_CONTRACT_v1.1.json.md`, `docs/load_document_parse_hydration_full.json`, `docs/LOAD_LAB_*`, `docs/PDF_LOAD_PIPELINE.md`, `docs/LOAD_LAB_REAL_PDF_EVALUATION.md`, comparison report, eval fixtures, etc.

*Note:* `app/services/loads.py` and `app/schemas/load.py` are general load domain; they remain tracked for the product; they are not stashed as they had no uncommitted diff in this cleanup.

## Git status after cleanup

Run: `git status` — expect **clean** working tree, **`main` aligned with `origin/main`**, no deleted tracked files.

## Latest commit on `main` (at time of report)

After staging the cleanup and committing this file:

**Tip after cleanup:** the commit that added this file is the repo tip: run `git log -1 --oneline`.  
Parent of that commit is `3c5238ce` (truckerjson full-form + high-risk overlay). Publish: `git push origin main`.
