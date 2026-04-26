"""Critical-field design instructions for the legacy `truckerjson` Load Lab contract.

Uses the same JSON source as `critical_extraction_v11_prompt` (`docs/CRITICAL_EXTRACTION_CONTRACT_v1.1.json.md`)
but prepends an adapter: output must stay `LoadLabSemanticModelOutput` / `LoadParseExtractedFields` (flat
scalars, 0-based stop sequence), not the nested `CriticalExtractionV11Root` shape.
"""

from __future__ import annotations

import json
from pathlib import Path

_LEGACY_ADAPTER = """
LEGACY JSON SCHEMA MAPPING (read first — do not output nested critical objects):
- The response follows the provided JSON schema: `document`, `extracted`, `extraction_warnings` only.
- `extracted.broker_name_snapshot` = plain string (not nested {value, confidence, ...}).
- `extracted.broker_load_reference` = a single string or null. Apply label/hint rules below; the string must
  include a digit when it is a real load/order ref; use null if uncertain. Put alternate labeled IDs in
  `extracted.references` with {kind, value, ...} as allowed by the schema.
- `extracted.rate` = carrier total as a number in `rate` (float) when clearly the **line-haul / carrier pay
  total** for this move — not accessorial, detention, lumper, or late fees (see do_not_use in contract JSON).
- `extracted.stops[]` items use: `stop_type` in pickup|delivery|drop|other, `sequence` 0,1,2,...
  in PDF order, `state_or_province` (not state_province), `appointment_date` YYYY-MM-DD or null,
  `appointment_time_text` for windows. You do **not** output address_quality, page_number, or nested
  reference_numbers on stops unless the schema includes them; keep street/city/zip as strings.
- `extracted.equipment_type`, `trailer_type`, `trailer_size` = separate strings as in schema.
- `extracted.temperature_requirement` = free text or null (not a structured min/max object).
- `extracted.commodity`, `extracted.estimated_weight` = scalar fields per schema.
- Field instructions below speak of "confidence" and "needs_review" for the **critical** design — for this
  contract, if something is uncertain use null/omit and optionally add a short human note in
  `extraction_warnings` (do not invent a parallel confidence object tree).

GLOBAL RULES ADAPTATION:
- Where the source says "return null when uncertain" for nested `.value` fields, apply the same to the
  corresponding legacy scalar.
- **Ignore** "every field must include confidence and source evidence" as a structural requirement; the
  provided schema has no per-field confidence objects. Prefer accurate scalars; use `extraction_warnings`
  for ambiguity when helpful.
- **Ignore** "preserve candidates in broker_load_reference.value null" in the sense of a nested value —
  use `null` for `broker_load_reference` and list extras under `extracted.references` instead.

"""


def _docs_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "CRITICAL_EXTRACTION_CONTRACT_v1.1.json.md"


def build_truckerjson_field_instruction_text() -> str:
    """
    Load shared critical-field instruction JSON, emit a single prompt block (adapter + field_instructions).
    Truncation matches critical prompt helper budget (~50k) so model context stays stable.
    """
    path = _docs_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return (
            _LEGACY_ADAPTER
            + "Field instructions file missing or invalid; use conservative extraction only.\n"
        )
    out: list[str] = [_LEGACY_ADAPTER, f"Purpose: {data.get('purpose', '')}\n", "Global rules (interpret per LEGACY MAPPING above):"]
    for g in data.get("global_rules") or []:
        if isinstance(g, str):
            out.append(f"- {g}")
    out.append("")
    out.append("Field instructions (source JSON — apply meaning to legacy `extracted` fields per mapping):")
    fi = data.get("field_instructions")
    out.append(json.dumps(fi if isinstance(fi, dict) else {}, indent=2)[:48000])
    return "\n".join(out)[:50000]


def build_truckerjson_field_instructions_block() -> str:
    """Block suitable for appending to the legacy system prompt."""
    return (
        "\n--- BEGIN DISPATCH-CRITICAL FIELD INSTRUCTIONS (truckerjson / legacy shape) ---\n"
        f"{build_truckerjson_field_instruction_text()}\n"
        "--- END DISPATCH-CRITICAL FIELD INSTRUCTIONS ---\n"
    )
