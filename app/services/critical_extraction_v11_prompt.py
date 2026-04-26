"""Field-instruction text for critical extraction v1.1 (prompt; not schema)."""

from __future__ import annotations

import json
from pathlib import Path

_FALLBACK = (
    "You are extracting dispatch-critical fields only. Return null when uncertain. "
    "Do not use bill-to, remittance, or corporate blocks as driver stops. "
    "Broker load reference must not be common English words. "
    "Include a digit in broker_load_reference unless you have explicit label+evidence. "
    "Read docs/CRITICAL_EXTRACTION_CONTRACT_v1.1.json.md in the repo for full field instructions if missing from deploy."
)


def build_critical_v11_field_instruction_text() -> str:
    root = Path(__file__).resolve().parents[2]
    path = root / "docs" / "CRITICAL_EXTRACTION_CONTRACT_v1.1.json.md"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _FALLBACK
    out: list[str] = [
        f"Purpose: {data.get('purpose', '')}",
        "",
        "Global rules:",
    ]
    for g in data.get("global_rules") or []:
        if isinstance(g, str):
            out.append(f"- {g}")
    out.append("")
    out.append("Field instructions (JSON; follow for reasoning):")
    fi = data.get("field_instructions")
    out.append(json.dumps(fi if isinstance(fi, dict) else {}, indent=2)[:48000])
    return "\n".join(out)[:50000]


def build_critical_v11_system_prompt() -> str:
    return (
        "You are a document extractor for US truckload rate confirmations. "
        "Return a single JSON object that matches the provided JSON schema exactly. "
        "The schema enforces shape; the FIELD INSTRUCTIONS block teaches what to put in each field. "
        "Prefer null over guessing. Set needs_review=true when the document is ambiguous.\n\n"
        "--- BEGIN FIELD INSTRUCTIONS ---\n"
        f"{build_critical_v11_field_instruction_text()}\n"
        "--- END FIELD INSTRUCTIONS ---\n"
    )
