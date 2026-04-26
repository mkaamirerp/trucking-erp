# Load Lab v3 — confidence + contradiction review (implementation report)

**Date:** 2026-04-20  
**Scope:** Lab only — read-only UI, no promote, no operational writes, no OCR, no inbox.

## Goal

Make semantic **candidates** reviewable using **simple, transparent heuristics** over the pair `(normalized_package.raw_full_text, parse_response)` before any promote flow exists.

## What shipped

### Persistence (tenant DB)

| Field | Purpose |
|--------|---------|
| `lab_confidence` (JSONB) | Document-level + per-group confidence (`unknown` / `low` / `medium` / `high`) with short `reasons` lists |
| `contradictions` (JSONB, existing column) | Ordered list of `{ id, severity, detail }` flags |
| `lab_review_status` (VARCHAR) | `not_applicable` \| `candidate_ok` \| `review_required` \| `blocked` |
| `lab_review_summary` (TEXT) | One-line operator summary (duplicated lightly into `warnings` as `[lab_review] …` when applicable) |

Migration: `alembic_tenant/versions/k9j8h7g6f5e4_load_lab_v3_review_columns.py` (revises `m8n7o6p5q4r3`).

### Backend

| Piece | Location |
|--------|-----------|
| Review engine | `app/services/load_lab_review.py` — `REVIEW_ENGINE_VERSION = "load_lab_review_heuristic_v1"` |
| Pure builder | `build_lab_review_payload(raw_text, parsed)` — testable without DB |
| Run mutation | `attach_lab_review_to_run`, `clear_lab_review_on_run`, `clear_lab_review_if_no_candidate`, `merge_lab_review_warnings`, `recompute_lab_review_for_run` |
| Semantic integration | `app/services/load_lab_semantic.py` — on success calls `attach_lab_review_to_run` + `merge_lab_review_warnings`; whenever `parse_response` becomes `None`, calls `clear_lab_review_if_no_candidate` |
| API | `POST /api/v1/load-lab/runs/{run_id}/lab-review` — recompute v3 from current candidate (no OpenAI) |
| Model | `app/models/load_lab.py` — new mapped columns |
| API schema | `app/schemas/load_lab.py` — `LoadLabRunOut` exposes `lab_confidence`, `contradictions`, `lab_review_status`, `lab_review_summary` |

### Confidence (grounded, coarse)

- **Per group** (`broker_identity`, `broker_contact`, `references`, `equipment`, `money`, `stops`, `customs`): mostly “is extracted text plausibly present in `raw_full_text`?” via substring / digit-sequence checks. Absent fields → **`unknown`**. Mismatch → **`low`**. Substring hit → **`medium`**. No numeric “confidence %”.
- **Document**: aggregates groups — prefers **`unknown`** / **`low`** when any group is weak.

### Contradictions (examples)

| `id` | Typical severity |
|------|-------------------|
| `multiple_money_amounts_in_text` | warning |
| `sparse_reference_capture` | info |
| `stop_sequence_irregular` | warning |
| `pickup_after_delivery` | warning |
| `single_stop_only` | info |
| `broker_mc_mismatch` | error |
| `broker_dot_mismatch` | error |
| `rate_and_customer_rate_diverge` | warning |

### Review status rules

- **`blocked`**: any contradiction with `severity == "error"`, or invalid `parse_response` when recomputing review.
- **`review_required`**: any `warning`, or populated data in a group marked **`low`**, or document-level **`low`**.
- **`candidate_ok`**: none of the above; **`info`**-only flags do not force review.
- **`not_applicable`**: no candidate JSON (`parse_response` null) after `clear_lab_review_on_run`.

### Frontend

- `apps/web/src/api.ts` — extended `LoadLabRun`, `postLoadLabRecomputeReview`.
- `apps/web/src/pages/LoadLabPage.tsx` — **Lab review state** banner, **confidence by group**, **contradiction list**, **Recompute lab review** when a candidate exists; run list shows `review:…` when present.

## Operator commands (this host)

```bash
/home/admin/trucking_erp/scripts/reload_api.sh
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && bash scripts/tenant_upgrade_head.sh'
/home/admin/trucking_erp/scripts/reload_nginx_web.sh
```

Verification:

```bash
docker exec truckerp-api grep -n "lab-review" /app/app/routers/load_lab.py
docker compose -f /home/admin/trucking_erp/docker-compose.yml exec truckerp-nginx sh -lc 'grep -l "lab-review" /usr/share/nginx/html/assets/*.js | head -1'
```

## Grounding note

This report matches the repository implementation at authoring time; use the commands above to confirm the **running** API and nginx bundle on a given host.
