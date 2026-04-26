## ML / Deep Learning Architecture for TruckERP (recommended path)

### Key principle
Do **not** train one big ML model immediately.

Build this in **3 layers**:

---

## Layer 1 — Deterministic extraction + AI parser

Current Load Lab direction:

PDF text/OCR → candidates → AI semantic parse → guardrails → diagnostics

This layer is responsible for:
- extraction
- schema-constrained structured output
- deterministic safety checks (guardrails)
- diagnostics and review flags

---

## Layer 2 — TruckERP learning memory (correction-learning engine)

TruckERP needs its own **correction-learning memory** outside the AI model.

Your own database watches:
- AI picked this → dispatcher changed this → final saved value → repeated pattern

Why this matters:
- The problem is not just “read PDF”
- The problem is: **“For this broker, what does this label mean in real dispatch behavior?”**

No outside ML model knows that. TruckERP must learn it from your users.

### Recommendation for the ML engine right now
For now: use your **own learning database**, not a trained ML model.

The first “ML” should actually be a **correction-learning engine** inside TruckERP.

It watches sequences like:

- AI extracted:
  - `broker_load_reference = Freight Bill # 9459258`

- Dispatcher saved:
  - `broker_load_reference = empty` (or different number, or same number)

- Later dispatcher changes it again:
  - `broker_load_reference = 9459258` (or something else)

Then TruckERP builds maturity:

**observation → pattern detected → suggestion → guarded auto-apply → disputed/disabled**

This gives “machine learning behavior” without blindly trusting a model.

### Critical rule
AI can suggest.
TruckERP learned rules decide whether to **trust / demote / promote / send to review**.

The learning layer must keep tracking corrections even after a rule becomes active.
If dispatch keeps changing the active rule result, the rule loses confidence and becomes disputed/disabled.

---

## Layer 3 — ML later, only when enough correction data exists

Train or fine-tune a model only after TruckERP has enough labeled examples.

This is safest because it avoids the trap:

AI keeps making the same mistake → we argue with prompts forever

and replaces it with:

AI makes mistake → dispatcher corrects → TruckERP remembers → future guardrail blocks repeated mistake

---

## OCR / managed extraction engines (later, as supporting tools)

### Use case
Use these for OCR / layout / “custom extraction backup” later, but they should **not** replace TruckERP’s correction-learning DB.

### Azure AI Document Intelligence
- Custom neural document models for structured / semi-structured / unstructured documents
- Custom extraction can train from labeled docs; Microsoft docs say you can start with as few as ~5 examples for the same form type
- Useful later for broker-specific templates

### AWS Textract (Custom Queries / Adapters)
- Lets you customize output from pretrained queries and improve results for business-specific documents
- Fits AWS direction
- Still won’t know operational meaning unless TruckERP tracks corrections

### Google Document AI
- Custom Extractor / fine-tuning from a small set of docs
- Caution: Google’s older built-in HITL feature is deprecated/unavailable after Jan 16, 2025
- Human correction workflow must live in TruckERP, not depend on a vendor HITL product

### Docling / open source (preprocessing)
- Strong for document conversion/layout prep (reading order, tables, OCR, etc.)
- Useful to produce cleaner structured text/layout chunks before sending to the AI parser
- Still not the “business memory” layer

---

## What to tell “Mini Architect” (instruction)

Do not build a standalone ML model first.

Build a TruckERP **correction-learning engine** first.

The engine must store:
- parser outputs
- dispatcher corrections
- final saved values
- later edits
- broker identity
- raw PDF label/value
- source text context
- confidence
- parser version

The system matures learned broker/reference rules over time from repeated human behavior.

AI remains the extractor.
TruckERP database becomes the memory.
Deterministic guardrails use the learned memory to correct or challenge AI next time.

---

## Correct TruckERP design (data model sketch)

### 1) Save every parser decision (durable snapshot)

Every Load Lab run should save a durable parse snapshot:

`parse_observation`
- tenant_id
- load_lab_run_id
- source_pdf_file_id
- parser_version
- semantic_mode
- detected_broker_candidates
- selected_broker_name
- selected_broker_id
- selected_global_broker_id
- selected_broker_load_reference
- all_reference_candidates
- accepted_references
- rejected_references
- broker_confidence_matrix
- diagnostics_json
- created_at

This is the “what AI believed at the time” record.

### 2) Save every human correction

When dispatch/admin saves or changes fields:

`correction_event`
- tenant_id
- observation_id
- load_id
- actor_user_id
- corrected_field
- ai_value
- previous_human_value
- new_human_value
- correction_type
- broker_name_snapshot
- broker_id
- global_broker_id
- raw_pdf_label
- raw_pdf_value
- source_context_json
- created_at

This matters because:
- the first correction may be wrong
- a later correction may be better

### 3) Broker-specific learning table (maturity tracking)

`broker_reference_learning_patterns`
- tenant_id
- broker_id
- global_broker_id
- broker_name_normalized
- raw_label_normalized
- observed_value_pattern
- proposed_reference_kind
- promotes_to_primary
- positive_count
- negative_count
- correction_count
- contradiction_count
- confidence_score
- maturity_status
  - observing
  - pattern_detected
  - suggestion
  - guarded_auto_apply
  - disputed
  - disabled
- last_observed_at

#### Example (demote Freight Bill #)
Broker: Landstar Transportation Logistics  
Raw label: Freight Bill #  
Pattern A:
- promotes_to_primary = false
- negative_count = 9
- maturity_status = guarded_auto_apply

Meaning:
AI keeps picking Freight Bill # as main reference; dispatch keeps demoting/removing it.
Next time, TruckERP should override AI and keep it secondary / leave primary empty.

#### Opposite example (promote Freight Bill #)
Broker: Landstar Transportation Logistics  
Raw label: Freight Bill #  
Pattern B:
- promotes_to_primary = true
- positive_count = 11
- maturity_status = suggestion

Meaning:
Dispatch keeps promoting Freight Bill # as main reference.
Next time, TruckERP should suggest it (and only auto-apply after maturity/approval).

---

## Final recommendation

Primary (now): **PostgreSQL + deterministic scoring + correction events**
- This is the real engine for V1, because the learning is business behavior.

Secondary: **existing AI parser**
- Keep using AI to extract candidates and structured JSON, but do not let it be the memory.

Optional OCR/layout: **Docling first, Textract later**
- Improve OCR/layout only after correction-learning loop exists.

Later custom model: **Azure Document Intelligence** or **AWS Textract adapters**
- Train only after enough labeled correction data exists from real TruckERP usage.

