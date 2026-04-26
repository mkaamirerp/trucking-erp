# Load Lab v2 — OpenAI structured extraction (implementation report)

**Date:** 2026-04-20  
**Scope:** Load Lab only — no operational load writes, no promote, no inbox, no OCR execution.

## Goal

For an existing persisted `load_lab_extraction_runs` row with usable normalized text (`status == text_extracted`), call OpenAI to produce a **candidate** TruckERP-shaped JSON (same geometry as workspace PDF parse: `LoadDocumentParseResponse`), validate it deterministically, and persist outcomes **on the run**.

## What shipped

### Backend

| Piece | Location |
|--------|-----------|
| Tenant migration (new columns) | `alembic_tenant/versions/m8n7o6p5q4r3_load_lab_semantic_columns.py` |
| SQLAlchemy model | `app/models/load_lab.py` — `semantic_model_name`, `semantic_prompt_version`, `semantic_schema_version`, `semantic_extract_status`, `semantic_validation_result` |
| Strict model-output contract | `app/schemas/load_lab_semantic.py` — `LoadLabSemanticModelOutput` (`document` + `extracted` + `extraction_warnings`) with `extra="forbid"` subclasses |
| Semantic service | `app/services/load_lab_semantic.py` |
| HTTP route | `POST /api/v1/load-lab/runs/{run_id}/semantic-extract?force=false` in `app/routers/load_lab.py` |
| API envelope | `LoadLabRunOut` extended in `app/schemas/load_lab.py` with `parse_response`, `ai_model_output`, and semantic fields |
| Config | `app/core/config.py` — `openai_extraction_model` (default `gpt-4o-mini`) |

### Persistence mapping

| Requirement | Where stored |
|-------------|----------------|
| Model name | `semantic_model_name` |
| Prompt version | `semantic_prompt_version` (`load_lab_semantic_v2`) |
| Schema version | `semantic_schema_version` (`load_lab_candidate_truckerjson_v1`) |
| Candidate JSON | `parse_response` (full `LoadDocumentParseResponse` dict, including `raw_text` from the stored normalized package) |
| Warnings / errors | `warnings` (semantic lines prefixed `[semantic]`), `pipeline_error` for short operator-facing summary on failure |
| Request outcome | `semantic_extract_status` (`success`, `openai_failed`, `validation_failed`, `skipped_*`, …) and `ai_model_output.outcome` |
| Deterministic validation | `semantic_validation_result` (`ok`, `issues`, `checks`; on some failures includes `candidate_preview` or `raw_model_json`) |
| Raw OpenAI envelope | `ai_model_output` (`usage`, `message_content` excerpt, `raw_response_excerpt`, meta) |

Upload-time pins (`parser_version`, `schema_version` = `normalized_package_v1`, `model_name` = `n/a`, etc.) are **unchanged** so hash/dedupe logic in `app/services/load_lab.py` stays stable.

### OpenAI call shape

- **Client:** `httpx.AsyncClient` (same dependency as smoke route — no `openai` SDK).  
- **Primary:** `response_format.type = json_schema` with `LoadLabSemanticModelOutput.model_json_schema()` and `strict: false`.  
- **Fallback:** On HTTP 400 mentioning `json_schema`, retry with `response_format: { "type": "json_object" }` and stricter user instructions (logged in `docs/LoadLabCleaner.md`).

### Deterministic validation

1. `LoadLabSemanticModelOutput.model_validate_json` on the model message.  
2. Assemble `LoadDocumentParseResponse` and `model_validate` again.  
3. `_deterministic_validate`: non-negative rates/miles/weight; `stop_type` ∈ {pickup, delivery, drop, other}.

### Isolation / failure behavior

- No writes to `loads` or related operational tables.  
- Missing `OPENAI_API_KEY`: run gets `semantic_extract_status=skipped_missing_key`, friendly `warnings`, no exception from the route.  
- OpenAI/validation failures: status + `semantic_validation_result` + `ai_model_output`; optional preservation of previous `parse_response` when `force=false` (see service).  
- **404** only if the run id does not exist for the tenant.

### Frontend

- `apps/web/src/api.ts` — `postLoadLabSemanticExtract`, extended `LoadLabRun` type.  
- `apps/web/src/pages/LoadLabPage.tsx` — when readability is `text_usable`, **Run OpenAI extraction** + optional force checkbox; panels for candidate JSON, validation JSON, OpenAI metadata, warnings.

## Optional request body

`force` is a **query parameter** (`?force=true`) rather than a JSON body so clients can POST without a body (matches existing Lab patterns).

`LoadLabSemanticExtractIn` remains in `app/schemas/load_lab.py` for documentation or future JSON bodies.

## Operator commands (this host)

```bash
# After code + migration file land in the image:
/home/admin/trucking_erp/scripts/reload_api.sh
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && bash scripts/tenant_upgrade_head.sh'
/home/admin/trucking_erp/scripts/reload_nginx_web.sh
```

Verification examples:

```bash
docker exec truckerp-api grep -n semantic-extract /app/app/routers/load_lab.py
docker compose -f /home/admin/trucking_erp/docker-compose.yml exec truckerp-nginx sh -lc 'grep -R "semantic-extract" /usr/share/nginx/html/assets/*.js 2>/dev/null | head -1'
```

## Grounding note

This report was written against the repository tree at implementation time; after deploy, use the container grep lines above to prove the **running** API/nginx bundle includes the route and UI bundle string.
