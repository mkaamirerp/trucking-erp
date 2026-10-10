# Fuel provider wall — architecture delta and file map

**Status:** Boundary lock **approved** (`cc153c8c`, `e493d95a`). **Phase 2** canonical processed read path is **implemented** on `feat/fuel-card` (local and `origin/feat/fuel-card` synchronized; commits through `b8b1bcd9`+).  
**Phase 2 verification:** Fuel suite `RUN_FUEL_TENANT_MIGRATE=1 ./scripts/run_fuel_pytest.sh tests/test_fuel*.py` — **392 passed, 0 skipped, 0 failed**. Authenticated **browser** acceptance on demo remains **pending** (automated browser reached `/login` without an authenticated session).  
**Next:** Further refactors gated per §7 (Phase 3+ not started).  
**Branch context:** `feat/fuel-card` with live BVD + Nationwide staging → Process → canonical batches.  
**Authoritative design:** `docs/fuel/FUEL_CARD_MODULE_DESIGN.md` (provider-native evidence before canonical meaning; one **Fuel** parse/validate orchestrator + approved provider profiles — not independent per-provider parser **workflows**).  
**Authoritative post-Process Fuel UI (visual):** [`docs/fuel/FUEL_UI_CONTRACT_WIREFRAME.html`](./FUEL_UI_CONTRACT_WIREFRAME.html) — wireframe contract for Fuel home / expanded processed row / Open source overlay (Checkpoint 0).

---

## 1. Locked funnel (do not drift)

```
SOURCE
  PDF / CSV / API / SFTP
       ↓
IDENTIFY PROVIDER / APPROVED PROFILE
       ↓
ONE FUEL PARSE / VALIDATE ORCHESTRATOR
       ↓
provider-specific profile / extraction helpers / rules
       ↓
provider-native staging / evidence
       ↓
review / corrections
       ↓
provider source reconciliation gates
       ↓
PROCESS  ──►  ════════════ PROVIDER WALL ════════════
       ↓
canonical fuel_source_batches
canonical fuel_source_controls
canonical fuel_transactions
       ↓
ONE TRUCKERP FUEL PIPELINE
       ↓
canonical mapping / classification
truck / driver / owner resolution
financial responsibility
O/O pricing
settlement candidate
history / search / dashboard / reporting
payroll / accounting consumption
```

**Reconciliation with design docs (no drift):**

- **SOURCE / SFTP:** Intake paths come from the provider catalog and connection methods (e.g. `PDF_UPLOAD`, `REST_API`, `SFTP`, structured file). SFTP is a **source acquisition** path into the same orchestrator — not a second post-wall workflow.
- **APPROVED PROFILE:** Provider code must resolve to an approved `fuel_provider_profile` / catalog entry before parse or Process; unknown or unapproved layouts stop at the gate (see §6 `process_fuel_import` — approved profile resolution).
- **Extraction helpers:** Provider-specific **extraction/helper modules** are allowed; independent per-provider **parser workflows/orchestrators** are forbidden (§2).
- **Payroll / accounting consumption:** Downstream TruckERP modules **consume** finalized canonical Fuel data (classification, responsibility, settlement candidates). Fuel Process does **not** run payroll, settlement generation, or payment posting inside Process (`docs/fuel/FUEL_CARD_MODULE_DESIGN.md`).

**Process is the controlled bridge across the provider wall:** it begins with reviewed provider-native evidence and ends with canonical Fuel records (`fuel_source_batches`, `fuel_source_controls`, `fuel_transactions` with FINALIZED batch semantics).

### 1.1 Route and identity lock

| Side of wall | Canonical API shape (target) | Primary identity |
|--------------|------------------------------|------------------|
| **Pre-wall** (staging, review, source document, Process) | `/fuel/providers/{provider_code}/imports/{import_id}` | `import_id` (stage id = import id today) |
| **Post-wall** (processed Fuel application) | `/fuel/processed/{batch_id}` | **`batch_id`** (`fuel_source_batches.id`) |

Normal post-Process application identity is **canonical `batch_id`**. `import_id` / `source_import_ref` remain traceability links to provider-native evidence, not the primary key for post-wall navigation.

Legacy `/fuel/bvd/...` and `/fuel/nationwide/...` routes are **migration aliases** toward the pre-wall shape above; they must not define a second post-wall identity model.

### 1.2 Canonical-first post-wall surfaces

**Processed history, list, dashboard counts, and normal Fuel search are canonical-first:**

- Authoritative reads: `fuel_source_batches` + `fuel_transactions` + `fuel_source_controls` (FINALIZED / operational statuses as today).
- Provider-native summary projectors (e.g. `fuel_bvd_completed_basic`, `fuel_nationwide_completed_basic`) and native row tables are **optional source-evidence enrichment** for display drill-down — **never required** for a provider to appear in normal Fuel history, Recent Activity, or dashboard processed metrics.

A new provider must be visible in shared processed history as soon as Process creates a finalized canonical batch; native “BASIC” projection can be added for richer columns but is not a gate.

### 1.3 Search boundaries

| Search context | Data source |
|----------------|-------------|
| **Normal Fuel processed search** (home, history, operational lookup) | Canonical batches / transactions (and shared joins), not provider-native tables |
| **Provider-native / source-evidence search** | Only inside native statement or evidence views (e.g. full BVD/Nationwide parsed statement UI, PDF-adjacent filters) |

Do not add per-provider “global Fuel search” implementations. Post-wall search stays one pipeline; native search stays scoped to the evidence viewer.

### 1.4 What “preserve Process” means

- **Now:** Preserve proven **behavior** of BVD and Nationwide Process. Do not break demo acceptance paths while refactoring.
- **End state:** Process is **one shared orchestration** (`process_fuel_import`), not one lifecycle per provider. BVD / Nationwide / WEX code supplies **differences** (extractors, row shapes, reconciliation rules, column renderers), not separate **application workflows** after the wall.

### 1.5 Post-wall history and “open statement”

**Wrong end state**

- `list_bvd_history()` + `list_nationwide_history()` + `merge_everything()`
- Separate processed overlay components per provider for **canonical** search, filters, and navigation
- `if (provider === 'BVD')` / `elif (provider === 'NATIONWIDE')` chains in processed history, dashboard, or post-wall search

**Right end state**

- `list_processed_fuel()` / `GET /fuel/processed` reading **canonical finalized batches**; detail at `GET /fuel/processed/{batch_id}`
- One Fuel processed viewer shell keyed by `batch_id`; **provider-specific column renderers** only when rendering full native source rows (enrichment), keyed by `provider_code` via **registry dispatch**
- Open full source statement: pre-wall route or enrichment endpoint under `/fuel/providers/{provider_code}/imports/{import_id}`

Provider differences in **presentation of source evidence** are legitimate. Duplicate **workflows** (history API, dashboard merge, Open routing, Process entrypoints) are not.

### 1.6 Stable canonical TruckERP Fuel contract

After Process, TruckERP consumes **one provider-neutral canonical Fuel contract** (`fuel_source_batches`, `fuel_source_controls`, `fuel_transactions` and shared DTOs/APIs). Provider differences **do not** redefine TruckERP field names or semantics.

**Rules:**

- Canonical field names and semantics are the **same** for BVD, Nationwide, WEX, and future providers.
- When a provider does not supply a value for a canonical field, that field may remain **NULL** (or unset) — no provider-specific “shadow columns” on the canonical model.
- Provider-only facts stay in **provider-native evidence**, `provider_raw`, and native tables — not as alternate canonical meanings.
- Adding a new global TruckERP business concept requires an **intentional canonical model change** (migration + design), not a provider-specific schema exception.

**Representative canonical concepts** (illustrative; not every provider populates every field):

- Provider / source lineage (`provider_code`, `source_import_ref`, `source_row_order`, `batch_id`)
- `transaction_date`, `transaction_datetime_source`, timezone fields
- `unit_number_snapshot`, `card_or_account_id`
- Driver / truck / payee references (`driver_id`, `truck_id`, `owner_operator_payee_id` when resolved)
- `city`, `province_state`, `country`, `merchant_site`
- `product` / `product_code_raw` / category-related canonical fields
- `quantity`, `quantity_unit`, `unit_price`, `unit_price_basis`
- `currency`, discount fields, tax fields (`hst_amount`, `gst_amount`, etc.)
- `total_amount`, `principal_amount`, `provider_fee_amount`
- `financial_responsibility`, `owner_operator_charge_amount`, settlement / deduction candidacy flags
- `provider_raw` and source linkage for audit drill-down

Mappers **project** provider evidence into this contract; they do not fork the contract per vendor.

### 1.7 Main Fuel page / provider selector lock

- **Main Fuel page / Recent Activity** shows **all** processed Fuel by default, **regardless of provider** (canonical list; optional display filter only — not separate per-provider history apps).
- The **provider selector** primarily controls **pre-wall ingestion** (upload handoff, staging workspace, native review entry). It must **not** turn post-wall payroll, history, search, or Open into a provider-specific application.
- **Provider name** may appear as **lineage / badge** (column, header, audit) — not as a separate product workflow.
- Normal post-wall behavior stays **shared**: one processed list, one shell, registry-backed evidence renderers.

### 1.8 Payroll / accounting lock

Payroll, accounting, driver-pay, and owner-operator downstream logic **consume canonical Fuel records** only.

They must **not** require provider-specific business branches such as:

- `if provider == BVD` …
- `if provider == Nationwide` …
- `if provider == WEX` …

**Normal questions** are canonical:

- Transactions for **driver**, **truck/unit**, **payee**
- **Category**, **financial responsibility**, **settlement candidate**
- **Amount**, **currency**, **date**

**Provider identity** is lineage and audit evidence — not the business data contract. (Fuel Process still does not execute payroll or accounting posting; see funnel and `docs/fuel/FUEL_CARD_MODULE_DESIGN.md`.)

### 1.9 Canonical view vs source evidence (UI boundary)

| Surface | Rule |
|---------|------|
| **Normal processed view** | Canonical TruckERP fields and labels; same operational shape for every provider |
| **Source evidence drill-down** | Provider-native labels/columns, native controls, original PDF/CSV/API/file — **provider-specific renderer allowed here only** |

**Conceptual drill-down chain:**

```text
canonical fuel_transaction
  → source lineage (batch_id, source_import_ref, source_row_order)
  → accepted provider-native row
  → original source evidence (file / API artifact)
```

Provider-native rendering must **not** become a separate payroll, history, or global search workflow — only enrichment inside the shared shell.

### 1.10 Canonical-first vs operational UI (presentation lock)

**Canonical-first is a data/read-model rule, not a mandate to create a second canonical presentation layer.** The refined **TruckERP Processed Fuel workspace** (`ProcessedStatementWorkspace` / `TruckErpProcessedFuelWorkspace`) is the **single** operational processed-Fuel UI for all providers. Canonical `fuel_transactions` populate that workspace; provider code does **not** fork the main operational layout.

- Main operational Fuel UI must **not** fork by provider (no parallel “canonical summary table” above the workspace).
- Provider-native column sets (Nationwide Network/Ex-GST/controls; BVD Auth/Site/Express; etc.) are **source-evidence only** — drill-down, PDF, native detail panels.
- Missing canonical or provider-mapped operational fields remain **NULL / blank / —** in the shared workspace; they must **not** trigger a provider-specific operational UI.

### 1.11 Post-Process Fuel UI wireframe (visual contract — Checkpoint 0)

The HTML wireframe **[`docs/fuel/FUEL_UI_CONTRACT_WIREFRAME.html`](./FUEL_UI_CONTRACT_WIREFRAME.html)** is the **authoritative visual contract** for post-Process Fuel on the main Fuel page. It locks:

1. Main Fuel **expanded row** = **one** TruckERP operational workspace (no parallel parser block).
2. Operational workspace = **canonical / final TruckERP fields only** (processed batch read model).
3. **Same operational layout** for every provider.
4. **No** provider-native / parser values **inline** on the main Fuel expand row.
5. **Open source** → separate provider-native evidence overlay/view.
6. **Close** returns to the main Fuel operational workspace.
7. **BVD** = visual/design baseline only; **BVD source types/components are not** the shared TruckERP data contract.
8. **Never** map Nationwide / WEX / others into `FuelBvdRow` (or BVD UI components) to fake a shared workspace.

Implementation refactors must conform to this wireframe plus §1.9–§1.10; the wireframe wins on **layout and what may appear on the main page vs Open source**.

### 1.12 Operational transaction contract (Checkpoint 1)

**`FuelProcessedOperationalTransactionOut`** / **`operational_transactions`** on **`GET /fuel/processed/{batch_id}`** is the single provider-neutral row shape for the TruckERP processed-Fuel workspace (Checkpoint 2 UI). Mapped only from **`fuel_transactions`** via **`fuel_transaction_to_operational_out`** — no provider-native staging reads.

---

## 2. Architecture delta (today → target)

| Layer | Today | Target |
|--------|--------|--------|
| Source intake | PDF/CSV/API today; SFTP/API in catalog where evidenced | **PDF / CSV / API / SFTP** → same **ONE FUEL PARSE / VALIDATE ORCHESTRATOR**; acquisition adapters only |
| Identify | Provider code + profile at upload/handoff | **IDENTIFY PROVIDER / APPROVED PROFILE** before hydrate or Process |
| Parse / extract | Shared `fuel_digital_pdf_extract.py` + profiles; provider modules `fuel_bvd_extraction.py`, `fuel_nationwide_extraction.py`, `fuel_digital_pdf_nationwide_table.py` | One orchestrator entry; **provider-specific extraction/helper modules allowed**; no second orchestrator per provider |
| Parser policy | Tests reject standalone `nationwide_parser.py` style forks | **Independent provider parser workflows/orchestrators forbidden**; helpers + profile hooks required |
| Staging | Parallel table families (`fuel_bvd_import_stage` / `fuel_nationwide_import_stage`) | Keep **per-provider staging tables**; shared stage **lifecycle** API |
| Pre-wall routes | `/fuel/bvd/...`, `/fuel/nationwide/...` | `/fuel/providers/{provider_code}/imports/{import_id}` (+ aliases during migration) |
| Source reconciliation | Per-provider modules | **Provider source reconciliation gates**; per-provider rules invoked from shared Process prelude |
| Process | `process_bvd_import_review` / `process_nationwide_import_review` → parallel `*_stage_to_permanent` | `process_fuel_import(...)` with provider **registry** |
| Canonical projection | `project_bvd_rows_to_canonical` vs `project_nationwide_rows_to_canonical` | Shared finalize + **provider mapper** plugin |
| Segment 8 canonical review | `fuel_review.py` on batches | Unchanged; staging Process lands on same batch semantics |
| Segment 9 reconciliation | `fuel_reconciliation.py` | **SHARED ALREADY** — post-wall only |
| History / activity | Dual history endpoints + `mergeFuelCompletedHistory` | Canonical `GET /fuel/processed`; optional native enrichment by `provider_code` |
| Dashboard | `processed_last_7_days` canonical (good); `needs_review` **BVD-only** | Processed metrics canonical; **one shared `needs_review` service** via provider registry adapters (no BVD+Nationwide+WEX hardcoding) |
| Search | BVD-shaped processed statement search in `fuelProcessedStatementSearch.ts` | Canonical search post-wall; native search only in evidence views |
| Frontend home | Dual history/upload/overlay wiring | Provider-agnostic processed DTO; registry for upload + native viewer |

---

## 3. Architectural acceptance gate: `TEST_PROVIDER`

Add a **fictitious** provider `TEST_PROVIDER` with **one** transaction fixture and minimal profile JSON.

**Pass:** Extract → stage → review → process → finalized canonical batch → appears in **shared** processed history/list/dashboard **without** any provider-named history API or frontend merge — optional TEST native renderer for evidence view only.

**Fail (architecture rejected):** Adding `TEST_PROVIDER` requires any of:

- A new provider **`if` / `elif` branch** (or equivalent hardcoded dispatch) in processed history, dashboard, search, classification, financial responsibility, settlement, or other **post-wall** workflow
- A **payroll** provider branch, **driver-pay** provider branch, or **O/O settlement** provider branch keyed on provider code (same rule as above: canonical queries only)
- A dedicated `list_test_provider_history()` (or per-provider list) instead of canonical `list_processed_fuel`
- A new dashboard merge function or provider-specific processed search entrypoint
- A separate Process **application** workflow component (provider Process **hooks** inside shared orchestration are OK)

**Registry / plugin dispatch is required** for: pre-wall review counts, native statement renderers, Process profile hooks, and optional enrichment — not central `switch (provider)` growth.

Existing BVD + Nationwide duplication is **documented debt** to remove, not a pattern to extend for WEX.

---

## 4. Known symptom (historical; Phase 2 read-path target)

Pre–Phase-2 Recent Activity expand on Fuel home (`FuelRecentActivitySection.tsx`) exhibited **BVD-default plumbing**:

1. **Branch order:** `ProcessedStatementWorkspace` when `chargeCount > 0` before Nationwide native rows → empty BVD workspace / “0 charges”.
2. **Hardcoded label:** `BVD {invoiceNumber}` on a non-BVD provider.

**Phase 2 direction:** canonical-first activity + `ProcessedFuelStatementShell` + registry evidence panels (§1.7, §1.9). Authenticated browser confirmation on demo remains pending (see **Status**).

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
| `app/routers/fuel.py` — `get_fuel_dashboard_stats` | M | Handler OK; `needs_review` must use registry, not BVD-only service |
| `app/routers/fuel.py` — Segment 8 queue / batch review / reconciliation | S | Canonical batch queue |
| `app/routers/fuel.py` — BVD import/upload/process/history routes | M | Target pre-wall: `/fuel/providers/BVD/imports/...` |
| `app/routers/fuel.py` — Nationwide mirror routes | M | Same pre-wall target |
| `app/routers/fuel.py` — post-wall processed + classification | M | Key by `batch_id`; one surface; registry for provider context |

### 5.2 Backend — ingestion, profiles, shared parse

| File | Cat | Notes |
|------|-----|--------|
| `app/services/fuel_provider_catalog.py` | S | |
| `app/services/fuel_provider_connections.py` | S | |
| `app/services/fuel_provider_adapter.py` | S | Future API/CSV fetch boundary |
| `app/services/fuel_provider_profile.py` | S | Profile loader; **forbids independent parser workflows**, not helper modules |
| `app/contracts/fuel_provider_profiles.json` | K | Per-provider rules |
| `app/services/fuel_ai_handoff.py` | S | Routes to profile + contract |
| `app/services/fuel_ai_contract.py` | S | |
| `app/services/fuel_digital_pdf_extract.py` | S/M | Shared orchestrator; extend via profile + helpers |
| `app/services/fuel_digital_pdf_table_geometry.py` | S | |
| `app/services/fuel_digital_pdf_express.py` | K | BVD express helpers (profile-invoked) |
| `app/services/fuel_digital_pdf_types.py` | S | |
| `app/services/fuel_ingestion.py` | S | Canonical row role routing |
| `app/services/fuel_controls.py` | S/M | Shared control typing |

### 5.3 Backend — BVD provider-native

| File | Cat | Notes |
|------|-----|--------|
| `app/services/fuel_bvd_extraction.py` | K | Extraction helper |
| `app/services/fuel_bvd_import.py` | K/M | Native persistence; drop dedicated completed history in favor of canonical list |
| `app/services/fuel_bvd_stage.py` | K/M | Stage + `process_stage_to_permanent` → delegate into shared `process_fuel_import` |
| `app/services/fuel_bvd_review.py` | K/M | Thin pre-wall facade |
| `app/services/fuel_bvd_effective.py` | K | |
| `app/services/fuel_bvd_correction_validate.py` | K | |
| `app/services/fuel_bvd_source_reconciliation.py` | K | Provider reconciliation gate |
| `app/services/fuel_bvd_column_map.py` | K | |
| `app/services/fuel_bvd_document_identity.py` | K | |
| `app/services/fuel_bvd_canonical_projection.py` | K/M | Mapper plugin; shared `finalize_batch` |
| `app/services/fuel_bvd_completed_basic.py` | K | Optional enrichment projector — not history gate |
| `app/models/fuel.py` — `FuelBvd`, stage tables | K | |

### 5.4 Backend — Nationwide provider-native

| File | Cat | Notes |
|------|-----|--------|
| `app/services/fuel_nationwide_extraction.py` | K | |
| `app/services/fuel_digital_pdf_nationwide_table.py` | K | |
| `app/services/fuel_nationwide_card_total.py` | K | |
| `app/services/fuel_nationwide_import.py` | K/M | |
| `app/services/fuel_nationwide_stage.py` | K/M | |
| `app/services/fuel_nationwide_review.py` | K/M | |
| `app/services/fuel_nationwide_effective.py` | K | |
| `app/services/fuel_nationwide_correction_validate.py` | K | |
| `app/services/fuel_nationwide_source_reconciliation.py` | K | |
| `app/services/fuel_nationwide_canonical_projection.py` | K/M | Mapper plugin |
| `app/services/fuel_nationwide_completed_basic.py` | K | Optional enrichment |
| `app/models/fuel.py` — `FuelNationwide`, stage tables | K | |

### 5.5 Backend — canonical pipeline (post-wall)

| File | Cat | Notes |
|------|-----|--------|
| `app/services/fuel_canonical.py` | S | |
| `app/models/fuel.py` — `FuelSourceBatch`, `FuelTransaction`, `FuelSourceControl` | S | |
| `app/services/fuel_reconciliation.py` | S | Segment 9 |
| `app/services/fuel_review.py` | S | Segment 8 |
| `app/services/fuel_source_duplicate_gate.py` | S | Exact-source duplicate/advisory patterns |
| `app/services/fuel_money.py` | S | |
| `app/services/fuel_transaction_classify.py` | S | |
| `app/services/fuel_classification_workflow.py` | S | |
| `app/services/fuel_classification_persistence.py` | S | Post-Process backfill (existing behavior) |
| `app/services/fuel_charge_categories.py` | S | |
| `app/services/fuel_financial_responsibility.py` | S | |
| `app/services/fuel_financial_responsibility_refresh.py` | S | |
| `app/services/fuel_oo_pricing.py` | S | |
| `app/services/fuel_historical_resolution.py` | S | |
| `app/services/fuel_dashboard_stats.py` | M | `count_processed_last_7_days` → S; `count_needs_review` → registry-based |
| `app/services/fuel_reason_normalize.py` | S | |
| `app/schemas/fuel.py` | M | Shared processed DTOs keyed by `batch_id` |
| `app/deps/fuel_rbac.py` | S | |

### 5.6 Frontend — Fuel home and shared shells

| File | Cat | Notes |
|------|-----|--------|
| `apps/web/src/pages/FuelMainPage.tsx` | M | Registry dispatch; canonical processed fetch |
| `apps/web/src/pages/fuel/fuelDashboardData.ts` | M | Remove `mergeFuelCompletedHistory` when canonical API exists |
| `apps/web/src/pages/fuel/FuelRecentActivitySection.tsx` | M | Canonical rows + registry evidence expand |
| `apps/web/src/pages/fuel/ProcessedStatementWorkspace.tsx` | M | BVD evidence viewer; not default for all providers |
| `apps/web/src/pages/fuel/fuelRecentActivityRows.ts` | M | |
| `apps/web/src/pages/fuel/fuelActivityInvoiceDisplay.ts` | S/M | |
| `apps/web/src/pages/fuel/FuelProviderCombobox.tsx` | S | |
| `apps/web/src/pages/fuel/FuelConfigureApiModal.tsx` | S | |
| `apps/web/src/pages/fuel/FuelFullScreenOverlay.tsx` | S | |
| `apps/web/src/pages/fuel/RecentActivityStatementTxnPanel.tsx` | M | |
| `apps/web/src/pages/fuel/fuelLastProvider.ts` | S | Upload UX only |
| `apps/web/src/api.ts` — dual history / parallel import clients | M | `GET /fuel/processed`, pre-wall provider import paths |
| `apps/web/src/pages/FuelReviewQueuePage.tsx` | M | Registry-backed queue |
| `apps/web/src/pages/FuelBvdHistoryPage.tsx` | M | Fold into canonical processed history |
| Legacy BVD upload/detail pages | M/K | Pre-wall aliases |

### 5.7 Frontend — BVD review / processed (provider-native UI)

| File | Cat | Notes |
|------|-----|--------|
| `apps/web/src/pages/fuelBvdReview/FuelBvdProcessingWorkspace.tsx` | K/M | Pre-wall staging |
| `apps/web/src/pages/fuelBvdReview/FuelBvdProcessedRecordView.tsx` | M | Shared processed shell + BVD enrichment |
| BVD parsed tables / PDF / review forms | K | Native evidence |
| `apps/web/src/pages/fuelBvdReview/fuelProcessedStatementSearch.ts` | K/M | **Native evidence search only** — not global Fuel search |
| `apps/web/src/pages/fuelBvdReview/FuelBvdCanonicalClassificationPanel.tsx` | S/M | Post-wall; `batch_id` |

### 5.8 Frontend — Nationwide review / processed

| File | Cat | Notes |
|------|-----|--------|
| `apps/web/src/pages/fuelNationwideReview/*` | K/M | Same split: pre-wall workspace + native renderer |

### 5.9 Tests (encode boundaries — update with refactor)

| File | Cat | Notes |
|------|-----|--------|
| `tests/test_fuel_nationwide_*.py`, `tests/test_fuel_bvd_*.py` | K/M | Provider acceptance |
| `tests/test_fuel_segment_7.py` | S | No standalone `nationwide_parser.py` workflow file |
| TEST_PROVIDER gate (future) | M | Assert no new post-wall if/elif surfaces |
| `apps/web/src/pages/FuelMainPage.test.tsx` | M | |

---

## 6. Conceptual `process_fuel_import` contract (preserve proven behavior)

Shared orchestration must **not** invent a new ordering that contradicts current BVD/Nationwide `*_stage_to_permanent` implementations. Conceptual steps (single entry; provider hooks for labeled steps):

1. **Approved profile resolution** — Provider code maps to an approved `fuel_provider_profile` / catalog entry (same rules as ingest; reject unknown or unapproved layouts).
2. **Idempotency** — If import already source-reviewed / process-complete, return existing summary and run idempotent stage cleanup where implemented (BVD path).
3. **Active stage load** — Fail clearly if no active stage when Process expected.
4. **Effective reviewed rows** — Stage rows + corrections → effective accepted row set (provider effective builder).
5. **Provider source reconciliation** — Provider rules; hard-fail Process if not passed (HTTP 400 with reconciliation payload).
6. **Source artifact read** — Load exact staged source bytes (e.g. PDF) for duplicate check and permanent storage.
7. **Exact-source duplicate / advisory gate** — Document identity + advisory lock + permanent-only duplicate check (exclude current `import_id`); fail with existing duplicate codes.
8. **Permanent source storage** — Write immutables to provider storage module before DB commit of financial rows.
9. **One atomic financial DB transaction** (commit once on success):
   - Persist accepted rows to provider-native permanent table (`fuel_bvd` / `fuel_nationwide` / …) with SOURCE_REVIEWED semantics.
   - Create `fuel_source_batch` linked to `import_id` / `source_import_ref`.
   - **Canonical projection** — provider mapper → `fuel_transactions` + `fuel_source_controls`.
   - **Canonical money gate** — provider-specific assert (e.g. BVD grand total / Nationwide transaction count rules).
   - **`finalize_batch`** — FINALIZED semantics, `finalized_at`, reviewed_by (shared helper).
10. **Rollback behavior** — On projection or gate failure: DB rollback; purge orphan permanent source files where implemented today.
11. **Stage retirement** — Delete stage records after successful commit (best-effort cleanup on failure logged).
12. **Existing shared post-Process behavior** — e.g. `best_effort_backfill_classifications_for_import` (classification persistence); continue to use shared classification / financial responsibility / O-O paths keyed by canonical data — **no new provider entrypoints**.

Provider-specific code implements hooks (effective rows, reconciliation, duplicate helpers, native ORM mapping, projector, money gate). The **lifecycle and transaction boundary** stay shared.

### 6.1 Proposed registry seams (names for approval only — not implemented)

```text
# Backend (conceptual)
class FuelProviderProcessProfile(Protocol):
    provider_code: str
    async def load_effective_accepted_rows(...) -> Sequence[Mapping]
    def run_source_reconciliation(rows) -> ReconciliationResult
    async def run_duplicate_gate(...) -> None  # raises on duplicate
    async def persist_provider_native(...)
    def project_to_canonical(...) -> tuple[txns, controls]
    def assert_canonical_money_gate(...)

class FuelProviderPreWallAdapter(Protocol):
    def count_needs_review(db, tenant_id) -> int

async def process_fuel_import(db, tenant_id, provider_code, import_id, ...) -> ProcessSummary

async def list_processed_fuel(db, tenant_id, ...) -> list[ProcessedFuelSummary]  # canonical
async def get_processed_fuel_batch(db, tenant_id, batch_id) -> ProcessedFuelDetail
```

```text
# Frontend (conceptual)
providerRenderers[providerCode].ParsedStatementView  // evidence only
ProcessedFuelShell({ batchId })  // canonical-first Open
```

---

## 7. Suggested refactor phases (approval-gated)

1. **Document & gate** — This file + `TEST_PROVIDER` fixture spec. **Done** (approved + hardened).  
2. **Read path** — **Done (Phase 2, `feat/fuel-card`):** `GET /fuel/processed` from `fuel_source_batches`; Fuel home Recent Activity canonical-first; registry for evidence expand.  
3. **Write path** — `process_fuel_import` delegating to existing `*_stage_to_permanent` (no behavior change). **Not started (Phase 3).**  
4. **Route migration** — Pre-wall `/fuel/providers/{provider_code}/imports/{import_id}`; post-wall `/fuel/processed/{batch_id}`; legacy aliases deprecated.  
5. **Dashboard** — Shared `needs_review` via provider registry adapters.  
6. **WEX** — Allow whatever provider-specific **source** adapter, native schema, profile, mapper, reconciliation, and native renderer real WEX evidence requires — **no new post-wall application workflow** (history, dashboard, search, classification, responsibility, settlement entrypoints stay shared).

**Explicit non-goals until phases 2–3 are stable:** Renaming `fuel_bvd` tables, merging staging schemas, or rewriting extraction.

---

## 8. Approval checklist

Before any refactor PR:

- [ ] Funnel, provider wall, and Process bridge wording accepted as locked  
- [ ] Pre-wall vs post-wall routes and `batch_id` identity accepted  
- [ ] Canonical-first history/dashboard/search vs native evidence search accepted  
- [ ] Stable canonical contract (§1.6), Fuel home selector lock (§1.7), payroll/accounting lock (§1.8), UI evidence boundary (§1.9), operational UI lock (§1.10), visual wireframe (§1.11 / `FUEL_UI_CONTRACT_WIREFRAME.html`) accepted  
- [ ] `process_fuel_import` contract matches proven BVD/Nationwide ordering  
- [ ] Extraction helper vs forbidden workflow distinction accepted  
- [ ] `TEST_PROVIDER` gate + registry dispatch requirement accepted  
- [ ] File map K / M / S reviewed  
- [ ] Phase order agreed (read-first recommended)

**Documentation cross-reference (done):**

- [x] **Provider Wall Architecture Lock** in `docs/fuel/FUEL_CARD_MODULE_DESIGN.md`  
- [ ] Optional: same xref in `docs/fuel/FUEL_CARD_IMPLEMENTATION_PLAN.md` if not already present  

---

## 9. References

- `docs/fuel/FUEL_CARD_MODULE_DESIGN.md` — §1.3 provider-native before canonical (to receive Provider Wall lock xref after approval)  
- `docs/fuel/FUEL_CARD_IMPLEMENTATION_PLAN.md` — profile reuse (to receive Provider Wall lock xref after approval)  
- `docs/fuel/FUEL_BVD_IMPLEMENTATION_1.md` — Process → canonical batch finalize  
- `tests/test_fuel_segment_7.py` — rejects standalone `nationwide_parser.py` workflow module; provider **helper** modules remain valid
