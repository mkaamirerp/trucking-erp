# Load Lab — 6‑PDF Baseline (Frozen)

**Status:** Frozen reference baseline (do not regress)

**Frozen at:** 2026-04-23T20:04:03Z  
**Repo commit:** `40c03cff`

## Lock / Non‑regression rule

All future parser work **must continue to pass this baseline**. Do **not** reopen or “improve” these expectations unless a new change **breaks** the baseline and we are investigating the regression.

## What this baseline covers

- **Broker**: booking broker selection + guardrails + display normalization
- **References**: primary broker reference ranking + alternates preserved
- **Digital references (pre-OCR)**: structured `extracted.references[]` hydrated from normalized PDF text (label regexes + supplemental carrier patterns), with `parse_diagnostics` fields `reference_candidates`, `accepted_references`, `rejected_reference_candidates` (each with `rejection_reason` where applicable), `primary_reference_selection_reason`, and `reference_extraction_gap_analysis` (explains empty structured output when `numeric_candidates` still show `reference_like` tokens, e.g. JB Hunt–style headers). The 6-PDF harness prints per-run `reference_digital_snapshot` for baseline reporting before OCR.
- **Stops**: minimal stop correctness + appointment normalization checks
- **Harness**: mismatch categories + concrete diffs when failures occur

## Artifacts (saved)

- **Harness script**: `app/scripts/load_lab_eval_6pdf.py`
- **Final fixtures**: `docs/load_lab_eval_fixtures_demo6.json`
- **Final harness output (JSON)**: `docs/load_lab_baseline_6pdf_output.json`
- **Cleaner ledger (updated)**: `docs/LoadLabCleaner.md`

## How to run (container)

```bash
docker exec truckerp-api bash -lc \
 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && \
  python -m app.scripts.load_lab_eval_6pdf \
    --tenant-id 53 \
    --expected /app/docs/load_lab_eval_fixtures_demo6.json \
    --run-ids 18,17,15,12,11,10'
```

