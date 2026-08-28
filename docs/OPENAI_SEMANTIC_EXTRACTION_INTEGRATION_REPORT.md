# OpenAI semantic extraction layer — grounded integration report

**Status:** **SUPERSEDED / HISTORICAL IMPLEMENTATION REPORT**  
**Current parser truth:** Rate Confirmation semantic extraction is now implemented on the product `POST /api/v1/loads/parse-document` path through Rate Confirmation v2 (`load_document_parse_rate_con`) with tenant identity exclusion + frozen field rules + page-separated text → OpenAI → mechanical validation. See `TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md` and `TruckERP_Shared_Document_Parsing_Architecture.md`.  
**Historical value:** This report is retained for the original connectivity, SSM, smoke-test, rollout, and Load Lab reasoning. Statements below such as “semantic extraction is not implemented,” “use Load Lab only,” or “do not wire OpenAI into `/loads/parse-document`” describe the **pre-cutover state** and must not be used as current implementation guidance.

**Audience:** Engineers researching the original OpenAI integration path and operational rationale. For current parser work, start from the parser design and shared parsing architecture docs instead.

---

## 1. Best backend integration point (historical future-PDF-pipeline recommendation)

### Canonical pipeline position

Per `docs/PDF_LOAD_PIPELINE.md`, OpenAI is the **primary semantic mapping** step: **after** the **normalized document package** exists and **after** (or in tight coupling with) **classification** and **relevance** gates, and **before** deterministic validation and confidence/contradiction gates.

Conceptually:

`… → normalized package → [classification / relevance] → **AI schema mapping** → deterministic validation → gates → apply/review …`

### Concrete code anchors at the time of this report

| Location | Role at report time | Historical proposed OpenAI role |
|----------|---------------------|---------------------------------|
| `app/services/load_document_parse.py` | Regex + PDF text → `LoadDocumentParseResponse` shape | Remain a fallback / feature source or pre-processor; not final semantic owner if OpenAI becomes primary. |
| `POST /api/v1/loads/parse-document` (`app/routers/loads.py`) | Ephemeral workspace hydration | Report originally recommended avoiding default OpenAI here until an explicit product decision. **This recommendation is superseded:** Rate Confirmation v2 is now intentionally wired here. |
| `app/services/load_lab.py` → `ingest_pdf_and_run_pipeline` | Persisted runs, normalized package, versions; regex-only mapping at the time | Original suggested first integration point for optional semantic mapping. |
| `load_lab_extraction_runs` | Persisted model/prompt/schema/evidence fields | Original proposed technical record for experiments. |

**Historical recommendation:** use Load Lab as the first experimentation surface and avoid product-path wiring until quality/ops sign-off. That rollout step has been superseded by the approved Rate Confirmation v2 cutover.

---

## 2. Where the API key should be read

### Runtime pattern recorded by this report

1. `docker-compose.yml` starts the API through `/app/scripts/start_api_with_ssm.sh`.
2. The startup script fetches SSM parameters under `/truckerp/prod/platform/` and `/truckerp/prod/shared/`, writes `/run/secrets/truckerp.env`, validates required variables, then starts uvicorn with that env file.
3. `app/core/config.py` uses Pydantic settings bound from process environment.

### Where `OPENAI_API_KEY` belongs

| Environment | Recommended location | Notes |
|-------------|---------------------|-------|
| Deployed | AWS SSM SecureString under the existing shared/platform secret flow | Parameter exports as `OPENAI_API_KEY`; do not put secrets in compose files. |
| Local/dev | Same SSM-backed mechanism when practical, or process env for ad-hoc experiments without committing secrets | Local env is not the standard prod secret path. |

The key should remain optional at application boot so a missing OpenAI credential does not make unrelated API startup fail.

---

## 3. Smallest safe connectivity test path

Goal: prove network + credentials from the same runtime without touching product parsing.

Historical safe options included:

1. one-off container command using the loaded secret env
2. `python -m app.scripts.openai_smoke`
3. admin-gated Load Lab smoke endpoint

Do not:

- call OpenAI from `GET /health`
- log auth headers or raw environment dumps

These connectivity rules remain useful even though the product semantic parser is now live.

---

## 4. Historical first experiment surface

At report time, Load Lab was recommended as the isolated first experiment surface because it had:

- tenant-scoped persistence
- no default operational Load mutation without promote
- version pins for parser/schema/prompt/model

The report explicitly recommended avoiding product `/loads/parse-document` during experimentation. That caution explains the rollout history but is **not current parser-routing guidance** after the Rate Confirmation v2 product decision.

---

## 5. Historical proposed service/module layout

| Piece | Suggested location at report time | Responsibility |
|-------|-----------------------------------|----------------|
| Client factory / thin wrapper | `app/services/openai_client.py` or integration package | Shared OpenAI transport/config only |
| Semantic map primitive | Load-Lab-specific semantic map module | normalized input → schema JSON |
| Orchestration | `app/services/load_lab.py` | feature branch / persistence |
| HTTP surface | Load Lab / dev tools | smoke or test-only endpoints |

Current Rate Confirmation v2 architecture supersedes this module-placement proposal for the product parser. Use the shared parsing architecture and actual production modules as current guidance.

---

## 6. Schema-driven extraction contract boundary

The durable part of this report remains valid:

- OpenAI output is TruckERP-owned schema-valid JSON.
- Model output must be validated before product use.
- prompt/schema versions matter for regression tracking where persisted run models use them.

For the current Rate Confirmation path, the concrete contract is documented in `TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`; do not infer current parser shape from this older report.

---

## 7. Logging and audit for OpenAI calls

### Must never log

- API keys
- `Authorization` headers
- raw env dumps

### Useful technical metadata

Where applicable and tenant-safe:

- tenant/run identifiers
- source route
- model id
- prompt/schema version where that surface persists versions
- timeout/retry/outcome/error class
- token usage if available and stored safely

Do not dump entire customer documents into generic application logs merely for debugging.

---

## 8. Cost, rate limits, and errors

| Topic | Guidance |
|-------|----------|
| **Cost** | Bound input sizes; use suitable models; record usage when useful. |
| **Rate limits** | Bounded retries/backoff for 429s. |
| **Timeouts** | Use finite timeouts and distinguish timeout from schema/validation failure. |
| **Errors** | Map failures to controlled outcomes rather than crashing unrelated flows. |

These remain generic integration guidance, not a substitute for the current Rate Confirmation implementation contract.

---

## 9. Guardrails from the original rollout

Durable guardrails:

1. `OPENAI_API_KEY` should not be a hard startup requirement for unrelated product boot.
2. Settings should keep integration secrets nullable where product behavior has a controlled missing-key path.
3. OpenAI failures must not expose secrets or corrupt unrelated product state.
4. Model output must pass TruckERP validation before hydration/use.

Superseded rollout-specific guardrail:

- “Ship OpenAI only behind Load Lab and never as `/loads/parse-document` default” — **superseded by the approved Rate Confirmation v2 cutover.**

---

## 10. Historical checklist

Connectivity work recorded by the report:

- optional OpenAI setting
- CLI smoke test
- optional admin smoke endpoint
- SSM/env guidance

The report’s extraction-pipeline checklist was written before semantic extraction shipped. Do not use unchecked boxes here to conclude that Rate Confirmation semantic extraction is still absent.

Current implementation verification belongs in:

- `TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`
- `TruckERP_Shared_Document_Parsing_Architecture.md`
- current Rate Confirmation parser tests

---

## References

Historical / operational references retained from the original report:

- `scripts/start_api_with_ssm.sh`
- `docs/secrets.md`
- `app/core/config.py`
- `docs/PDF_LOAD_PIPELINE.md`
- `docs/LOAD_LAB_AND_EXTRACTION_AUDIT_PLAN.md`
- `app/services/load_lab.py`
- `app/routers/load_lab.py`
- `app/scripts/openai_smoke.py`

Current parser references:

- `app/services/load_document_parse_rate_con.py`
- `app/services/load_parser_openai_handoff_v2.py`
- `app/services/load_parser_tenant_identity_exclusion.py`
- `app/services/load_parser_rate_con_field_rules.py`
- `app/services/load_parser_mechanical_validation.py`
- `app/services/load_parser_pdf_acquisition.py`
- `docs/TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`
- `docs/TruckERP_Shared_Document_Parsing_Architecture.md`
