"""HTTP helper for POST /loads/parse-document.

This module is **not** a second parser. It validates caller context and forwards bytes to the
single product entrypoint ``parse_pdf_bytes_to_load_document_response`` (see
``app.services.load_document_product_parser``).

Revised-rate-confirmation compare calls that same entrypoint and does not change it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.load_commercial_evidence import LoadCommercialEvidence
from app.schemas.load_document_parse import (
    LoadDocumentParseResponse,
    RateConfirmationRevisionChange,
    RateConfirmationRevisionCompareResponse,
)
from app.services.load_document_product_parser import parse_pdf_bytes_to_load_document_response


async def parse_load_workspace_document_orchestrated(
    pdf_bytes: bytes,
    *,
    filename: str,
    email_thread_id: int | None = None,
    load_id: int | None = None,
    openai_chat_json_schema: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    tenant_id: int | None = None,
    db: AsyncSession | None = None,
    continue_anyway: bool = False,
    incoming_broker_id: int | None = None,
) -> LoadDocumentParseResponse:
    """
    Parse PDF for workspace hydration only (no DB, no load/trip mutation).

    No feature flag and no legacy diagnostics fallback: Rate Confirmation v2 path.
    """
    _ = email_thread_id, load_id
    fn = (filename or "upload.pdf")[:512]

    if tenant_id is None or db is None:
        raise RuntimeError("tenant_id and db are required for parse-document")

    out = await parse_pdf_bytes_to_load_document_response(
        db,
        tenant_id=tenant_id,
        pdf_bytes=pdf_bytes,
        filename=fn,
        openai_chat_json_schema=openai_chat_json_schema,
        continue_anyway=continue_anyway,
        exclude_load_id=load_id,
        incoming_broker_id=incoming_broker_id,
    )
    ctx = dict(out.context or {})
    if email_thread_id is not None:
        ctx["email_thread_id"] = int(email_thread_id)
    if load_id is not None:
        ctx["load_id"] = int(load_id)
    if ctx != out.context:
        out = out.model_copy(update={"context": ctx})
    return out


class RateConfirmationRevisionCompareError(Exception):
    """Domain result for the read-only revised rate-confirmation compare."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


_NO_BASELINE = (
    "This load has no usable creation snapshot or original rate-confirmation extraction."
)
_CANCELLED = "Cancelled loads cannot be compared to a revised rate confirmation."
_DIFFERENT_LOAD = (
    "The revised rate confirmation has a different broker load number than this load. "
    "No changes are proposed."
)
_NO_REVISED_REF = (
    "Could not read a broker load number on this PDF, so it cannot be confirmed as the same load."
)
_NO_SAVED_REF = "This load has no broker load number saved, so the revised PDF cannot be matched."
_COMPARE_FAILED = "Revised rate confirmation comparison could not be read."

_STORED_TOP = frozenset(
    {
        "load_number",
        "broker_load_reference",
        "references",
        "broker_id",
        "broker_contact_id",
        "customs_broker_id",
        "broker_name_snapshot",
        "broker_contact_name_snapshot",
        "broker_contact_phone_snapshot",
        "broker_contact_extension_snapshot",
        "broker_contact_email_snapshot",
        "broker_match_method",
        "broker_match_confidence_tier",
        "broker_match_explanation",
        "review_required",
        "is_duplicate_of_load_id",
        "promotion_origin_workspace_draft_id",
        "status",
        "mode",
        "equipment_type",
        "trailer_type",
        "trailer_size",
        "commodity",
        "estimated_weight",
        "hazmat_flag",
        "temperature_requirement",
        "pallet_case_count",
        "miles",
        "internal_notes",
        "rate",
        "customer_rate",
        "stops",
    }
)
_STORED_STOP = frozenset(
    {
        "id",
        "stop_type",
        "sequence",
        "facility_name",
        "street",
        "city",
        "state_or_province",
        "postal_code",
        "country",
        "reference_number",
        "appointment_type",
        "appointment_date",
        "appointment_time_text",
        "notes",
        "commodity_notes",
    }
)
_MONEY = frozenset({"rate", "customer_rate"})
_BROKER_IDENTITY = frozenset(
    {
        "broker_load_reference",
        "broker_id",
        "broker_contact_id",
        "customs_broker_id",
        "customs_broker_name",
        "broker_name_snapshot",
        "broker_phone_snapshot",
        "broker_contact_name_snapshot",
        "broker_contact_phone_snapshot",
        "broker_contact_extension_snapshot",
        "broker_contact_email_snapshot",
        "broker_mc_number_snapshot",
        "broker_dot_number_snapshot",
    }
)
_STOP_WHEN = frozenset({"appointment_date", "appointment_time_text"})
_BROKER_NOTICE_FIELDS = _BROKER_IDENTITY - {"broker_load_reference"}
_INFO_ONLY_FIELDS = frozenset({"mode", "equipment_type", "trailer_type", "trailer_size"})
_UNREADABLE_PARSE = frozenset({"blocked_ocr_required", "skipped_missing_client", "ocr_failed"})
_UNREADABLE_PDF = "This PDF could not be read"
_BROKER_NOTICES = {
    "broker_name_snapshot": "Broker name reads differently on the revised PDF",
    "broker_phone_snapshot": "Broker phone reads differently on the revised PDF",
    "broker_contact_name_snapshot": "Broker contact reads differently on the revised PDF",
    "broker_contact_phone_snapshot": "Broker contact phone reads differently on the revised PDF",
    "broker_contact_extension_snapshot": "Broker contact extension reads differently on the revised PDF",
    "broker_contact_email_snapshot": "Broker contact email reads differently on the revised PDF",
    "broker_mc_number_snapshot": "Broker MC number reads differently on the revised PDF",
    "broker_dot_number_snapshot": "Broker DOT number reads differently on the revised PDF",
    "broker_id": "Broker identity reads differently on the revised PDF",
    "broker_contact_id": "Broker contact reads differently on the revised PDF",
    "customs_broker_id": "Customs broker reads differently on the revised PDF",
    "customs_broker_name": "Customs broker reads differently on the revised PDF",
}

_COMPARE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "field": {"type": "string"},
                    "new_value": {"type": "string"},
                    "ai_note": {"type": "string"},
                },
                "required": ["field", "new_value", "ai_note"],
            },
        }
    },
    "required": ["changes"],
}
_COMPARE_SYSTEM = (
    "You compare one saved load snapshot to one new rate-confirmation extraction. "
    "Return a per-field change list only. Never return a load, a replacement extraction, "
    "or a field that did not change. "
    "field is a path into the extraction, such as rate or stops[0].city. "
    "new_value is that field's value from the new extraction, written as a string. "
    "ai_note is one short sentence."
)
_PATH_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PATH_INDEX = re.compile(r"\[(\d+)\]")


def original_evidence_select(tenant_id: int, load_id: int):
    """Tenant-scoped read of the original accepted extraction. Not an update."""
    return select(LoadCommercialEvidence).where(
        LoadCommercialEvidence.tenant_id == int(tenant_id),
        LoadCommercialEvidence.load_id == int(load_id),
        LoadCommercialEvidence.evidence_kind == "rate_confirmation_pdf",
    )


def _extraction_dict(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or not payload:
        return None
    extracted = payload.get("extracted")
    if isinstance(extracted, dict) and extracted:
        return extracted
    if any(key in payload for key in ("broker_load_reference", "rate", "stops", "broker_name_snapshot")):
        return payload
    return None


def _parse_field_path(field: str) -> list[str | int] | None:
    path = field.strip()
    if path.startswith("extracted."):
        path = path[len("extracted.") :]
    if not path or len(path) > 200:
        return None
    tokens: list[str | int] = []
    index = 0
    while index < len(path):
        if path[index] == ".":
            index += 1
            if index >= len(path):
                return None
            continue
        name = _PATH_NAME.match(path, index)
        if name:
            tokens.append(name.group(0))
            index = name.end()
            continue
        bracket = _PATH_INDEX.match(path, index)
        if bracket:
            tokens.append(int(bracket.group(1)))
            index = bracket.end()
            continue
        return None
    if not tokens or not isinstance(tokens[0], str):
        return None
    return tokens


def _lookup(tree: Any, tokens: list[str | int]) -> tuple[bool, Any]:
    current = tree
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current) or token < 0:
                return False, None
            current = current[token]
            continue
        if not isinstance(current, dict) or token not in current:
            return False, None
        current = current[token]
    return True, current


def _looks_numeric(text: str) -> bool:
    cleaned = text.replace("$", "").replace(",", "").strip()
    if not cleaned or any(ch.isalpha() for ch in cleaned):
        return False
    try:
        Decimal(cleaned)
    except InvalidOperation:
        return False
    return True


def _canon_number(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
    else:
        cleaned = str(value)
    try:
        return format(Decimal(cleaned).quantize(Decimal("0.01")), "f")
    except (InvalidOperation, ValueError):
        return None


def _canon(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return _canon_number(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        if _looks_numeric(text):
            return _canon_number(text)
        return text.casefold()
    if isinstance(value, list):
        return tuple(_canon(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((str(key), _canon(item)) for key, item in value.items()))
    return str(value).strip().casefold()


def _names(tokens: list[str | int]) -> list[str]:
    return [token for token in tokens if isinstance(token, str)]


def _is_stored(tokens: list[str | int]) -> bool:
    names = _names(tokens)
    if not names or names[0] not in _STORED_TOP:
        return False
    if names[0] == "stops":
        return len(names) == 1 or names[-1] in _STORED_STOP
    if names[0] == "references":
        return True
    return len(names) == 1


def _requires_explicit_accept(tokens: list[str | int]) -> bool:
    names = _names(tokens)
    if not names:
        return False
    leaf = names[-1]
    return leaf in _MONEY or leaf in _BROKER_IDENTITY or leaf in _STOP_WHEN


def _broker_ref(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _mode_label(value: Any) -> str | None:
    """Fold a longer name for the same mode. A different mode stays different."""
    text = _canon(value)
    if not isinstance(text, str):
        return None
    compact = text.replace(" ", "")
    if compact in {"ftl", "fulltruckload", "truckload"}:
        return "truckload"
    if compact in {"ltl", "lessthantruckload"}:
        return "ltl"
    return None


def _same_reading(leaf: str, left: Any, right: Any) -> bool:
    if _canon(left) == _canon(right):
        return True
    if leaf == "mode":
        label = _mode_label(left)
        return label is not None and label == _mode_label(right)
    return False


def _has_usable_extraction(extracted: dict[str, Any]) -> bool:
    for key, value in extracted.items():
        if key in {"stops", "references"}:
            if isinstance(value, list) and any(
                any(_canon(item) is not None for item in row.values()) if isinstance(row, dict) else _canon(row) is not None
                for row in value
            ):
                return True
            continue
        if _canon(value) is not None:
            return True
    return False


def _revised_pdf_unreadable(parsed: LoadDocumentParseResponse) -> bool:
    outcome = str((parsed.context or {}).get("semantic_outcome") or "")
    if outcome in _UNREADABLE_PARSE:
        return True
    return not _has_usable_extraction(parsed.extracted.model_dump(mode="json"))


def _broker_notices(
    *,
    current: dict[str, Any],
    original_extracted: dict[str, Any],
    new_extracted: dict[str, Any],
) -> list[str]:
    notices: list[str] = []
    for field, sentence in _BROKER_NOTICES.items():
        found, new_value = _lookup(new_extracted, [field])
        if not found or _canon(new_value) is None:
            continue
        _original_found, original_value = _lookup(original_extracted, [field])
        _current_found, current_value = _lookup(current, [field])
        if _same_reading(field, new_value, original_value) or _same_reading(field, new_value, current_value):
            continue
        notices.append(sentence)
    return notices


def _facility_notices(
    *,
    current: dict[str, Any],
    original_extracted: dict[str, Any],
    new_extracted: dict[str, Any],
) -> list[str]:
    """A different facility name is visible and is not a proposed load change."""
    notices: list[str] = []
    new_stops = new_extracted.get("stops") if isinstance(new_extracted.get("stops"), list) else []
    original_stops = original_extracted.get("stops") if isinstance(original_extracted.get("stops"), list) else []
    current_stops = current.get("stops") if isinstance(current.get("stops"), list) else []
    for index, stop in enumerate(new_stops):
        if not isinstance(stop, dict):
            continue
        new_name = stop.get("facility_name")
        if _canon(new_name) is None:
            continue
        original_name = None
        if index < len(original_stops) and isinstance(original_stops[index], dict):
            original_name = original_stops[index].get("facility_name")
        current_name = None
        if index < len(current_stops) and isinstance(current_stops[index], dict):
            current_name = current_stops[index].get("facility_name")
        if _same_reading("facility_name", new_name, original_name) or _same_reading(
            "facility_name", new_name, current_name
        ):
            continue
        notices.append(f"Facility name reads differently at stop {index + 1}")
    return notices


def verify_revision_changes(
    proposals: list[dict[str, Any]],
    *,
    current: dict[str, Any],
    original_extracted: dict[str, Any],
    new_extracted: dict[str, Any],
) -> list[RateConfirmationRevisionChange]:
    """Keep a proposal only when the new extraction value is new against both baselines.

    A repeat of the original misread is not a change. A value the new extraction does
    not contain is dropped. This function does not write.
    """
    kept: list[RateConfirmationRevisionChange] = []
    seen: set[str] = set()
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        field = proposal.get("field")
        if not isinstance(field, str) or not field.strip():
            continue
        if "new_value" not in proposal:
            continue
        tokens = _parse_field_path(field)
        if tokens is None:
            continue
        path = field.strip().removeprefix("extracted.")
        if path in seen:
            continue
        names = _names(tokens)
        leaf = names[-1]
        if leaf in _BROKER_NOTICE_FIELDS or leaf == "facility_name":
            continue
        found, extracted_value = _lookup(new_extracted, tokens)
        if not found or _canon(proposal.get("new_value")) != _canon(extracted_value):
            continue
        _original_found, original_value = _lookup(original_extracted, tokens)
        _current_found, current_value = _lookup(current, tokens)
        if _same_reading(leaf, extracted_value, original_value) or _same_reading(leaf, extracted_value, current_value):
            continue
        note = proposal.get("ai_note")
        note_text = note.strip()[:400] if isinstance(note, str) and note.strip() else None
        seen.add(path)
        info_only = leaf in _INFO_ONLY_FIELDS or not _is_stored(tokens)
        kept.append(
            RateConfirmationRevisionChange(
                field=path,
                current_value=current_value,
                original_extracted=original_value,
                new_value=extracted_value,
                kind="info_only" if info_only else "changed",
                ai_note=note_text,
                requires_explicit_accept=False if leaf in _INFO_ONLY_FIELDS else _requires_explicit_accept(tokens),
            )
        )
    return kept


async def _default_compare_chat(**kwargs: Any) -> dict[str, Any]:
    from app.services.load_document_parse_openai import parse_document_openai_chat_json_schema

    return await parse_document_openai_chat_json_schema(**kwargs)


async def compare_revised_rate_confirmation(
    db: AsyncSession,
    *,
    tenant_id: int,
    load_id: int,
    pdf_bytes: bytes,
    filename: str,
    parse_document: Callable[..., Awaitable[LoadDocumentParseResponse]] | None = None,
    compare_chat: Callable[..., Awaitable[dict[str, Any]]] | None = None,
) -> RateConfirmationRevisionCompareResponse:
    """Parse a revised rate confirmation and return verified field changes.

    Does not insert, update, or delete. The saved load stays the dispatcher-corrected truth.
    """
    from app.services.load_approved_commercial_snapshot import (
        OUTCOME_PRESENT,
        build_approved_db_fields,
        get_creation_snapshot,
    )
    from app.services.loads import get_load

    load = await get_load(db, tenant_id, load_id)
    if load is None:
        raise RateConfirmationRevisionCompareError(404, "Load not found")
    if (load.status or "").strip().casefold() == "cancelled":
        raise RateConfirmationRevisionCompareError(409, _CANCELLED)

    try:
        snapshot = await get_creation_snapshot(db, tenant_id, load_id)
    except ProgrammingError:
        await db.rollback()
        raise RateConfirmationRevisionCompareError(409, _NO_BASELINE) from None
    if snapshot.outcome != OUTCOME_PRESENT or not isinstance(snapshot.payload, dict):
        raise RateConfirmationRevisionCompareError(409, _NO_BASELINE)

    try:
        evidence = await db.scalar(original_evidence_select(tenant_id, load_id))
    except ProgrammingError:
        await db.rollback()
        raise RateConfirmationRevisionCompareError(409, _NO_BASELINE) from None
    accepted = evidence.accepted_parse_json if evidence is not None else None
    original = _extraction_dict(accepted if isinstance(accepted, dict) else None)
    if original is None:
        raise RateConfirmationRevisionCompareError(409, _NO_BASELINE)

    parser = parse_document or parse_load_workspace_document_orchestrated
    parsed = await parser(
        pdf_bytes,
        filename=filename,
        load_id=load_id,
        tenant_id=tenant_id,
        db=db,
    )
    if _revised_pdf_unreadable(parsed):
        raise RateConfirmationRevisionCompareError(422, _UNREADABLE_PDF)
    new_extracted = parsed.extracted.model_dump(mode="json")
    current = build_approved_db_fields(load)
    saved_ref = _broker_ref(load.broker_load_reference)
    new_ref = _broker_ref(new_extracted.get("broker_load_reference"))
    if not saved_ref:
        return RateConfirmationRevisionCompareResponse(
            same_load=False,
            same_load_confirmed=False,
            warning=_NO_SAVED_REF,
            notices=[],
            changes=[],
        )
    if not new_ref:
        return RateConfirmationRevisionCompareResponse(
            same_load=False,
            same_load_confirmed=False,
            warning=_NO_REVISED_REF,
            notices=[],
            changes=[],
        )
    if saved_ref != new_ref:
        return RateConfirmationRevisionCompareResponse(
            same_load=False,
            same_load_confirmed=True,
            warning=_DIFFERENT_LOAD,
            notices=[],
            changes=[],
        )

    chat = compare_chat or _default_compare_chat
    user_text = json.dumps(
        {
            "saved_snapshot": snapshot.payload,
            "new_extraction": parsed.model_dump(mode="json"),
        },
        default=str,
        ensure_ascii=True,
    )
    try:
        raw = await chat(
            system=_COMPARE_SYSTEM,
            user_text=user_text,
            schema=_COMPARE_SCHEMA,
            schema_name="rc_revision_field_changes",
        )
    except RateConfirmationRevisionCompareError:
        raise
    except Exception as exc:
        raise RateConfirmationRevisionCompareError(502, _COMPARE_FAILED) from exc
    proposals = raw.get("changes") if isinstance(raw, dict) else None
    if not isinstance(proposals, list):
        proposals = []
    changes = verify_revision_changes(
        [item for item in proposals if isinstance(item, dict)],
        current=current,
        original_extracted=original,
        new_extracted=new_extracted,
    )
    notices = _broker_notices(
        current=current,
        original_extracted=original,
        new_extracted=new_extracted,
    )
    notices.extend(
        _facility_notices(
            current=current,
            original_extracted=original,
            new_extracted=new_extracted,
        )
    )
    return RateConfirmationRevisionCompareResponse(
        same_load=True,
        same_load_confirmed=True,
        warning=None,
        notices=notices,
        changes=changes,
    )
