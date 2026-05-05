# Load Page / Intake / Load Lab — Implementation Tracker

**Roadmap mode:** work is split into **three connected tracks** (A / B / C). Every slice should declare its track so we **stop drifting** across intake, parser, and dispatch concerns.

---

## 1. Purpose / why this doc exists

**Load Lab** is the **extraction and proving surface**; the **real goal** is a **safe migration into the real Load Page and intake flow**—not to ship Load Lab as the canonical production form.

This document is the **living tracker**. It records intent vs. drift, what is done, what is paused, and **non-negotiable safety rails**.

---

## 2. Three-track roadmap (do not conflate)

| Track | Scope | Examples |
|-------|--------|----------|
| **A — Load Page / Intake** | Canonical **`LoadWorkspaceForm`**, operator load UX | Manual load creation, intake draft, **Save Draft / Save Ready**, **`Load.status` target model**, **save/commit contract** |
| **B — Parser / AI / Load Lab** | Proving surface + hydration + parse API evolution | Load Lab, **frontend hydration helper**, **mapper**, **golden tests**, **stateless semantic skeleton**, future **disabled adapter** / **parse-document cutover** |
| **C — Trip / Dispatch** | Operational trip container, assignment, execution adjacency | **PR #31** legacy dispatch cutover, **trip assignment endpoint**, Load Page links to **Trip Workspace**, future **Assign & Send**, execution / custody / terminal / recovery / payroll |

**Rule of thumb:** Parser output (**B**) may **hydrate draft only** until **Track A** save/commit rules say otherwise. **Track C** owns assignment and dispatch-side effects—not the parser.

---

## 3. Architecture rule (all tracks)

- **`LoadWorkspaceForm`** is the **one real production load form**.
- **Load Lab** is **test / debug / proving**, not the production form.
- **Parser / Lab output** may **hydrate the Load Page draft only** (assistive fill). It must not become the system of record without an **explicit** user save/commit path (**Track A**).
- The **parser must not**:
  - create **trips**,
  - assign **equipment** (driver / truck / trailer),
  - write **`dispatch_trips`**,
  - or set **`Load.status` = dispatched** (or equivalent stealth dispatch).

---

## 4. Where we started

- Goal: **Load Lab / parser migration into the real Load Page** and intake—so operators get better PDF assist and consistent **`LoadDocumentParseResponse`** hydration on **`LoadWorkspaceForm`**.

---

## 5. Why we drifted

- **Load Page** and **dispatch / `Load.status`** were **mixed** in product and code mental models.
- **`Load.status` = dispatched`** could create **operational side effects** (perception of “live” dispatch) when the intent was only commercial/intake editing.
- **Trip/dispatch safety** had to be **separated** (endpoints, UI boundaries, PR #31-style guards) **before** parser **production** wiring (`/loads/parse-document` cutover, flags, semantic default).

---

## 6. Where we are now (completed slices by track)

### Track A — Load Page / Intake

| Slice | Summary |
|--------|--------|
| **Slice 16A** | Shared **PDF hydration helper** (`loadParseHydration` / parse → draft bridge; foundation for form hydration). |
| **Slice A1** | **Load Draft/Ready Foundation Alignment** — aligns manual create and **`mark-ready`** validation with draft/ready intent before explicit Save Draft / Save Ready UI. |
| **Slice A2** | **Mark Ready UI (save-then-mark)** — **`LoadWorkspacePage`** exposes **Mark ready** for **draft** loads in **detail/intake**; **PATCH** then **`POST /loads/{id}/mark-ready`**; **no** A2 backend change. |
| **Slice A3** | **Status helper copy (wording-only)** — Assignment/status hint: use **Mark ready** for validated draft → ready; legacy statuses noted for compatibility; **no** dropdown/backend **`ALLOWED_STATUSES`** changes. |

**Slice A1 (accepted) — scope and safety:**

- Manual **`/loads/new`** default **`Load.status`** changed from **`unassigned`** to **`draft`** (`LoadWorkspacePage` initial state).
- **`initialWorkspaceFieldsManual`** **`status`** set to **`draft`** (`loadWorkspaceShared.ts`; consistency / future consumers).
- **`mark_load_ready`** now treats **`DELIVERY`** as a valid delivery/drop leg (same as **`DROP`**) so the default PICKUP + DELIVERY pair qualifies.
- **`POST …/mark-ready`** still only persists **`ready`**, **`concurrency_version`**, and **`updated_at`** on the load row — no stop rewrite in that endpoint.
- **No** trip creation, **no** assignment, **no** **`dispatch_trips`** writes from A1.
- **No** parser / Load Lab production wiring in A1.
- **No** **`Load.status = dispatched`** path added; full **`ALLOWED_STATUSES`** / board rewrite **not** in scope.

**Slice A2 (accepted) — scope and safety:**

- **Mark ready** is shown only when **`load`** exists, **`workspaceMode`** is **detail** or **intake**, and **server** **`Load.status`** is (**`draft`**); not on manual create.
- Operator flow: **Mark ready** first **`PATCH`**es the **current form** (same payload as **Save load**), then **`POST /api/v1/loads/{id}/mark-ready`** with **`expected_concurrency_version`** from the **PATCH** response, then **hydrates** the final **`ready`** **`Load`** response.
- **PATCH** failure **does not** call **`mark-ready`**; errors use the same **conflict / toolbar** patterns as **Save**.
- **`mark-ready`** validation (**400**) and **version conflict** (**409**) surface in the **toolbar**; if **PATCH** succeeded but **mark-ready** failed, UI keeps **saved** state unless a **conflict snapshot** applies.
- **No** **A2** backend change (reuse existing **`mark_load_ready`**).
- **No** parser / Load Lab, **no** trip assignment, **no** **`dispatch_trips`**, **no** **`Load.status = dispatched`**, **no** Assign & Send / custody / payroll / package in A2.

**Slice A3 (accepted) — wording-only:**

- Helper text under the **Status** dropdown (**`LoadWorkspaceForm`**) explains **Mark ready** for validated **draft → ready** and that **legacy operational statuses** stay for **historical compatibility**; trip/dispatch boundary unchanged.
- **`ALLOWED_STATUSES`**, dropdown options, **dispatched** disable, **Save load** / **Mark ready** buttons, backend, board/list — **unchanged** (broader **status / `cancelled` / dropdown narrowing** — **parked**).

### Track B — Parser / AI / Load Lab

| Slice | Summary |
|--------|--------|
| **Slice 17A-1** | **`LoadDocumentParseResponse` mapper** — `parse_response` → stable contract for consumers. |
| **Slice 17A-2** | **Golden PDF + Lab JSON comparison tests** — regression safety on fixtures. |
| **Slice 17A-3** | **Stateless semantic adapter design report** — DB-free semantic layer approach (report-only precursor). |
| **Slice 17A-3A** | **Stateless semantic core skeleton** — `load_document_parse_semantic.py` + tests; injected OpenAI-shaped callable; **no** router, flag, frontend, DB, Lab run persistence, live OpenAI in unit tests. **Implemented locally and accepted after code review.** |
| **Slice B1** | **`POST /api/v1/loads/parse-document` semantic adapter flag + orchestrator** — **`LOAD_PARSE_DOCUMENT_SEMANTIC_ADAPTER_ENABLED`** default **false**; **`load_document_parse_orchestrator.py`**; flag **off** = legacy regex only; flag **on** = semantic stateless only (**no** silent regex fallback); **`response_model=LoadDocumentParseResponse`**; route **DB-free**; **real OpenAI injectable at router:** **B2-B**; **no** Load Lab run persistence; **no** frontend / trip / dispatch / **`Load.status`** / **`dispatch_trips`** change. |
| **Slice B2-A** | **Shared OpenAI chat JSON helper** — **`app/services/openai_chat_json_schema.py`** (`openai_chat_json_schema_raw`, **`extract_chat_completion_content_json`**, **`openai_chat_json_schema_content`**); **`tests/test_openai_chat_json_schema.py`** (mocked **`httpx.AsyncClient`**, **no** live OpenAI); Load Lab **`_openai_chat_json_schema`** delegates to shared **`openai_chat_json_schema_raw`**; **no** DB / run persistence in shared module; **no** frontend / trip / dispatch / **`Load.status`** / **`dispatch_trips`**. **B2-B** wires parse-document to **`openai_chat_json_schema_content`** via thin wrapper. |
| **Slice B2-B** | **Real semantic client wiring behind parse-document flag** — router passes **`parse_document_openai_chat_json_schema`** only when **`LOAD_PARSE_DOCUMENT_SEMANTIC_ADAPTER_ENABLED=true`** (**default remains false**); flag **off** = legacy parser; flag **on** = semantic stateless only (**no** silent regex fallback); empty **`OPENAI_API_KEY`** → **`skipped_missing_key`**, **no** HTTP call; **`context`** allowlist sanitization (**no** **`parse_diagnostics` / `ai_model_output` / `run_id`** leaks); **`tests/test_load_document_parse_openai.py`** + existing semantic/orchestrator/openai-helper suites. **No** DB on parse route; **no** Load Lab run persistence; **no** frontend / trip / dispatch / **`Load.status`** / **`dispatch_trips`** changes. |
| **Slice B4** | **Parse-document semantic prompt + JSON schema v1** — **`ParseDocumentSemanticModelOutput`** (no **`raw_text`** / **`context`** in AI output); prompt **`parse_document_prompt_v1`**, schema meta **`parse_document_semantic_schema_v1`**, OpenAI **`json_schema.name`** **`parse_document_semantic_v1`**; server attaches PDF **`raw_text`** + allowlisted **`context`**; lab-shaped injectable still uses mapper; semantic-shaped validates via Pydantic; extra root keys ignored; AI **`warnings`** precede PDF extract **`warnings`**; **flag default unchanged**; **semantic not enabled** for demo/prod by policy; **no** frontend / trip / dispatch / DB grounding / Lab persistence; tests semantic/orchestrator/openai + adapter/golden. |
| **B5** | **Demo-readiness / real-PDF manual test plan** — **planning accepted** (report-only, **no** code); baseline **`parse_path=legacy`**, flag on **`parse_path=semantic`**, rollback; samples: committed **`docs/fixtures/load_lab/*.pdf`** + **`LOAD_LAB_CONTRACT_COMPARISON_REPORT.md`** PDF names where available; **hard / soft** fail categories + **safety boundaries** + **no secrets / full raw_text** in shared logs (see **§6 B5**). |
| **B5-A** | **Controlled demo-tenant manual parse-document test** — **evidence accepted** (manual run on **demo** / **`tenant_demo`** / **demo.truckerp.me**); **POST `/api/v1/loads/parse-document` only**; full findings **§6 B5-A**. **Not** semantic **production-ready**; **no** broad semantic enablement from this evidence alone. |
| **B6** | **Real broker PDF semantic evaluation plan** — **report accepted:** [`B6_REAL_BROKER_PDF_SEMANTIC_EVALUATION_PLAN.md`](./B6_REAL_BROKER_PDF_SEMANTIC_EVALUATION_PLAN.md). **No** broad semantic enablement; **not** production-ready. |
| **B6-A** | **Phase 1 real broker PDF evaluation (parse-document)** — evidence accepted as **2/3 complete** for **`tenant_demo`** **only** — **not** “3/3,” **not** **JB Hunt tested**. **Armstrong** + **TQLRC** evaluated (Lab **48** / **50**); **JB Hunt** (`JBHunt.pdf` / historical **run 38**) **missing / owner-waived** for this environment. See **§6 B6-A**. |
| **B6-A1** | **JB Hunt recovery search** — **closed** (report-only): **no** Load Lab row, **no** stored PDF, **no** `/tmp` artifact, **no** repo fixture, **no** `parse_response` on **`tenant_demo`**. **Owner decision:** proceed with **2/3** Phase 1 evidence; **JB Hunt** on **data recovery backlog** (re-upload or other env if ever needed). |
| **B6-B** | **Phase 2 real broker PDF evaluation** — **paused** (report-only, owner-supplied files only). No further Load Lab / PDF **eval loops** on this host until **operator acceptance** or corpus recovery. **Do not** block on missing Hub/Canada/FIRST BASE/JB Hunt assets. See [`B6_REAL_BROKER_PDF_SEMANTIC_EVALUATION_PLAN.md`](./B6_REAL_BROKER_PDF_SEMANTIC_EVALUATION_PLAN.md). |
| **B6-PARITY** | **Semantic parse ↔ Load Lab parity closeout** — **closed** (report-only): **`POST /loads/parse-document`** semantic path matches **accepted** Load Lab **`truckerjson`** **intent** + **`LoadDocumentParseResponse`** **safety** as far as **B4/B2-B** design goes; **not** a byte-for-byte clone of Lab **guarded** post-processing; **no** **must-fix** code slice before **owner/operator testing** behind flag (**§6 B6-PARITY** narrative). |

**B6-PARITY — Semantic parse pipeline parity closeout (closed):**

- **Acceptance path:** **Operator testing** on real PDFs (demo/test, flag on) — not further historical corpus chasing on **`tenant_demo`**.
- **Mirrors:** **B4** prompt/schema/contract goals aligned with **Load Lab default** **`truckerjson`** comparison baseline (`docs/LOAD_LAB_CONTRACT_COMPARISON_REPORT.md` — default remains **truckerjson**; **critical_v1_1** stays **evidence-only**, **not** parse-document default).
- **Known delta (by design, not a gate):** parse-document is **stateless** — **no** `parse_diagnostics` JSON in model input, **no** tenant **broker DB grounding**, **no** Load Lab **post-AI guardrails** (reference gating/ranking, trailer/temp cleanup, broker authority repair, etc. from `load_lab_semantic.py`). **Strict** field parity with **guarded** Lab runs is **not** claimed.
- **Safety unchanged:** **no** `parse_diagnostics` / **`ai_model_output`** / **`run_id`** in **public** `context` (allowlist); **no** Lab run persistence from parse; **no** regex fallback when semantic flag **on**; default flag **off**.

**B6-A — Phase 1 evidence (2/3 complete, `tenant_demo`; JB Hunt owner-waived):**

- **Do not** label Phase 1 as **“3/3 complete.”** **Do not** report **JB Hunt** as tested on this environment.
- **Accepted:** **Armstrong** + **TQLRC** — legacy vs semantic `parse-document` vs Load Lab **`truckerjson`** reference; semantic **closer** to Lab on major fields than legacy.
- **Waived / missing:** **`JBHunt.pdf`** — no **`load_lab_extraction_runs`** row, no bytes under **`load_lab_uploads`**, no eval artifact — see **B6-A1** closure.
- **Legacy hard failures (evidence):** **Armstrong** — wrong **rate**, **route** / stop count, **weight**; **TQLRC** — wrong **broker_load_reference**, **inflated stops**, **commodity** garbage.
- **Safety (B6-A run):** **no** parse-document leak keys; **`loads`** / **`dispatch_trips`** unchanged; semantic flag **rollback** confirmed.
- **Backlog:** **`JBHunt.pdf`** / Lab run / `parse_response` recovery — **future data** work if product wants a true **3/3** Phase 1 later.
- **Prompt/schema follow-up candidates (future implementation — not started here):** normalize **`broker_load_reference`** (`#` / **`PO#`**); **MC/DOT** for **TQL**-style; Phase 2+ per **B6-B**.

**Slice B1 (accepted) — parse-document flag + orchestrator:**

- **Setting:** **`LOAD_PARSE_DOCUMENT_SEMANTIC_ADAPTER_ENABLED`** (`Settings.load_parse_document_semantic_adapter_enabled`) — **default `false`**; production default remains **legacy regex** until explicitly enabled.
- **Flag off:** Same behavior as before B1: **`parse_load_workspace_from_pdf_bytes`** only; response validated as **`LoadDocumentParseResponse`**; orchestrator adds **`context.parse_path = "legacy"`** (non-breaking observability).
- **Flag on:** **`parse_load_workspace_from_pdf_semantic_stateless` only** — **no** silent fallback to regex; skips/errors surface as **sparse `extracted`**, **warnings**, and **`context.semantic_outcome`**; **`context.parse_path = "semantic"`** (normalized from skeleton).
- **Route:** **`POST /api/v1/loads/parse-document`** unchanged **`response_model=LoadDocumentParseResponse`**; PDF size/`%PDF-` validation unchanged; **no** `get_tenant_db` on this handler; **injectable wired at router:** see **B2-B** — **`parse_document_openai_chat_json_schema`** when flag **on**.
- **Out of scope / unchanged:** **no** Load Lab run persistence from parse; **no** frontend contract change; **no** trip/dispatch/**`Load.status`**/**`dispatch_trips`**/**`ALLOWED_STATUSES`** edits.
- **Tests passed (suite):** `test_load_document_parse_adapter.py`, `test_load_document_parse_golden_comparison.py`, `test_load_document_parse_semantic.py`, `test_load_document_parse_orchestrator.py`. (Post **B2-B:** add **`test_openai_chat_json_schema.py`**, **`test_load_document_parse_openai.py`**.)

**Slice B2-B (accepted) — real semantic client wiring behind parse-document flag:**

- **`POST /api/v1/loads/parse-document`** passes **`parse_document_openai_chat_json_schema`** (thin delegate to **`openai_chat_json_schema_content`**) **only when** **`LOAD_PARSE_DOCUMENT_SEMANTIC_ADAPTER_ENABLED=true`**.
- **Default flag remains `false`** — production default stays **legacy regex** until explicitly enabled.
- **Flag off:** legacy parser only (**`parse_load_workspace_from_pdf_bytes`** via orchestrator); **`context.parse_path = "legacy"`**.
- **Flag on:** **semantic stateless path only** — **`parse_load_workspace_from_pdf_semantic_stateless`**; **no** silent regex fallback on failure or skip.
- **Missing `OPENAI_API_KEY`:** **`context.semantic_outcome = "skipped_missing_key"`**, warning to operator, **no** OpenAI HTTP call, **no** regex fallback.
- **`context`** is sanitized through **`_PUBLIC_CONTEXT_ALLOW_KEYS`** — unknown keys stripped; **`parse_diagnostics` / `ai_model_output` / `run_id`** (and related lab-only roots) do not leak in public **`context`**.
- **No** tenant **`get_tenant_db`** / DB session on the parse route; **no** Load Lab **`ExtractionRun`** / run persistence from parse-document.
- **No** frontend, trip/dispatch, **`Load.status`**, **`dispatch_trips`**, or **`ALLOWED_STATUSES`** changes in **B2-B** scope.
- **Tests passed:** **`./venv/bin/python -m pytest tests/test_openai_chat_json_schema.py tests/test_load_document_parse_semantic.py tests/test_load_document_parse_orchestrator.py tests/test_load_document_parse_openai.py -v`** (mocked / fakes only — **no** live OpenAI). (See **B4** for **adapter + golden** regression.)

**Slice B4 (accepted) — parse-document semantic prompt + JSON schema v1:**

- **Schema:** **`ParseDocumentSemanticModelOutput`** in **`app/schemas/load_document_parse.py`** — AI returns **`document`**, **`extracted`**, **`warnings`**, **`field_confidence`** only; **`raw_text`** and **`context`** are **not** part of the model-output schema.
- **Versions:** **`SEMANTIC_PROMPT_VERSION_PARSE_DOCUMENT` = `parse_document_prompt_v1`**; **`SEMANTIC_SCHEMA_VERSION_PARSE_DOCUMENT` = `parse_document_semantic_schema_v1`**; OpenAI **`json_schema`** name **`parse_document_semantic_v1`** (see **`load_document_parse_semantic.py`**).
- **Server:** attaches **PDF-extracted `raw_text`**, **upload `document.filename`**, and **allowlist-sanitized `context`** (`semantic_outcome`, meta, echo ids).
- **Payload routing:** **Lab-shaped** dict (lab root keys) → **`map_lab_parse_response_to_document_contract`** unchanged; **semantic-shaped** → **`ParseDocumentSemanticModelOutput.model_validate`** then map to **`LoadDocumentParseResponse`**.
- **Tolerance / ordering:** unknown **extra root keys** ignored (`extra="ignore"`); **AI `warnings`** precede **PDF extraction `warnings`** in the merged list.
- **Policy:** **`LOAD_PARSE_DOCUMENT_SEMANTIC_ADAPTER_ENABLED`** default remains **`false`**; **B5-A** evidence **accepted** — semantic is **still not** **production-ready** and **not** broadly enabled; **no** silent semantic default; broader enablement remains **product-gated**.
- **Out of scope:** **no** frontend; **no** trip/dispatch / **`Load.status`** / **`dispatch_trips`** / **`ALLOWED_STATUSES`**; **no** DB broker grounding; **no** Load Lab run persistence from parse-document.
- **Tests passed:** semantic/orchestrator/openai/openai-schema suites + **adapter + golden**:  
  **`./venv/bin/python -m pytest tests/test_load_document_parse_semantic.py tests/test_load_document_parse_orchestrator.py tests/test_load_document_parse_openai.py tests/test_openai_chat_json_schema.py -v`** and **`./venv/bin/python -m pytest tests/test_load_document_parse_adapter.py tests/test_load_document_parse_golden_comparison.py -v`**.

**B5 (accepted) — demo-readiness / real-PDF manual test plan (planning only):**

- **Status:** **Report accepted** — **no** code changes from the plan alone; **no** automatic enablement. **B5-A** **evidence accepted** — controlled **demo** manual run (**§6 B5-A**). **Semantic remains off** by default; **not** **production-ready**; **no** broad enablement.
- **Corpus eval:** **B6-B** **paused** — **§6 B6-B** / **§14**; **B6-PARITY** **closed** (**§6**).
- **Baseline vs semantic:** flag **off** → **`context.parse_path = "legacy"`** (regex); flag **on** → **`context.parse_path = "semantic"`** (no silent regex fallback).
- **Rollback:** set **`LOAD_PARSE_DOCUMENT_SEMANTIC_ADAPTER_ENABLED=false`** (or rely on default) + **API restart/reload**; verify **`parse_path`** returns **legacy**.
- **Sample PDFs:** committed **`docs/fixtures/load_lab/*.pdf`**; plus **Load Lab comparison** filenames from **`docs/LOAD_LAB_CONTRACT_COMPARISON_REPORT.md`** (e.g. JBHunt, Armstrong, TQLRC, multi-stop fixtures) **where corpus available** — not all may be in-repo.
- **Hard fail (stop):** HTTP **5xx**; invalid **`LoadDocumentParseResponse`** shape; **`parse_diagnostics` / `ai_model_output` / `run_id`** (or **`choices`**) leaks in response; **load/trip/dispatch** side effects; **`Load.status=dispatched`**; empty **`extracted`** on clear digital rate con without credible **`warnings`**; obvious wrong **broker** or **stop count/order** on simple PDFs.
- **Soft fail / review:** date formatting; optional contacts; secondary refs; **`warnings`** wording; known **broker-load-reference** ambiguities (per comparison report).
- **Safety boundaries:** **no** automatic load save from parse alone; **no** trip creation; **no** assignment; **no** **`dispatch_trips`**; **no** **`Load.status=dispatched`**; **no** custody / payroll / package triggers **from** **`POST /loads/parse-document`**.
- **Logging hygiene:** **no** secrets or **full `raw_text`** in shared logs / transcripts.

**B5-A (accepted) — controlled demo-tenant manual test (evidence report):**

**Policy:** Acceptance is **evidence-only** on the **demo** tenant — **not** “semantic is production-ready” and **not** authorization to enable semantic **broadly** (demo-wide or prod).

1. **Environment:** **demo** / **`tenant_demo`** / **demo.truckerp.me**; only **`POST /api/v1/loads/parse-document`** exercised; **no** load save/create, **no** trip, **no** dispatch calls.
2. **Baseline:** flag **off** → **`context.parse_path = legacy`**.
3. **Semantic:** temporary flag **on** → **`parse_path = semantic`**; **`semantic_outcome = success`** on **both** committed **`docs/fixtures/load_lab`** fixture PDFs (`load_lab_fixture_1pickup_3deliveries.pdf`, `load_lab_fixture_3pickups_1delivery.pdf`).
4. **Rollback:** flag **off** restored; **`parse_path = legacy`** confirmed **after** rollback.
5. **Safety:** no response keys **`parse_diagnostics`**, **`ai_model_output`**, **`run_id`**, **`choices`**; **`loads`** row count unchanged; **`dispatch_trips`** count unchanged; **no** **`Load.status` / dispatched** side effects attributed to parse.
6. **Quality findings:** semantic **4** stops vs legacy **7** on **both** synthetic fixtures; **rate** matched legacy; broker **MC/DOT** populated in semantic where legacy left null; **equipment / trailer / miles / weight / temp** mostly still null; **commodity** missing on second semantic fixture; **only two** synthetic fixtures — **insufficient** for production or broad demo enablement.
7. **Operational finding:** stale API image initially yielded **`skipped_no_client`** (injectable not wired in running image); future semantic tests need a **deployment smoke check** that the **running** image passes **OpenAI injectable** wiring when the flag is **on** (align image to repo / verify handler).
8. **Next (Track B):** **B6-B** **paused**; **B6-PARITY** **closed**; **operator testing** behind flag (**§14**).

**Slice B2-A (accepted) — shared OpenAI chat JSON helper:**

- **New:** **`app/services/openai_chat_json_schema.py`** — stateless **`httpx`** OpenAI **`json_schema`** + **`json_object`** fallback (same behavior as former Load Lab inline helper); **`extract_chat_completion_content_json`** / **`openai_chat_json_schema_content`**.
- **New tests:** **`tests/test_openai_chat_json_schema.py`** — **`httpx.AsyncClient`** mocked; **no** live OpenAI.
- **Load Lab:** **`load_lab_semantic._openai_chat_json_schema`** now **delegates** to **`openai_chat_json_schema_raw`** only (`semantic_extract_run` wire path unchanged).
- **B2-B follow-on:** **`POST /parse-document`** (flag **on**) uses shared helper via **`app/services/load_document_parse_openai.py`**.
- **Out of scope:** **no** frontend; **no** DB / **`LoadLabExtractionRun`** / broker grounding in shared module; **no** trip / **`Load.status`** / **`dispatch_trips`**.
- **Tests passed:** `test_openai_chat_json_schema.py` + **`test_load_document_parse_semantic.py`** + **`test_load_document_parse_orchestrator.py`**.

### Track C — Trip / Dispatch

| Slice | Summary |
|--------|--------|
| **PR #31 / legacy dispatch cutover** | Generic **`Load.status` → `dispatched`** blocked for normal UI/API paths. |
| **Slice 14A** | **`PUT /api/v1/trips/{trip_id}/assignment`** — explicit trip assignment API. |
| **Slice 15A** | **Load Page / Trip assignment boundary cleanup** — links to Trip Workspace; intake vs assignment separated in UX. |

### Cross-track reference — current local notes

- **`load_document_parse_adapter.py`**, **`load_document_parse_semantic.py`** (**B4** prompt + **`ParseDocumentSemanticModelOutput` JSON Schema**), **`load_document_parse_openai.py`** (**B2-B** injectable wrapper), **`load_document_parse_orchestrator.py`** (B1), **`openai_chat_json_schema.py`** (B2-A; **B4** fallback copy aligned to semantic output keys).
- **`POST /api/v1/loads/parse-document`:** orchestrator + **`LOAD_PARSE_DOCUMENT_SEMANTIC_ADAPTER_ENABLED`** (default **off** = legacy regex); **on** = semantic path only (**B1**) with real OpenAI client (**B2-B**) and **B4** prompt + schema when flag enabled. **B5** plan + **B5-A** demo-tenant evidence **accepted** — semantic **not** production-ready / **not** broadly enabled. **B6** plan: [`B6_REAL_BROKER_PDF_SEMANTIC_EVALUATION_PLAN.md`](./B6_REAL_BROKER_PDF_SEMANTIC_EVALUATION_PLAN.md). **B6-A** Phase 1 **2/3**; **B6-A1** **closed**; **B6-B** **paused**; **B6-PARITY** **closed** (**§6**).
- Parser / OpenAI helper tests: `test_load_document_parse_adapter.py`, `test_load_document_parse_golden_comparison.py`, `test_load_document_parse_semantic.py`, **`test_load_document_parse_orchestrator.py`**, **`test_openai_chat_json_schema.py`** (B2-A), **`test_load_document_parse_openai.py`** (B2-B).
- **No Load Lab run persistence** from production parse; **no** semantic **default** without explicit flag.
- **No Load Lab production wiring** as the main load form.

---

## 7. What is paused

- **Track C (deep):** trip **execution**, **custody**, **terminal/yard**, **recovery**, **payroll** (and related slices)—not active intake/parser milestones.
- **Track B (production / parser):** **B1–B4** implementation complete; **B3** + **B5** + **B5-A** accepted. **B6** plan; **B6-A** Phase 1 **2/3**; **B6-A1** **closed**. **B6-B** Phase 2 **paused** (owner files / operator path). **B6-PARITY** (**semantic ↔ accepted Lab contract**) **closed** — **§6**. **Semantic remains off** by default; **not** production-ready; **no** broad enablement.
- **Track A / model:** **`Load.status` hard cleanup**, **`cancelled`**, dropdown narrowing, **`ALLOWED_STATUSES`** edits — **parked** (not prerequisites for Track B **planning**); **A1**/**A2**/**A3** did **not** narrow **`ALLOWED_STATUSES`**.

---

## 8. Next main focus (Track A)

- **Load Page Save/Commit Contract Plan** — **accepted**. **A1**/**A2**/**A3** (**wording-only**) complete for current scope.
- **Track A — parked (until product pulls again):** **`cancelled`**, status dropdown filtering, **Save Draft** labeling, **ready-only-via-Mark-ready** enforcement — see archived **A3 report** / Decision 11 roadmap; **no** board rewrite required as gate.

---

## 9. Track B — next planned work (parser adapter / parse-document)

**B1**, **B2-A**, **B2-B**, and **B4** implementation accepted — see **§6**. **B3** + **B5** **planning reports accepted** (no code). **B5-A** **evidence accepted** — controlled **demo** / **`tenant_demo`** manual test (**§6 B5-A**); semantic is **not** **production-ready**; **no** broad semantic enablement. **B6** plan accepted; **B6-A** Phase 1 **2/3**; **B6-A1** **closed**. **B6-B** **paused**. **B6-PARITY** **closed** — parse-document semantic vs **accepted** Lab **`truckerjson`** **intent** + response **safety**; **operator testing** is the forward acceptance path.

### B5-A status (closed — evidence accepted)

Summary matches **§6 B5-A**: environment (demo only, parse-document **only**), baseline **legacy**, semantic **success** on two fixtures, rollback **legacy**, safety (no leak keys, stable **loads** / **dispatch_trips** counts, no dispatched side effects), quality deltas (stops 7→4, rates matched, MC/DOT vs legacy, sparse equipment/miles/weight/temp, commodity gap on second PDF, **N=2** fixtures), operational note (stale image → **`skipped_no_client`** until image matches injectable wiring).

### B6 / B6-A / B6-A1 / B6-B / B6-PARITY status

- **B6** plan: [`docs/B6_REAL_BROKER_PDF_SEMANTIC_EVALUATION_PLAN.md`](./B6_REAL_BROKER_PDF_SEMANTIC_EVALUATION_PLAN.md) — **accepted** (report-only).
- **B6-A** Phase 1: evidence accepted as **2/3 complete** — **Armstrong**, **TQLRC** tested; **JB Hunt not tested** — missing / **owner-waived** on **`tenant_demo`** (**§6 B6-A**). **Do not** call Phase 1 **3/3**.
- **B6-A1** — **closed**: recovery search found **no** Lab row / PDF / `/tmp` artifact / repo fixture / `parse_response` for JB Hunt on **`tenant_demo`**; owner accepted **2/3**; **JB Hunt** → **data recovery backlog**.
- **B6-B** — **paused**: no further **Load Lab / PDF evaluation loops** until **operator-driven acceptance** or **owner-provided** Phase 2 corpus; missing assets are **not** a blocker (**§6 B6-B**).
- **B6-PARITY** — **closed** (report-only): **semantic `parse-document`** aligned with **accepted** **`truckerjson`**-style goals + **`LoadDocumentParseResponse`** + **no-leak** policy; **not** full **guarded** Lab post-pipeline parity — **§6 B6-PARITY** narrative.

**Still in order:**

1. ~~Route / feature-flag wiring on **`POST /api/v1/loads/parse-document`** (default off).~~ **Done (B1).**
2. ~~Shared OpenAI **`json_schema` / fallback** transport.~~ **Done (B2-A).**
3. ~~**B2-B** — semantic **client** wiring + **`context`** allowlist / **`skipped_missing_key`**.~~ **Done (B2-B).**
4. ~~**B3** — semantic quality / schema readiness **report**.~~ **Done (accepted).**
5. ~~**B4** — **v1** prompt + real JSON schema for parse-document semantic path.~~ **Done (B4).**
6. ~~**B5** — demo manual test **plan** (report-only).~~ **Done (accepted).**
7. ~~**B5-A** — controlled manual test + **report-only** evidence (**demo** / **`tenant_demo`**).~~ **Done (accepted — §6 B5-A).**
8. ~~**B6** — **real broker PDF semantic evaluation plan** (**report-only**).~~ **Done** — [`B6_REAL_BROKER_PDF_SEMANTIC_EVALUATION_PLAN.md`](./B6_REAL_BROKER_PDF_SEMANTIC_EVALUATION_PLAN.md).  
9. ~~**B6-A1** — **JB Hunt** recovery / Phase 1 completion decision.~~ **Done** — **2/3** Phase 1 accepted; **JB Hunt** waived + **backlog** (**§6**).  
10. ~~**B6-B** — Phase 2 real broker PDF evaluation (Hub/LME, Canada reefer, FIRST BASE/DeGroot).~~ **Paused** — owner files / operator path only (**§6**).  
11. ~~**B6-PARITY** — semantic parse ↔ accepted Load Lab contract check.~~ **Done (closed — report-only)** — **§6 B6-PARITY**.  
12. **Broker grounding input DTO** at router edge (optional; after operator feedback).
13. **Production parse-document** enablement — **no** silent semantic default; **not** production-ready; product gate.

**Slice 17A-3A non-goals** (historical): skeleton originally shipped without router/flag/DB/Lab persistence — **B1** added router/orchestrator + flag; **B2-B** added real OpenAI injectable when flag **on**; **B4** added v1 prompt + **`ParseDocumentSemanticModelOutput`** schema.

---

## 10. Deferred / not now (cross-track parking lot)

- Live **`/loads/parse-document`** semantics in prod without flag + contract alignment.
- **Full** Lab semantic pipeline as **silent** prod default.
- **DB-backed broker grounding** inside parser core without DTO edge pattern.
- **OpenAI live** in default CI.
- **Load Lab run persistence** driven from production parse (unless explicitly designed).
- **Assign & Send**, **driver package**, **custody**, **terminal / yard**, **payroll / recovery** (Track C future; **paused**).

---

## 11. Safety checklist for every future slice

Every slice **must** pass the checklist **and** declare **track(s)** per **§12**.

- [ ] **No accidental load persistence** from parser-only paths (**B**) beyond the **Track A** save/commit contract
- [ ] **No trip creation** from parser
- [ ] **No driver / truck / trailer assignment** from parser
- [ ] **No `dispatch_trips` write** from parser
- [ ] **No `Load.status` = `dispatched` writer** (or stealth dispatch) from adapter/parser
- [ ] **No full `parse_diagnostics` leak** unless explicitly reviewed
- [ ] **No `ai_model_output` leak** unless explicitly reviewed
- [ ] **No OpenAI** in normal CI (mocks/fakes unless labeled integration)
- [ ] **No DB** in unit tests unless integration-marked and documented
- [ ] **Frontend contract** remains **`LoadDocumentParseResponse`** for parse unless deliberately versioned

---

## 12. Mandatory slice declaration (every future implementation slice)

Each slice PR / description **must** include:

- **Track:** **A** / **B** / **C** (or primary + secondary, e.g. “A + C touch review only”).
- **Touches:** files, APIs, user-visible behavior.
- **Must not touch:** other tracks’ invariants (e.g. parser must not write dispatch).
- **Tests:** what runs in CI; integration vs unit.
- **Rollback:** feature flag, revert path, or config kill-switch.
- **Tracker:** **yes/no** — if **yes**, update **this document** in the same merge window as acceptance.

---

## 13. Update rule

After every **accepted** slice: update this tracker **before** starting the next slice (completed tables, paused list, next focus).

---

## 14. Immediate next action

1. **Track B — operator acceptance:** **`LOAD_PARSE_DOCUMENT_SEMANTIC_ADAPTER_ENABLED`** stays **default `false`**. Owner may enable on **demo/test** only when ready; operators exercise **`POST /api/v1/loads/parse-document`** with **real PDFs**; report issues with examples (responses **redacted** per **§6 B5** logging hygiene). **Do not** enable semantic **broadly**; **do not** mark **production-ready**. **B6-B** corpus evaluation **paused** unless **owner supplies** files. **B6-PARITY** **closed** (**§6**).
2. **Track A:** No mandatory next slice until product pulls **parked** items (**§8**).

---

*Last updated: **B6-PARITY** **closed** (semantic ↔ accepted Lab **`truckerjson`** **intent** + **`LoadDocumentParseResponse`** safety); **B6-B** **paused**; **B6-A** **2/3**; **B6-A1** **closed**; **operator testing** behind flag; **semantic** default **off** / **not** production-ready / **not** broadly enabled; Track A **parked**.*
