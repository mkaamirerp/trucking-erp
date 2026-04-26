"""Truckerjson (legacy) Load Lab: full `LoadParseExtractedFields` target + high-risk instruction overlay.

`docs/CRITICAL_EXTRACTION_CONTRACT_v1.1.json.md` is a **strict rules source** for *selected* high-risk
fields (dispatch-critical heuristics). It must **not** cause the model to output only “critical” fields;
the model must still populate every field the JSON schema allows for the full load-form / workspace
hydration shape (`LoadDocumentParseResponse.extracted`).

`critical_extraction_v11_prompt` embeds the same file as the *primary* contract for `critical_v1_1`.
Here we embed it only as an **overlay** alongside explicit “fill the full form” instructions.
"""

from __future__ import annotations

import json
from pathlib import Path

# --- Full-form target (must match `LoadParseExtractedFields` / workspace hydration) ----------------

_FULL_FORM_TARGET = """
PRIMARY TARGET — FULL LEGACY / TRUCKERJSON LOAD-FORM (do not shrink the output):
- You MUST extract the **complete** load-form payload allowed by the provided JSON schema: `document`,
  `extracted`, and `extraction_warnings`.
- `extracted` must **attempt** every field the schema supports (use null, 0, or [] only when truly absent
  or not applicable), including **all** of the following when present in the document:
  - `broker_name_snapshot`, `broker_contact_name_snapshot`, `broker_contact_phone_snapshot`,
    `broker_contact_email_snapshot`, `broker_load_reference`, `broker_mc_number_snapshot`,
    `broker_dot_number_snapshot`, `mode`, `equipment_type`, `trailer_type`, `trailer_size`, `commodity`,
    `estimated_weight`, `temperature_requirement`, `rate`, `customer_rate`, `miles`, `customs_broker_name`,
    `references[]`, `stops[]`.
- Each `stops[]` item must use the schema fields: `stop_type`, `sequence`, `facility_name`, `street`,
  `city`, `state_or_province`, `postal_code`, `country`, `reference_number`, `appointment_type`,
  `appointment_date` (YYYY-MM-DD or null), `appointment_time_text`, `notes`.
- **Stops** = physical **pickup / delivery** locations in **PDF order**; support **multiple** pickups and
  **multiple** deliveries. **0-based** `sequence` in order.
- **Do not** stop after “critical” fields. The next block is a **stricter rule set** for high-risk fields
  only; it does **not** mean other fields are optional to skip.

BROKER CONTACT / AGENT (normal extraction, not “critical only”):
- **Do** extract broker/agent/dispatch/load-rep **name**, **phone**, and **email** when clearly tied to
  the **booking broker** (broker contact blocks, agent lines, load rep, dispatch for this tender).
- **Do not** use **carrier** / **driver** / **factoring** / **remittance** / **payment** / **invoice-only**
  / shipper / receiver / generic document footers as the broker **agent** email or primary broker contact
  when a clearer broker-tender contact exists.
- **Do not** promote **paperwork/invoice** email to broker agent email unless it is **explicitly** the
  broker’s stated contact for this load (not a generic “send invoices here” that is not the load rep).
- Broker **office** main line may fill `broker_contact_phone_snapshot` only if there is no better
  **agent / load rep / dispatch** phone for this tender.
- Keep **secondary** labeled IDs in `references[]` (kind, value; label optional) when the schema allows;
  not every ID belongs in `broker_load_reference`.
"""

# --- High-risk fields: the overlay applies stricter “wrong blank > wrong fill” rules -----------------

_HIGH_RISK_OVERLAY = """
STRICT OVERLAY (high-risk fields — wrong blank is better than wrong filled; do not invent):
Applies with **stricter** caution to: `broker_name_snapshot`, `broker_load_reference`, `rate` (linehaul /
 carrier pay, not accessorials), **physical** pickup/delivery **stops** and their **full address** and
**date/time**, `equipment_type` / `trailer_type` / `trailer_size`, `temperature_requirement`, `commodity`,
`estimated_weight`.
- For these fields: if uncertain, use **null** (or `extraction_warnings` short note) — do **not** guess.
- **Stops:** never use bill-to, remittance, payment, **invoice-only**, **mailing**, **corporate**,
  **broker back-office (non-stop)**, or **carrier** yard as a **driver** pickup/delivery stop unless the
  document clearly labels that address as the actual **shipper pickup** or **receiver delivery** for
  this load.
- **broker_load_reference:** must be a plausible broker/order id (typically includes a **digit**);
  not ordinary English; not Yes/RELATES/will/must/Information; not MC/DOT, phone, fax, weight, miles,
  rate, date, or time alone; put alternates in `references[]` when in doubt.
- **rate:** prefer **agreed linehaul / total carrier pay** for this move — not detention, lumper, late fee,
  quick pay discount line (see Do-not-use labels in the JSON block below when choosing `rate`).

The JSON block after this preface is the **strict semantic reference** for those high-risk areas; map
concepts to **flat** `extracted` fields as in the MAPPING section (no nested `CriticalExtractionV11` objects).
"""

_FLAT_FIELD_MAPPING = """
FLAT `extracted` MAPPING (no nested critical objects; schema is fixed):
- Scalars: `broker_name_snapshot`, `broker_load_reference`, `rate` (float), `commodity`,
  `temperature_requirement` (string), `estimated_weight` (int), `equipment_type`, `trailer_type`,
  `trailer_size`, `mode`, `miles`, `customer_rate`, `customs_broker_name`, MC/DOT snapshots, and all
  three broker **contact** snapshots — each is a string or null as the schema says.
- `references[]`: {kind, value, label?, primary_candidate?, confidence?} as allowed; keep useful
  secondary IDs.
- `stops[]`: `stop_type` in pickup|delivery|drop|other; `sequence` 0,1,2…; `state_or_province` (name as
  in schema); not `state_province`.
- The critical JSON’s nested `output` / `needs_review` / `confidence` objects do **not** exist in
  this contract — if ambiguous, `extraction_warnings` + nulls, not a parallel tree.
- Where the overlay JSON says "return null when uncertain" for a nested value, apply to the **matching**
  legacy scalar; where it says to preserve **candidates** in a separate list, use `references[]` and null
  `broker_load_reference` if needed.
"""


def _docs_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "CRITICAL_EXTRACTION_CONTRACT_v1.1.json.md"


def build_truckerjson_field_instruction_text() -> str:
    """
    High-risk instruction JSON (same file as `critical_v1_1`) + explicit full-form + contact guidance.
    Truncation ~50k to match `build_critical_v11_field_instruction_text` budget.
    """
    path = _docs_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return (
            _FULL_FORM_TARGET
            + _HIGH_RISK_OVERLAY
            + _FLAT_FIELD_MAPPING
            + "\n(High-risk rules file missing; use conservative nulls for broker_load_reference, rate, and stops.)\n"
        )
    out: list[str] = [
        _FULL_FORM_TARGET,
        _HIGH_RISK_OVERLAY,
        _FLAT_FIELD_MAPPING,
        f"--- High-risk source document: purpose: {data.get('purpose', '')!s}\n",
        "Global rules from high-risk file (apply where they align with the overlay; do not use them to drop full-form fields):",
    ]
    for g in data.get("global_rules") or []:
        if isinstance(g, str):
            out.append(f"- {g}")
    out.append("")
    out.append("Field instructions (JSON — use as strict semantics for the named high-risk areas; keep filling all other legacy fields):")
    fi = data.get("field_instructions")
    out.append(json.dumps(fi if isinstance(fi, dict) else {}, indent=2)[:48000])
    return "\n".join(out)[:50000]


def build_truckerjson_field_instructions_block() -> str:
    """Appended to `_system_prompt()` in `load_lab_semantic` for `response_contract=truckerjson`."""
    return (
        "\n--- BEGIN TRUCKERJSON: FULL-FORM + HIGH-RISK INSTRUCTION OVERLAY ---\n"
        f"{build_truckerjson_field_instruction_text()}\n"
        "--- END TRUCKERJSON: FULL-FORM + HIGH-RISK INSTRUCTION OVERLAY ---\n"
    )
