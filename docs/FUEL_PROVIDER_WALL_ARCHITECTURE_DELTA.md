# Fuel provider wall — architecture delta and file map

**Status:** Planning / boundary lock (no refactor until this map is approved).  
**Branch context:** `feat/fuel-card` with live BVD + Nationwide staging → Process → canonical batches.  
**Authoritative design:** `docs/FUEL_CARD_MODULE_DESIGN.md` (provider-native evidence before canonical meaning; one parser + provider profiles, not one engine per provider).

---

## 1. Locked funnel (do not drift)

```
SOURCE
  PDF / CSV / API
       ↓
IDENTIFY PROVIDER
       ↓
ONE PARSE / VALIDATE ORCHESTRATOR
       ↓
provider-specific profile / rules
       ↓
provider-native staging / evidence
       ↓
review / corrections
       ↓
provider reconciliation gates
       ↓
PROCESS  ──►  ════════════ PROVIDER WALL ════════════
       ↓
canonical fuel_source_batches
canonical fuel_source_controls
canonical fuel_transactions
       ↓
ONE TRUCKERP FUEL PIPELINE
       ↓
mapping / classification
truck / driver / owner
financial responsibility
O/O pricing
settlement candidate
history / search / dashboard / reporting
```

### 1.1 What “preserve Process” means

- **Now:** Preserve proven **behavior** of BVD and Nationwide Process (reconciliation gates, idempotency, duplicate gate, canonical finalize semantics). Do not break demo acceptance paths while refactoring.
- **End state:** Process is **one shared orchestration**, not one lifecycle per provider:

```text
process_fuel_import(import_id, provider_profile)
  → build effective accepted rows
  → provider reconciliation rules
  → provider-native permanent acceptance (fuel_bvd | fuel_nationwide | …)
  → canonical mapping (profile-driven projector)
  → fuel_source_controls + fuel_transactions
  → finalize batch
```

BVD / Nationwide / WEX code supplies **differences** (extractors, row shapes, reconciliation rules, column renderers), not separate **application workflows** after the wall.

### 1.2 Post-wall history and “open statement”

**Wrong end state**

- `list_bvd_history()` + `list_nationwide_history()` + `merge_everything()`
- Separate processed overlay components per provider for search, filters, and navigation

**Right end state**

- `list_processed_fuel()` (and `get_processed_fuel(import_id)`) reading **canonical finalized batches** + shared summary projection
- One Fuel processed viewer shell; **provider-specific column renderers** when showing full native source rows:
  - `provider = NATIONWIDE` → Nationwide native columns
  - `provider = BVD` → BVD native columns

Provider differences in **presentation of source evidence** are legitimate. Duplicate **workflows** (history API, dashboard merge, Open routing, Process entrypoints) are not.

---

## 2. Architecture delta (today → target)

| Layer | Today | Target |
|--------|--------|--------|
| Parse / extract | Shared `fuel_digital_pdf_extract.py` + profiles; BVD also has `fuel_bvd_extraction.py`; Nationwide has `fuel_nationwide_extraction.py` + `fuel_digital_pdf_nationwide_table.py` | One orchestrator entry; provider hooks = profile + optional table/CSV adapter modules |
| Staging | Parallel table families (`fuel_bvd_import_stage` / `fuel_nationwide_import_stage`) | Keep **per-provider staging tables**; shared stage **lifecycle** API (create, save review, discard, process) |
| Source reconciliation | `fuel_bvd_source_reconciliation.py` vs `fuel_nationwide_source_reconciliation.py` | Keep **per-provider rules**; invoke from shared Process prelude |
| Process | `process_bvd_import_review` → `process_stage_to_permanent` vs `process_nationwide_import_review` → `process_nationwide_stage_to_permanent` | `process_fuel_import(...)` with provider profile registry |
| Canonical projection | `project_bvd_rows_to_canonical` vs `project_nationwide_rows_to_canonical` (duplicate structure) | Shared `finalize_batch` + **provider mapper** implementing one interface |
| Segment 8 canonical review | `fuel_review.py` on `fuel_source_batches` (batch queue) | Unchanged role; BVD/Nationwide **staging** path must land on same batch semantics at Process |
| Segment 9 reconciliation | `fuel_reconciliation.py` on canonical rows | **SHARED ALREADY** — post-wall only |
| History / activity | `GET /fuel/bvd/history` + `GET /fuel/nationwide/history`; frontend `mergeFuelCompletedHistory` | `GET /fuel/processed` (or batches query) keyed by `fuel_source_batches` |
| Dashboard | `processed_last_7_days` uses canonical batches (good); `needs_review` counts **BVD stage + legacy fuel_bvd only** (gap) | Single counts over all active provider stages + legacy rules per provider |
| Frontend home | `FuelMainPage` dual upload/history/overlay; `FuelBvdCompletedBasic` type name for all providers | Provider-agnostic activity DTO; provider only for upload + native viewer |
| Routes | `/fuel/bvd/...` and `/fuel/nationwide/...` mirrors | Long term: `/fuel/imports/{id}/...` with `provider_code` on resource; provider paths may remain as aliases during migration |

---

## 3. Architectural acceptance gate: `TEST_PROVIDER`

Add a **fictitious** provider `TEST_PROVIDER` with **one** transaction fixture and minimal profile JSON.

**Pass:** Wire extract → stage → review → process → canonical row → appear in shared history → expand/open uses **shared** shell + TEST column renderer.

**Fail (architecture rejected):** Any new provider requires a new:

- history list function or HTTP route dedicated to that provider
- dashboard merge function
- search implementation
- Process workflow component
- settlement/classification **entry** path (post-wall classification may stay shared; only **source** tables differ)

Existing duplication (BVD + Nationwide) is **documented debt** to remove, not a pattern to extend for WEX.

---

## 4. Known symptom (approved diagnosis, fix deferred)

Recent Activity expand on Fuel home (`FuelRecentActivitySection.tsx`):

1. **Branch order:** Renders `ProcessedStatementWorkspace` when `chargeCount > 0` **before** checking `nationwideRows`. Nationwide sets `chargeCount` from TRANSACTION rows but leaves `sourceRows` empty → BVD workspace with empty charges.
2. **Hardcoded label:** `ProcessedStatementWorkspace` titles rows `BVD {invoiceNumber}` regardless of provider.

This is **BVD plumbing as default Fuel plumbing**, not a Nationwide parse failure. Fix belongs in the **MUST BECOME SHARED** bucket (single expand viewer), not a Nationwide-only patch—unless an emergency UX fix is approved before refactor.

---

## 5. File-level target map

Legend:

- **K** — KEEP PROVIDER-SPECIFIC  
- **M** — MUST BECOME SHARED (or shared interface with provider plugins)  
- **S** — SHARED ALREADY — DO NOT DUPLICATE  

### 5.1 Backend — router

| File / symbol | Cat | Notes |
|---------------|-----|--------|
| `app/routers/fuel.py` — `list_fuel_providers`, connections, catalog | S | Platform catalog |
| `app/routers/fuel.py` — `get_fuel_dashboard_stats` | M | Handler OK; stats service incomplete for Nationwide staging |
| `app/routers/fuel.py` — Segment 8 `list_fuel_review_queue`, `process_fuel_batch_review`, reconciliation | S | Canonical batch queue (post-parse ingestion path) |
| `app/routers/fuel.py` — `upload_bvd_import`, `list_bvd_*`, `process_bvd_import_review`, document | M | Collapse to provider-scoped import resource + shared handlers |
| `app/routers/fuel.py` — `upload_nationwide_import`, `list_nationwide_*`, `process_nationwide_import_review`, document | M | Mirror of BVD routes — same target |
| `app/routers/fuel.py` — `list_bvd_import_canonical_transactions`, classification endpoints | M | Today BVD-import-scoped; should be **batch / import** scoped with `provider_code`, one router surface |

### 5.2 Backend — ingestion, profiles, shared parse

| File | Cat | Notes |
|------|-----|--------|
| `app/services/fuel_provider_catalog.py` | S | |
| `app/services/fuel_provider_connections.py` | S | |
| `app/services/fuel_provider_adapter.py` | S | Future API/CSV fetch boundary |
| `app/services/fuel_provider_profile.py` | S | Profile loader; forbids per-provider parser modules |
| `app/contracts/fuel_provider_profiles.json` | K | Per-provider rules; not duplicated per engine |
| `app/services/fuel_ai_handoff.py` | S | Routes to profile + contract |
| `app/services/fuel_ai_contract.py` | S | |
| `app/services/fuel_digital_pdf_extract.py` | S/M | Shared engine; extend via profile, not fork |
| `app/services/fuel_digital_pdf_table_geometry.py` | S | Geometry helper |
| `app/services/fuel_digital_pdf_express.py` | K | BVD express line shapes (profile-invoked) |
| `app/services/fuel_digital_pdf_types.py` | S | |
| `app/services/fuel_ingestion.py` | S | Canonical row role routing |
| `app/services/fuel_controls.py` | S/M | Shared control typing; small Nationwide label helpers may stay or move to profile |

### 5.3 Backend — BVD provider-native

| File | Cat | Notes |
|------|-----|--------|
| `app/services/fuel_bvd_extraction.py` | K | BVD PDF → staged rows |
| `app/services/fuel_bvd_import.py` | K/M | Import persistence; `list_bvd_completed_history` → shared history |
| `app/services/fuel_bvd_stage.py` | K/M | Stage tables + `process_stage_to_permanent` core → shared process funnel |
| `app/services/fuel_bvd_review.py` | K/M | Review + `process_bvd_import_review` facade → thin wrapper over shared process |
| `app/services/fuel_bvd_effective.py` | K | Effective values for review |
| `app/services/fuel_bvd_correction_validate.py` | K | |
| `app/services/fuel_bvd_source_reconciliation.py` | K | Provider reconciliation gate |
| `app/services/fuel_bvd_column_map.py` | K | |
| `app/services/fuel_bvd_document_identity.py` | K | |
| `app/services/fuel_bvd_canonical_projection.py` | K/M | `project_bvd_rows_to_canonical` = provider mapper; `finalize_batch` → S |
| `app/services/fuel_bvd_completed_basic.py` | K/M | Summary projection; consume from shared `list_processed_fuel` |
| `app/models/fuel.py` — `FuelBvd`, corrections, stage tables | K | Permanent + staging evidence |

### 5.4 Backend — Nationwide provider-native

| File | Cat | Notes |
|------|-----|--------|
| `app/services/fuel_nationwide_extraction.py` | K | |
| `app/services/fuel_digital_pdf_nationwide_table.py` | K | Layout-specific table extraction |
| `app/services/fuel_nationwide_card_total.py` | K | CARD_TOTAL review fields |
| `app/services/fuel_nationwide_import.py` | K/M | |
| `app/services/fuel_nationwide_stage.py` | K/M | Parallel to BVD stage |
| `app/services/fuel_nationwide_review.py` | K/M | Includes `list_nationwide_completed_history` |
| `app/services/fuel_nationwide_effective.py` | K | |
| `app/services/fuel_nationwide_correction_validate.py` | K | |
| `app/services/fuel_nationwide_source_reconciliation.py` | K | |
| `app/services/fuel_nationwide_canonical_projection.py` | K/M | Mapper plugin |
| `app/services/fuel_nationwide_completed_basic.py` | K/M | |
| `app/models/fuel.py` — `FuelNationwide`, stage tables | K | |
| `alembic_tenant/versions/e6f7a8b9c0d1_fuel_nationwide_implementation_1.py` | K | Schema |

### 5.5 Backend — canonical pipeline (post-wall)

| File | Cat | Notes |
|------|-----|--------|
| `app/services/fuel_canonical.py` | S | Batch status constants |
| `app/models/fuel.py` — `FuelSourceBatch`, `FuelTransaction`, `FuelSourceControl` | S | |
| `app/services/fuel_reconciliation.py` | S | Segment 9 |
| `app/services/fuel_review.py` | S | Segment 8 batch review |
| `app/services/fuel_source_duplicate_gate.py` | S | |
| `app/services/fuel_money.py` | S | |
| `app/services/fuel_transaction_classify.py` | S | |
| `app/services/fuel_classification_workflow.py` | S | |
| `app/services/fuel_classification_persistence.py` | S | |
| `app/services/fuel_charge_categories.py` | S | |
| `app/services/fuel_financial_responsibility.py` | S | |
| `app/services/fuel_financial_responsibility_refresh.py` | S | |
| `app/services/fuel_oo_pricing.py` | S | |
| `app/services/fuel_historical_resolution.py` | S | |
| `app/services/fuel_dashboard_stats.py` | M | `count_processed_last_7_days` S; `count_needs_review` BVD-only |
| `app/services/fuel_reason_normalize.py` | S | |
| `app/schemas/fuel.py` | M | Split provider row DTOs OK; shared processed/history DTOs should not be `FuelBvd*` |
| `app/deps/fuel_rbac.py` | S | |

### 5.6 Frontend — Fuel home and shared shells

| File | Cat | Notes |
|------|-----|--------|
| `apps/web/src/pages/FuelMainPage.tsx` | M | Dual providers wired explicitly; target single refresh/history/upload dispatch |
| `apps/web/src/pages/fuel/fuelDashboardData.ts` | M | `mergeFuelCompletedHistory` — delete when one API |
| `apps/web/src/pages/fuel/FuelRecentActivitySection.tsx` | M | Shared table; provider-aware expand (renderer registry) |
| `apps/web/src/pages/fuel/ProcessedStatementWorkspace.tsx` | M | BVD-only; hardcoded “BVD” title |
| `apps/web/src/pages/fuel/fuelRecentActivityRows.ts` | M | BVD row parsing for dashboard |
| `apps/web/src/pages/fuel/fuelActivityInvoiceDisplay.ts` | S/M | Display helpers; keep if DTO is provider-neutral |
| `apps/web/src/pages/fuel/FuelProviderCombobox.tsx` | S | |
| `apps/web/src/pages/fuel/FuelConfigureApiModal.tsx` | S | |
| `apps/web/src/pages/fuel/FuelFullScreenOverlay.tsx` | S | |
| `apps/web/src/pages/fuel/RecentActivityStatementTxnPanel.tsx` | M | Verify consumers |
| `apps/web/src/pages/fuel/fuelLastProvider.ts` | S | Upload UX only |
| `apps/web/src/api.ts` — `listFuelBvdCompletedHistory`, `listFuelNationwideCompletedHistory`, parallel import APIs | M | Single processed-fuel client |
| `apps/web/src/pages/FuelReviewQueuePage.tsx` | M | `listFuelBvdImports` only today |
| `apps/web/src/pages/FuelBvdHistoryPage.tsx` | M | BVD-named full history page |
| `apps/web/src/pages/FuelBvdUploadPage.tsx`, `FuelBvdExtractionReviewPage.tsx`, `FuelBvdFullDetailPage.tsx` | M/K | Legacy routes; long-term fold into Fuel home + shared import workspace |

### 5.7 Frontend — BVD review / processed (provider-native UI)

| File | Cat | Notes |
|------|-----|--------|
| `apps/web/src/pages/fuelBvdReview/FuelBvdProcessingWorkspace.tsx` | K/M | Staging workspace — keep BVD fields; shell may share with Nationwide |
| `apps/web/src/pages/fuelBvdReview/FuelBvdProcessedRecordView.tsx` | M | Becomes BVD renderer + shared processed shell |
| `apps/web/src/pages/fuelBvdReview/BvdParsedStatementView.tsx` (if present) / tables / PDF viewer | K | Native columns & PDF |
| `apps/web/src/pages/fuelBvdReview/BvdTransactionRowsTable.tsx`, `BvdExpressRowsTable.tsx` | K | |
| `apps/web/src/pages/fuelBvdReview/fuelProcessedStatementSearch.ts` | M | Search over BVD row types — generalize to “source rows + canonical join” |
| `apps/web/src/pages/fuelBvdReview/FuelBvdCanonicalClassificationPanel.tsx` | S/M | Post-wall; should key off batch/import not BVD-only routes |
| Remaining `fuelBvdReview/*` (forms, PDF, validation, CSS) | K | Provider-native review |

### 5.8 Frontend — Nationwide review / processed

| File | Cat | Notes |
|------|-----|--------|
| `apps/web/src/pages/fuelNationwideReview/FuelNationwideProcessingWorkspace.tsx` | K/M | |
| `apps/web/src/pages/fuelNationwideReview/FuelNationwideProcessedRecordView.tsx` | M | Merge into shared processed shell |
| `apps/web/src/pages/fuelNationwideReview/NationwideParsedStatementView.tsx` | K | Native column renderer |
| `apps/web/src/pages/fuelNationwideReview/nationwideCellFormat.ts`, `nationwideReconciliationStrip.ts` | K | |

### 5.9 Tests (encode boundaries — update with refactor)

| File | Cat | Notes |
|------|-----|--------|
| `tests/test_fuel_nationwide_*.py` | K/M | Provider acceptance; add TEST_PROVIDER gate test in **M** |
| `tests/test_fuel_bvd_*.py` | K/M | |
| `tests/test_fuel_segment_7.py` | S | Profile / no `nationwide_parser.py` |
| `tests/test_fuel_segment_8.py` | S | `test_bvd_and_nationwide_same_review_path` — canonical segment |
| `tests/test_fuel_segment_9.py` + reconciliation tests | S | Post-wall |
| `apps/web/src/pages/FuelMainPage.test.tsx` | M | Mocks dual history |

---

## 6. Proposed shared interfaces (names for approval only — not implemented)

These are **target seams**, not new code in this phase:

```text
# Backend (conceptual)
class FuelProviderProcessProfile(Protocol):
    provider_code: str
    async def load_accepted_source_rows(...) -> Sequence[Mapping]
    def run_source_reconciliation(rows) -> ReconciliationResult
    async def persist_provider_native(...)
    def project_to_canonical(rows, batch) -> CanonicalProjection

async def process_fuel_import(db, tenant_id, import_id, provider_code, ...) -> ProcessSummary

async def list_processed_fuel(db, tenant_id, ...) -> list[ProcessedFuelSummary]
async def get_processed_fuel_detail(db, tenant_id, import_id) -> ProcessedFuelDetail  # includes provider_code
```

```text
# Frontend (conceptual)
ProcessedFuelStatementShell({ importId, providerCode, onOpenPdf })
  → providerRenderers[providerCode].ParsedStatementView
```

---

## 7. Suggested refactor phases (approval-gated)

1. **Document & gate** — This file + `TEST_PROVIDER` fixture spec (no production provider).  
2. **Read path** — `list_processed_fuel` backed by `fuel_source_batches` + join to provider summary projector; frontend switches Recent Activity to one API (keep provider expand renderers). Fix expand branch order as part of shared viewer.  
3. **Write path** — Extract shared `process_fuel_import` calling existing BVD/Nationwide stage functions internally (no behavior change).  
4. **Route aliasing** — Add neutral `/fuel/imports/...` routes; deprecate duplicate list/history endpoints.  
5. **WEX** — Only provider K files + profile JSON + mapper + reconciliation module.

**Explicit non-goals until phases 2–3 are stable:** Renaming `fuel_bvd` tables, merging staging schemas, or rewriting extraction.

---

## 8. Approval checklist

Before any refactor PR:

- [ ] Funnel and provider wall wording accepted as locked  
- [ ] Every file touched in fuel-card work classified K / M / S above (amend map if we missed a path)  
- [ ] `TEST_PROVIDER` gate agreed as CI/architecture test  
- [ ] Order of phases 2 vs 3 agreed (read-first recommended so Nationwide UX stops using BVD default)  
- [ ] Route naming (`/fuel/processed` vs `/fuel/imports`) agreed  

---

## 9. References

- `docs/FUEL_CARD_MODULE_DESIGN.md` — §1.3 provider-native before canonical  
- `docs/FUEL_CARD_IMPLEMENTATION_PLAN.md` — Nationwide consumes same `fuel_provider_profile.py`  
- `docs/FUEL_BVD_IMPLEMENTATION_1.md` — Process → canonical batch finalize  
- Manifest lock: one Fuel parser + profiles (`tests/test_fuel_segment_7.py` asserts no `nationwide_parser.py`)
