## Correction-learning memory (concept)

**Important clarification:** We are **not** saying one PDF correction should immediately teach the system a permanent rule.

We need a **maturing learning layer**. AI may repeat the same parsing mistake forever (especially when broker names and document labels are confusing). Therefore TruckERP cannot rely on AI “memory” or prompt examples alone.

### Required concept
TruckERP needs its own **correction-learning memory** outside the AI model.

The system should:
- **Save what AI/parser selected.**
- **Save what dispatch/admin changed** when saving the load (human override).
- **Save later corrections too**, because the first human correction may also be wrong.
- **Watch repeated human behavior over time.**
- **Build broker-specific learned patterns only after repeated evidence.**
- **Use learned patterns as deterministic guardrails/suggestions** before trusting AI output.

This is:
- **Not** “manual-only mapping”
- **Not** one-correction learning
- **Yes** correction-history-based mature learning
- AI remains replaceable; learned rules live in **TruckERP database**

---

## Learning maturity model (state machine)

The learning layer tracks correction history and moves a potential rule through maturity states.

### States
- **observation**
  - Record the delta between AI output and the human-saved value.
  - No new behavior is applied.

- **pattern_detected**
  - Repeated similar corrections are observed for the **same broker** and **same field/label/value-type** pattern.
  - Still no auto-apply; the system only marks a candidate rule as emerging.

- **suggestion**
  - UI can suggest the learned mapping (“We usually demote Freight Bill # for this broker”).
  - Dispatch/admin can accept/ignore; no silent changes.

- **guarded_auto_apply**
  - After threshold and/or admin approval, the parser can deterministically apply/demote automatically.
  - Still emits review flags and can be overridden.

- **disputed**
  - If later human corrections contradict an active rule, reduce confidence or mark as disputed.
  - Disputed rules should revert to suggestion/review until stability returns.

### Critical safety rule
The learning layer must **keep tracking corrections even after a rule becomes active**.

If dispatch keeps changing the active rule result:
- the rule loses confidence
- may become **disputed**
- may be disabled or require re-approval

---

## What gets recorded (minimal required events)

For each “save” action (and for later edits), record:
- **run_id / document_id context** (Load Lab run or workspace load)
- **broker identity context** (as known at the time: broker_id, broker_name_snapshot, or grounded broker reference)
- **field name** (e.g. `broker_load_reference`)
- **AI value** (what the model produced)
- **pre-guardrail value** (optional) and **post-guardrail value** (if guardrails ran)
- **human final value** (saved)
- **who/when** (actor + timestamp)
- **reason metadata** where possible (label matched, extraction evidence, UI interaction source)

This enables:
- auditability (“why did this value change?”)
- longitudinal learning (“what does dispatch keep doing?”)
- safe maturity gating (“is this pattern stable?”)

---

## Example: demoting Freight Bill # for Landstar

### Scenario
AI repeatedly picks **“Freight Bill #”** as `broker_load_reference` for **Landstar Transportation Logistics**.
Dispatch repeatedly removes/changes it.

### What the system learns (after repeated evidence)
For broker **Landstar Transportation Logistics**, raw label **“Freight Bill #”** should **not** automatically become `broker_load_reference`.

### Future behavior
If AI picks it again:
- deterministic guardrail **demotes it** to a secondary reference
- leaves `broker_load_reference` empty unless a higher-confidence load/order/tender reference exists
- logs another observation (continues learning)

---

## Opposite example: promoting Freight Bill # for Landstar

### Scenario
AI repeatedly ignores “Freight Bill #”.
Dispatch repeatedly promotes that same label/value as the actual load reference.

### What the system learns (after repeated evidence)
For Landstar, “Freight Bill #” is likely `broker_load_reference`.

### Future behavior
System:
- suggests it in the UI (suggestion state)
- later can auto-apply only after maturity threshold/admin approval (guarded_auto_apply)
- continues monitoring; contradictions reduce confidence and may dispute the rule

