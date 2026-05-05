"""Pure adapter: Load Lab–shaped parse_response dict → LoadDocumentParseResponse.

No database, no OpenAI, no file I/O. Safe for unit tests and future parse-document wiring.

Stop sequences: optional reindex to 0..n-1 after stable sort by (sequence, list order).
Appointment dates are left as-is (Lab may use MM/DD/YYYY; schema allows any string).
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from app.schemas.load_document_parse import LoadDocumentParseResponse

_WORKSPACE_PARSE_ROOT_KEYS = frozenset(
    {
        "document",
        "extracted",
        "raw_text",
        "warnings",
        "field_confidence",
        "context",
    }
)


def _reindex_stop_sequences(stops: list[Any]) -> list[Any]:
    """Stable sort by (sequence, original index), then assign sequence 0..n-1."""
    keyed: list[tuple[int, int, Any]] = []
    for i, item in enumerate(stops):
        if isinstance(item, dict):
            raw_seq = item.get("sequence", 0)
            try:
                seq_int = int(raw_seq)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                seq_int = 0
        else:
            seq_int = 0
        keyed.append((seq_int, i, item))
    keyed.sort(key=lambda t: (t[0], t[1]))
    out: list[Any] = []
    for new_seq, (_, _, item) in enumerate(keyed):
        if isinstance(item, dict):
            out.append({**item, "sequence": new_seq})
        else:
            out.append(item)
    return out


def map_lab_parse_response_to_document_contract(
    payload: Mapping[str, Any],
    *,
    strip_parse_diagnostics: bool = True,
    strip_unknown_root_keys: bool = True,
    reindex_stop_sequences: bool = True,
) -> LoadDocumentParseResponse:
    """Map an in-memory Lab-style payload to a validated workspace contract.

    - Root-level keys are restricted to the workspace contract when
      ``strip_unknown_root_keys`` is True (default), which drops
      ``parse_diagnostics`` and any other Lab-only root keys.
    - If ``strip_unknown_root_keys`` is False, ``strip_parse_diagnostics`` removes
      only that key from a copied dict before validation (other extras may still
      be ignored by Pydantic depending on model configuration).

    ``context`` is taken only from ``payload[\"context\"]`` when it is a dict;
    it is not merged from root-level Lab fields.
    """
    if strip_unknown_root_keys:
        contract: dict[str, Any] = {
            k: payload[k] for k in _WORKSPACE_PARSE_ROOT_KEYS if k in payload
        }
    else:
        contract = dict(payload)
        if strip_parse_diagnostics:
            contract.pop("parse_diagnostics", None)

    if "warnings" not in contract:
        contract["warnings"] = []
    if "field_confidence" not in contract:
        contract["field_confidence"] = {}

    ctx = contract.get("context", payload.get("context"))
    if isinstance(ctx, dict):
        contract["context"] = copy.deepcopy(ctx)
    else:
        contract["context"] = {}

    extracted = contract.get("extracted")
    if reindex_stop_sequences and isinstance(extracted, dict):
        ex = copy.deepcopy(extracted)
        stops = ex.get("stops")
        if isinstance(stops, list) and stops:
            ex["stops"] = _reindex_stop_sequences(stops)
        contract["extracted"] = ex
    elif isinstance(extracted, dict):
        contract["extracted"] = copy.deepcopy(extracted)

    return LoadDocumentParseResponse.model_validate(contract)

