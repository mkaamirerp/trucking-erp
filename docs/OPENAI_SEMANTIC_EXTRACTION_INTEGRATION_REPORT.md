# OpenAI semantic extraction layer — grounded integration report

**Status:** Report-first. **Connectivity-only** pieces are implemented (`Settings.openai_api_key`, `app/scripts/openai_smoke.py`, tenant-admin `POST /api/v1/load-lab/openai-smoke`). **Semantic extraction** (schema mapping in the parse pipeline) is **not** implemented here.

**Audience:** Engineers wiring OpenAI **after** text acquisition and **before** (or alongside) deterministic validation, aligned with `docs/PDF_LOAD_PIPELINE.md` and `docs/LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md`.

---

## 1. Best backend integration point (future PDF pipeline)

### Canonical pipeline position

Per `docs/PDF_LOAD_PIPELINE.md`, OpenAI is the **primary semantic mapping** step: **after** the **normalized document package** exists and **after** (or in tight coupling with) **classification** and **relevance** gates, and **before** deterministic validation and confidence/contradiction gates.

Conceptually:

`… → normalized package → [classification / relevance] → **AI schema mapping** → deterministic validation → gates → apply/review …`

### Concrete code anchors in *this* repo (today)

| Location | Role today | Future OpenAI role |
|----------|------------|-------------------|
| `app/services/load_document_parse.py` | Regex + PDF text → `LoadDocumentParseResponse` shape | Remains a **fallback / feature source** or pre-processor; **not** the final semantic owner if OpenAI is primary. |
| `POST /api/v1/loads/parse-document` (`app/routers/loads.py`) | Ephemeral workspace hydration | **Avoid** turning this into the default OpenAI path without an explicit product decision — it is user-facing load workspace and has no persisted run/audit model. |
| `app/services/load_lab.py` → `ingest_pdf_and_run_pipeline` | Persists runs, normalized package, versions; regex-only `mapped` today | **Best first integration point:** insert an **optional** “semantic map” step after digital text exists and `normalized_package` is built, **only inside Load Lab**, until quality and ops sign off. |
| `load_lab_extraction_runs` (tenant DB) | Already has `model_name`, `prompt_version`, `ai_model_output`, `field_evidence`, etc. | Store OpenAI **output + metadata** here; keep **main load rows** untouched until explicit promote (already the Lab contract). |

**Recommendation:** Treat **`app/services/load_lab.py`** (or a sibling module it calls, e.g. `app/services/load_lab_openai_map.py`) as the **first** production code location that invokes OpenAI. Optionally extract a shared **`app/services/pdf_semantic_map.py`** later if email intake or other routes need the same primitive **without** duplicating HTTP client and prompt/schema versioning.

**Do not** wire OpenAI into `POST /loads/parse-document` as the default until: persisted runs, versioning, audit, and guardrails match what Load Lab already encodes.

---

## 2. Where the API key should be read (this project’s actual runtime pattern)

### Runtime facts (grounded)

1. **Container entry:** `docker-compose.yml` runs the API with `command: ["/bin/sh", "-lc", "/app/scripts/start_api_with_ssm.sh"]`.
2. **Secrets file:** `scripts/start_api_with_ssm.sh` fetches SSM parameters under `/truckerp/prod/platform/` and `/truckerp/prod/shared/`, writes **`/run/secrets/truckerp.env`**, validates **required** vars, then starts uvicorn with `--env-file` pointing at that file (see script and `docs/secrets.md`).
3. **Application settings:** `app/core/config.py` uses **Pydantic `BaseSettings`** with `settings = Settings()` — fields map from **process environment** (which uvicorn populates from the env file). Optional third-party secrets follow the same pattern as e.g. `google_client_secret`, `microsoft_client_secret` (nullable `str | None`).

### Where `OPENAI_API_KEY` should live

| Environment | Recommended location | Notes |
|-------------|---------------------|--------|
| **Deployed (this repo’s prod pattern)** | AWS SSM **SecureString**, under `/truckerp/prod/shared/` *or* `/truckerp/prod/platform/` | `start_api_with_ssm.sh` merges both trees into one file. The **parameter’s last path segment** becomes the env var name in `truckerp.env` (see `docs/secrets.md` — “Adding a New Secret”). Use a parameter whose exported name is exactly **`OPENAI_API_KEY`** so `Settings` can bind it without adapters. **Do not** put the key in `docker-compose*.yml` (workspace rules). |
| **Local / dev container** | Same mechanism if using SSM-backed dev; **or** inject via host/env only for ad-hoc experiments **without** committing secrets | If the process is started **without** the SSM script, any `export OPENAI_API_KEY=...` before `uvicorn` still feeds `BaseSettings` — but that is **not** the standard server path documented for TruckERP prod. |

### Settings binding (recommended when you implement)

Add to `app/core/config.py` (illustrative — **not implemented in this report**):

- `openai_api_key: str | None = None` (or `Field(None, validation_alias="OPENAI_API_KEY")` if naming differs).
- Optionally: `openai_organization_id`, `openai_default_model`, timeouts — keep **optional** so missing config never breaks app boot.

**Important:** `start_api_with_ssm.sh` only **fails closed** on a fixed list (e.g. `DATABASE_URL`, `POSTGRES_PASSWORD`, …). **`OPENAI_API_KEY` must remain optional** so the API starts even if OpenAI is not configured yet.

---

## 3. Smallest safe test call path (connectivity only, no parsing integration)

Goal: prove **network + credentials + SDK** from the **same runtime** as production (inside `truckerp-api`, with `/run/secrets/truckerp.env` loaded).

### Recommended minimal approaches (in order of safety)

1. **One-off container command (no new routes)**  
   ```bash
   docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && python - << "PY"
   import os
   from openai import OpenAI
   assert os.environ.get("OPENAI_API_KEY"), "OPENAI_API_KEY missing"
   c = OpenAI()
   m = c.models.list()
   print("ok", getattr(m, "data", m) and "first model id", (m.data[0].id if getattr(m, "data", None) else "?"))
   PY'
   ```  
   Adjust to the **installed** client API (`openai` package version) if `models.list` differs. This touches **no** TruckERP routes and **no** tenant data.

2. **Tiny internal script** (e.g. `python -m app.scripts.openai_smoke`)  
   Same env sourcing pattern as `app/scripts/create_proof_token.py` (documented: load `/run/secrets/truckerp.env` inside container). Keeps smoke tests repeatable and grep-able in ops docs.

3. **Optional future HTTP probe** (only if you need UI/ops button)  
   e.g. `POST /api/v1/load-lab/openai-smoke` **admin-gated**, returns only `{ "ok": true }` / error class — **not** wired to PDF parsing. This is optional; (1)–(2) are smaller blast radius.

### What *not* to do for “connectivity only”

- Do not call OpenAI from **`GET /health`** or any path every dependency uses for liveness (risk of rate limits / latency / false unhealthy).
- Do not log request headers or full env dumps (key leakage).

---

## 4. First non-production-safe experiment path

**Use Load Lab only** (`/loads/lab` UI, `app/routers/load_lab.py`, `app/services/load_lab.py`):

- Isolated **tenant** persistence (`load_lab_extraction_runs` / `load_lab_promote_audits`).
- **No** default write to operational loads without promote.
- Already carries **version pins** (`parser_version`, `schema_version`, `prompt_version`, `model_name`, …) suitable for OpenAI rollout tracking.

**Avoid** experimenting first on `POST /loads/parse-document` or email intake auto-hydration — those paths lack the same persisted audit spine and are higher blast radius for dispatch/settlement/payroll data if mis-applied.

---

## 5. Proposed service/module layout (when implementation starts)

| Piece | Suggested location | Responsibility |
|-------|--------------------|------------------|
| Client factory / thin wrapper | `app/services/openai_client.py` or `app/integrations/openai/client.py` | Build `OpenAI()` (or async client) from `settings.openai_api_key`; shared timeouts; **no** business logic. |
| Semantic map primitive | `app/services/load_lab_semantic_map.py` (name illustrative) | Input: normalized package + schema version; output: JSON + usage metadata; **no** DB session concerns if avoidable. |
| Orchestration | `app/services/load_lab.py` | Branch: if key present and feature enabled → call mapper; else existing regex path; always persist `model_name` / `prompt_version` / `ai_model_output` consistently. |
| HTTP surface | `app/routers/load_lab.py` | Any “smoke” or “test map” routes stay here or under `dev_tools` with strict gating — not under `loads` core CRUD. |

This keeps **OpenAI** behind a **single** service boundary for timeouts, retries, and redaction policy.

---

## 6. Schema-driven extraction contract boundary

- **Upstream of OpenAI:** `normalized_package` (and optional OCR-enriched fields) — already aligned with `docs/PDF_LOAD_PIPELINE.md` stage 6.
- **Contract:** Pydantic models representing **TruckERP-owned** output — today `LoadDocumentParseResponse` is a useful **interim** target; long term the design doc calls for a **canonical load JSON** that may be a strict subset/superset of workspace parse. The **boundary** is: **OpenAI returns JSON that validates against a pinned Pydantic schema / JSON Schema** (`schema_version` on the run row).
- **Downstream:** Deterministic validation + gates (stops ordering, money rules, etc.) — **must not** trust model output without this step (`docs/PDF_LOAD_PIPELINE.md` stage 10).

Version **`prompt_version`** and **`schema_version`** on each run (Load Lab already has columns) are mandatory for regression and audit.

---

## 7. Logging and audit for OpenAI calls

### Must never log

- API keys, `Authorization` headers, raw env dumps.

### Should log / persist (tenant-safe, debuggable)

- **Tenant id**, **run id** (Load Lab), **route** (`source_route` / endpoint).
- **Model id**, **prompt_version**, **schema_version**, request **timeout** / retry count.
- **Outcome:** success / HTTP 4xx / 5xx / timeout; **not** full raw PDF bytes in logs.
- **Token usage** when returned by API (`prompt_tokens`, `completion_tokens`) — store on run row or in `context_json` of `audit_events`, not in generic app logs if logs are aggregated insecurely.

### Central audit spine

Use existing `app/services/audit_events.write_audit_event` with e.g. `module="load_lab"`, `entity_type="load_lab_run"`, `entity_id=str(run_id)`, `action` in (`openai_map_started`, `openai_map_completed`, `openai_map_failed`) and **`context_json`** holding model + latency + error class (not user document text by default).

Load Lab tables already support **`ai_model_output`** and versioning fields — use them as the **authoritative** technical record per run; audit_events for **cross-module** operator visibility.

---

## 8. Cost, rate limits, and errors (basics)

| Topic | Guidance |
|-------|----------|
| **Cost** | Cap input size (already truncate large `raw_full_text` in Lab); prefer **small** smoke payloads; use the **cheapest** model acceptable for structured JSON tests; log token usage per run. |
| **Rate limits** | Exponential backoff on **429** / `rate_limit_exceeded`; bounded retries; surface **retry_after** to operator in Lab UI if exposed. |
| **Timeouts** | Short HTTP timeouts (e.g. 30–60s) for map calls; distinguish timeout vs validation failure in run status / `pipeline_error`. |
| **Errors** | Map OpenAI errors to **typed** outcomes (`failed` vs `review_required`) without crashing the worker; **never** let an OpenAI exception bubble out of Load Lab upload in a way that breaks unrelated routes. |

---

## 9. Guardrails — missing key or API failure must not break normal flows

1. **Startup:** Do **not** add `OPENAI_API_KEY` to `required_vars` in `scripts/start_api_with_ssm.sh`. API must boot with key absent.
2. **Settings:** Nullable key; code paths default to **regex-only** or **skip AI** when unset.
3. **Scope:** Ship OpenAI first **only** behind Load Lab (or feature flag + admin role), not `POST /loads/parse-document` default.
4. **Timeouts / circuit breaker:** Optional global “disable OpenAI for N minutes” after repeated failures — ops preference; not required day one.
5. **Promote:** Keep current rule: **no promote** from runs that did not reach `validated` / `review_required`; if OpenAI fails, run should end in **`failed`** or **`review_required`** with clear `pipeline_error`, not partial promote.

---

## 10. Checklist — connectivity vs extraction pipeline

**Connectivity (partially done in repo):**

- [ ] SSM parameter exists and renders as `OPENAI_API_KEY` in `/run/secrets/truckerp.env` (verify with `docker exec` + `grep` pattern that **does not** print the value in runbooks).
- [x] `Settings.openai_api_key` in `app/core/config.py` — optional; API starts if unset.
- [x] Script: `python -m app.scripts.openai_smoke` (see module docstring; uses `httpx`, no OpenAI SDK dependency).
- [x] Optional HTTP: `POST /api/v1/load-lab/openai-smoke` — **tenant admin only**; returns JSON only (no key); same `GET https://api.openai.com/v1/models` probe.

**Extraction pipeline (still open before “AI extracted” in product):**

- [ ] Design alignment: `PDF_LOAD_PIPELINE.md` stage 9 + `LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md` versioning + evidence in run rows.
- [ ] Audit + run persistence updated for **model** / **tokens** / **error class** on real map calls.
- [ ] Deterministic validation and gates on model output before promote.

---

## References (in-repo)

- `scripts/start_api_with_ssm.sh` — SSM → `/run/secrets/truckerp.env` → uvicorn `--env-file`
- `docs/secrets.md` — secret flow, adding parameters, `db_run.sh` / container exec patterns
- `app/core/config.py` — `BaseSettings` / optional integration secrets pattern
- `docs/PDF_LOAD_PIPELINE.md` — where AI mapping sits in the target pipeline
- `docs/LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md` — isolated surface, audit, promote rules
- `app/services/load_lab.py`, `app/routers/load_lab.py` — current Lab orchestration and API prefix `/api/v1/load-lab`
- `app/scripts/openai_smoke.py` — CLI connectivity smoke
