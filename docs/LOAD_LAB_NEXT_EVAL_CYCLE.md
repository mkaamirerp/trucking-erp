# Load Lab — Next Evaluation Cycle (10–20 PDFs)

**Goal:** Expand beyond the frozen 6‑PDF baseline without regressions.

## Non‑regression lock

Every change in the next cycle must keep passing:

- `docs/LOAD_LAB_BASELINE_6PDF.md` (fixtures + harness output expectations)

If it breaks, treat it as a regression until proven otherwise.

## Build the next test set (10–20 harder PDFs)

Prioritize:

- **3–6 stop documents**
- **Messy tables** (multi-column, wrapped text)
- **Mixed appointment formats** (FCFS, windows, “by 14:00”, “0800–1600”, etc.)
- **Multiple references per stop** (PU#, delivery #, PO#, BOL, PRO, customer ref)
- **More broker families** (not only TQL/RXO/Hub Group/BM2/Landstar patterns)
- **Weak/scanned PDFs** (for later OCR branch testing; not required until OCR branch work begins)

## Keep the next cycle focused (priority order)

1. **Harder stop extraction**
2. **Per-stop reference numbers**
3. **Per-stop contact fields**
4. **Broader broker grounding coverage**
5. **OCR branch** only when ready

## Keep the fix-type distinction explicit (lock)

When adding fixes, label them explicitly as one of:

- **Normalization fix** (presentation consistency; not parsing correctness)
- **Semantic extraction fix** (model prompt/schema/evidence packet changes)
- **Deterministic post‑AI repair** (contract safety rails / guardrails)

