# B6 — Real Broker PDF Semantic Evaluation Plan

**Track:** B — Parser / AI / Load Lab  
**Type:** Report-only (no code, no semantic enablement, no production-readiness claim).  
**Prerequisites:** B5-A accepted on **synthetic** fixtures only; **`POST /api/v1/loads/parse-document`** semantic path is **off** by default everywhere unless explicitly toggled for controlled tests.

**Contract references:** `LoadDocumentParseResponse` / `LoadParseExtractedFields` (`app/schemas/load_document_parse.py`); semantic behavior + prompt + allowlisted `context` (`app/services/load_document_parse_semantic.py`).  
**Path context:** [`docs/CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) — workspace parse vs Load Lab vs intake are **not** one pipeline; this plan evaluates **parse-document** (legacy vs B4 semantic) and **relates** outputs to Load Lab evidence where useful.

**Related evidence:** [`docs/LOAD_LAB_CONTRACT_COMPARISON_REPORT.md`](./LOAD_LAB_CONTRACT_COMPARISON_REPORT.md) (runs **38–43**, `truckerjson` vs `critical_v1_1`); [`docs/LOAD_LAB_REAL_PDF_EVALUATION.md`](./LOAD_LAB_REAL_PDF_EVALUATION.md).

---

## 1. Candidate PDF set

### 1.1 What is in-repo today

| Asset | Location | Notes |
|--------|----------|--------|
| Synthetic load-lab PDFs | `docs/fixtures/load_lab/load_lab_fixture_1pickup_3deliveries.pdf`, `..._3pickups_1delivery.pdf` | **Committed**; B5-A already ran these; **not** real broker rate cons. |
| Real broker PDF bytes | **Not** under `docs/fixtures/` | Glob search finds **no** `JBHunt.pdf`, `Armstrong.pdf`, `TQLRC.pdf`, etc. in the repo tree. |

### 1.2 Real broker PDFs named in Load Lab comparison (evidence set 38–43)

These filenames and run ids appear in [`LOAD_LAB_CONTRACT_COMPARISON_REPORT.md`](./LOAD_LAB_CONTRACT_COMPARISON_REPORT.md). They are **operator-curated** real documents used for **Load Lab** semantic contract comparison, **not** shipped as git fixtures.

| run_id | Filename (as in report) | Broker / theme |
|--------|---------------------------|----------------|
| 38 | `JBHunt.pdf` | J.B. Hunt |
| 39 | `Armstrong.pdf` | Armstrong Transport Group |
| 40 | `161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf` | FIRST BASE / DeGroot Logistics |
| 41 | `612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf` | Canada reefer / cross-border style |
| 42 | `order_confirmation_2398968_4674419509316643175-lme_temp.pdf` | Hub Group / LME-style order confirmation |
| 43 | `TQLRC.pdf` | TQL rate con |

**Where the bytes likely live:** tenant **`demo`** (`tenant_id=53`) **Load Lab** persistence — `load_lab_extraction_runs` (and related storage for uploaded PDFs per [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md)). Pair-eval tool writes ephemeral JSON under `/tmp/contract_pair_{run_id}_*.json` **inside the API container** (not committed).

### 1.3 Inclusion order (recommended)

**Phase 1 (first scripts / operator sessions):** runs **38, 39, 43** — relatively “standard” two-stop rate cons with rich comparison table coverage (JB Hunt, Armstrong, TQL).

**Phase 2:** **42** (Hub/LME) — exercises **broker_load_reference** ambiguity (Order Number vs long numeric) documented in the comparison report.

**Phase 3:** **41** (Canada reefer) — temperature / commodity encoding diffs between contracts in the table; good stress for **`temperature_requirement`** and **`commodity`**.

**Phase 4:** **40** (FIRST BASE / DeGroot) — commodity gap on `truckerjson` vs `critical` in report; tests “thin” commodity lines.

### 1.4 Commit safety (privacy)

| Content | Safe to commit? |
|---------|------------------|
| Original real broker PDFs | **Generally no** — may contain customer, facility, phone, email, carrier, broker, and shipment identifiers. Treat as **tenant-private** unless legal/product explicitly approves scrubbed samples. |
| Synthetic fixtures already in `docs/fixtures/load_lab/` | **Yes** — designed for repo use. |
| Redacted **JSON** (normalized fields only) | **Yes, conditional** — if values are scrubbed or synthetic (e.g. replace facility names with tokens, truncate refs), and reviewed; prefer **structure + types** over verbatim strings. |
| Comparison **reports** (markdown tables like the contract report) | **Yes** — already practice in-repo; avoid pasting full `raw_text` or OCR dumps. |

---

## 2. Evaluation matrix

For **each** PDF in the active set, record **four** columns where available:

| Column | Source | How to obtain |
|--------|--------|----------------|
| **Legacy (parse-document)** | `POST /api/v1/loads/parse-document` with **`LOAD_PARSE_DOCUMENT_SEMANTIC_ADAPTER_ENABLED=false`** | Controlled env (e.g. demo tenant); expect **`context.parse_path`** = `legacy`. |
| **Semantic (parse-document)** | Same endpoint with flag **temporarily** `true` + verified injectable wiring in **running** image | Expect **`context.parse_path`** = `semantic`, **`context.semantic_outcome`** in `{success, skipped_*, openai_error, …}`. |
| **Load Lab reference** | Last successful `parse_response` for the same run id, or re-semantic snapshot | Prefer **one** contract as reference (e.g. `truckerjson` **or** `critical_v1_1`) per row; **do not** mix contracts without labeling. `compare_load_lab_contracts_eval` / pair-eval JSON if re-run. |
| **Human expected truth** | Operator sign-off | Use PDF + domain knowledge; for 38–43, reuse **correct / needs_review** semantics from the comparison table as **hints**, not automatic ground truth. |

**Important:** Load Lab outputs may include **`parse_diagnostics`**, **`critical_extraction_v1_1`**, etc.; **`LoadDocumentParseResponse` from parse-document must not** expose those keys publicly (B2-B allowlist). Matrix scoring should still **check absence** of leaks on the **parse-document** columns.

---

## 3. Fields to score

Align scoring with [`app/schemas/load_document_parse.py`](../app/schemas/load_document_parse.py) / semantic prompt targets ([`app/services/load_document_parse_semantic.py`](../app/services/load_document_parse_semantic.py)):

| Domain | JSON paths / notes |
|--------|-------------------|
| Broker name | `extracted.broker_name_snapshot` |
| Broker MC/DOT | `extracted.broker_mc_number_snapshot`, `extracted.broker_dot_number_snapshot` |
| Broker load reference | `extracted.broker_load_reference` |
| Rate | `extracted.rate`, `extracted.customer_rate` if present |
| Miles | `extracted.miles` |
| Equipment / trailer | `extracted.equipment_type`, `trailer_type`, `trailer_size`, `extracted.mode` |
| Commodity / weight / temp | `extracted.commodity`, `estimated_weight`, `temperature_requirement` |
| Stops | `extracted.stops[]`: **count**, **order** (`sequence`), **stop_type**, facility/address fields, **appointment_date**, **appointment_time_text** |
| References | `extracted.references[]` (`kind`, `value`, …) |
| Warnings | `warnings[]` (semantic + PDF extraction merge order per B4) |
| Field confidence | `field_confidence` keys and levels (`low`/`medium`/`high`) |
| Semantic outcome | `context.semantic_outcome` (parse-document semantic path only) |

Optional cross-check: broker contact snapshots if present (`broker_contact_*`) — **soft** unless product declares them dispatch-critical.

---

## 4. Pass / fail categories

### 4.1 Hard fail (stop — tune, disable, or fix deployment before any broader trial)

- **Wrong broker** (identity points to carrier/shipper/consignee vs issuing broker).
- **Wrong rate** (materially different USD linehaul vs PDF anchor used in human review).
- **Wrong primary load reference** (dominant broker shipment id — not a phone, BOL substitution, or nonsense token).
- **Stop count or order wrong** on **simple** PDFs (e.g. clear one pickup + one delivery): must match human expectation; multi-stop PDFs need explicit human definition of “physical” stops.
- **Leak:** `parse_diagnostics`, `ai_model_output`, `run_id`, raw **`choices`**, or other OpenAI wire in HTTP JSON (see B5-A checklist).
- **Invalid shape:** response fails **`LoadDocumentParseResponse`** validation or HTTP **5xx** from parse route.
- **Route / ops error:** auth, tenant resolution, or file limits preventing an apples-to-apples run.

### 4.2 Soft fail (review — acceptable for limited demo if bounded and surfaced)

- Optional **broker contact** missing or generic.
- **Secondary references** missing (BOL/PO) when non-critical.
- **Date format** differences (`YYYY-MM-DD` vs `MM/DD/YYYY`) with same calendar meaning.
- **Sequence origin** offset (0-based vs 1-based) **if** stop count, types, and geography still align — product must decide canonical display.
- **Low `field_confidence`** or empty confidence for a field.
- **Warning text** quality (too verbose, unclear, or missing when ambiguous).
- **Equipment** string normalization (e.g. `53' Van` vs `Van 53'`) without changing meaning.

---

## 5. Redaction / privacy

| Artifact | Guidance |
|----------|----------|
| **Repo storage** | Prefer **synthetic PDFs** + **redacted JSON**; avoid committing **raw** customer/broker PDFs unless cleared. |
| **Local-only** | Original PDFs, full `parse_response` dumps, and anything with `raw_text` from real docs — **operator workstation** or **secure tenant storage** only. |
| **Redacted expected JSON** | Recommended path: maintain **normalized** expected objects (field paths above) with scrubbed strings; pair with an internal id → filename map **outside** git. |
| **Written summaries** | Publish **normalized field values**, **counts**, **sequence lists**, **hashes** of outputs for drift detection — **not** full `raw_text` or full PDF bodies in shared reports. |

---

## 6. Test method (choice)

| Option | Description | B6 recommendation |
|--------|-------------|-------------------|
| **A** | Manual redacted comparison report only | **Primary** for B6 execution: lowest risk to privacy; matches B5-A style; easy to gate with product. |
| **B** | Local / non-CI script (operator machine or API container) reading PDFs from **non-repo** paths | **Strong supplement** for repeatability; **must not** land real PDF paths or secrets in repo; script may live in `tools/` but default to **opt-in** data dirs. |
| **C** | Committed **redacted JSON** fixtures | **Follow-on** after A/B stabilize which fields matter; avoids binary PDF in git. |
| **D** | Full automated CI tests on real PDFs | **Later** — **not** B6; real PDFs should not block CI; use synthetics in CI only. |

**Selected path for B6:** **A** (required) + **B** (optional, local-only inputs), then **C** only for scrubbed artifacts product approves. **D** explicitly **out of scope** until corpus and redaction policy are settled.

---

## 7. Decision gate (when semantic may move states)

Semantic remains **not production-ready** and **not broadly enabled** until product explicitly moves the gate. Proposed criteria:

| Gate state | Conditions (all must be true unless noted) |
|------------|----------------------------------------------|
| **Prompt/schema tuning** | Hard fails **absent** on Phase **38,39,43**; soft fails documented; B5-A-style rollback proven; no leak keys on parse-document responses. |
| **More real PDF testing** | Tuning iteration applied; Phase **42,41,40** scored; Hub/LME reference ambiguity documented with **human** preferred id; Canada reefer temp/commodity rules aligned with product. |
| **Limited demo trial** | At least **six** real PDFs (the 38–43 set) pass **hard** gates; operator runbook exists (flag on/off, rollback, image smoke); UI surfaces **`parse_path`** / **`semantic_outcome`**; **time-box** and **tenant-scoped** (e.g. demo only) with explicit end date; **no** default-on for prod. |
| **Stay disabled (default)** | Any recurring hard failure on anchor PDFs; leak detected; **skipped_no_client** / image drift repeats (injectable wiring); or product withholds sign-off. |

**Explicit non-gates:** Load Lab **`truckerjson` vs `critical_v1_1` “default switch”** decisions are **orthogonal** to parse-document semantic enablement — do not conflate them in sign-off.

---

## 8. Final recommendation — next concrete step after B6

1. **Execute Phase 1 (runs 38, 39, 43)** under **controlled** parse-document tests: legacy vs semantic side-by-side, **redacted** matrix, confirm **no** leak keys — **before** any prompt edit.
2. **Record** semantic vs Load Lab reference column **per field** for ref/rate/broker/stops; use comparison report **needs_review** rows to prioritize prompt/schema tweaks (dates, equipment splits, facility naming).
3. **Add deployment smoke:** after any API deploy where semantic might be tested, verify **`openai_chat_json_schema=injectable`** in running image when flag is on (B5-A operational finding).
4. **Revisit tracker** after B6 execution (not this plan doc alone): either open a **B6-A** “evaluation executed” evidence slice or fold results into the next **B7** implementation milestone — **without** claiming production readiness.

---

*End of B6 plan — implementation deliberately omitted.*
