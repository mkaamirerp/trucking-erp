# Load Parser

Purpose:
Rate confirmation / BOL commercial document parsing, Load Lab, AI extraction, parser contracts, and OCR/digital-PDF pipeline.

Status:
Documentation organization scaffold only.

Current files:
Existing files have not yet been moved or reconciled. This folder already holds parser transport/execution designs; top-level Rate Confirmation / Load Lab docs remain at current paths until a move pass.

Future structure:
This folder will contain the module MASTER, TODO, verification evidence, contracts, fixtures, or lab docs where appropriate.

---

# Document Parser transport / execution designs

This folder contains designs about **how parser work is executed or transported**, not alternate semantic parsers.

## Architecture lock

TruckERP has **one shared Document Parser engine/pipeline with attached document profiles**. Rate Confirmation v2 is the first shipped profile; Fuel, Toll, and future document types attach their own profile/rules/schema/context to the same parser boundary.

### Digital rate confirmation — OpenAI semantic input (2026-10-06)

| PDF kind | Authoritative semantic evidence to OpenAI | Local extracted text |
|---|---|---|
| **Digital** (embedded text + PDF bytes attached) | Original PDF file + `field_rules` + `tenant_identity_exclusion` + output schema | May remain as `raw_text` / mechanical validation; **must not** be duplicated into `document.pages` in the AI user message |
| **Scanned image-only** | OCR text in `document.pages` + rules + schema (no PDF attachment) | Same as semantic source today |
| **Mixed** digital/scanned | Blocked (unchanged) | — |

**Why:** Duplicate evidence (PDF + flattened page text) can destroy layout/ownership (TQL PO **34307972**: JD FACTORS decoy vs Charlotte pickup). Prior frozen baseline with duplicate evidence on `gpt-4o-mini`: Charlotte **8/10**, JD_FACTORS pickup **2/10**.

**Regression case:** `/TQLRC.pdf` SHA256 `05849ad1a1256eff16b7cc117d0b694c55e1b599d9ad6e0da3ba36a2ee8c8b89`. JD FACTORS (Mississauga) must never be pickup or delivery.

Do not re-label the parser module **GOLD** until architecture + TQL batch results are reviewed.

Current semantic architecture lives in:

- `../TruckERP_Shared_Document_Parsing_Architecture.md`
- `../TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`

A job/queue/background-worker design may change **when and where** the shared parser runs. It must not create a second parser implementation or redefine profile semantics.

## Re-parse — owner rules, locked 2026-10-28

Re-parse reads a PDF again on a load that is already chosen and shows what differs. The locked rules are in [`.cursor/rules/owner-product-rules.mdc`](../../.cursor/rules/owner-product-rules.mdc) under **RE-PARSE (owner rules, locked 2026-10-28)**.

## Dispatcher verification and approval — OWNER-LOCKED TODO (2026-10-28)

The PDF parser and comparison model **assist** in interpreting RC documents; they do not approve or silently modify dispatcher-verified commercial values. The logged-in, authorized dispatcher reviews the RC and expressly approves the final form before Create Load or intentional revised-RC acceptance. The system must save precisely those values and retain a trustworthy user-attributed approval/change audit. This requirement is **not yet implemented**.

**Canonical work item (including exact mandatory acknowledgement text and acceptance checklist):** [TruckERP TODO — Load / Rate Confirmation dispatcher verification acknowledgement](../../TODO.md#load--rate-confirmation--dispatcher-verification-acknowledgement-owner-locked-todo-2026-10-28).

This is a responsibility and audit requirement, not a change to the existing PDF extraction handoff, original Parse gates, or the Re-parse semantic-comparison contract.

## Current design note

- `ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md` — **design only / not implemented**. Proposes moving the Load Page Rate Confirmation parse request from synchronous HTTP execution to a durable async job while preserving the same parser/profile result and workspace hydration contract.
