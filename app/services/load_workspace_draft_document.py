"""Persist rate-confirmation PDF + accepted parse on a load workspace draft."""

from __future__ import annotations

import copy
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency.draft_conflicts import workspace_draft_version_conflict_exception
from app.core.storage import get_storage
from app.models.load_workspace_draft import LoadWorkspaceDraft
from app.schemas.load_document_parse import (
    LoadDocumentParseResponse,
    strip_nul_bytes_from_json_tree,
)
from app.services.load_document_parse_orchestrator import parse_load_workspace_document_orchestrated
from app.services.load_parser_pdf_safety import UnsafeLoadPdfError, validate_load_parser_pdf
from app.services.load_workspace_draft_lifecycle import require_workspace_draft_open_for_mutation

LOAD_WORKSPACE_DRAFT_PDF_MODULE = "load_workspace_draft"
WORKSPACE_DRAFT_ACCEPTED_PARSE_SCHEMA_VERSION = "load_document_parse_response_v1"
MAX_PDF_BYTES = 20 * 1024 * 1024
EDITABLE_STATUS = "draft"


async def _read_bounded_pdf(file: UploadFile) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = await file.read(1024 * 1024)
        if not piece:
            break
        total += len(piece)
        if total > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="PDF too large",
            )
        chunks.append(piece)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    filename = (file.filename or "upload.pdf")[:512]
    return data, filename


def accepted_parse_from_response(parse: LoadDocumentParseResponse) -> dict:
    return strip_nul_bytes_from_json_tree(parse.model_dump(mode="json"))


_REVISED_PDF_KEY = "_revised_pdf"
_REVISED_PDFS_KEY = "_revised_pdfs"
_MISSING = object()
_INDEXED_FIELD = re.compile(r"^([A-Za-z0-9_]+)\[(\d+)\](?:\.([A-Za-z0-9_]+))?$")

_SCALAR_FIELDS = (
    "broker_name_snapshot",
    "broker_contact_name_snapshot",
    "broker_contact_phone_snapshot",
    "broker_contact_extension_snapshot",
    "broker_contact_email_snapshot",
    "broker_load_reference",
    "mode",
    "equipment_type",
    "trailer_type",
    "trailer_size",
    "commodity",
    "estimated_weight",
    "hazmat_flag",
    "temperature_requirement",
    "pallet_case_count",
    "rate",
    "customer_rate",
    "miles",
)

_STOP_FIELDS = (
    "stop_type",
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
)

_DRAFT_KEYS_TO_EXTRACTED = (
    (("brokerNameSnapshot", "broker_name_snapshot"), "broker_name_snapshot"),
    (("brokerContactNameSnapshot", "broker_contact_name_snapshot"), "broker_contact_name_snapshot"),
    (("brokerContactPhoneSnapshot", "broker_contact_phone_snapshot"), "broker_contact_phone_snapshot"),
    (("brokerContactExtensionSnapshot", "broker_contact_extension_snapshot"), "broker_contact_extension_snapshot"),
    (("brokerContactEmailSnapshot", "broker_contact_email_snapshot"), "broker_contact_email_snapshot"),
    (("brokerLoadReference", "broker_load_reference"), "broker_load_reference"),
    (("freightMode", "mode"), "mode"),
    (("equipmentType", "equipment_type"), "equipment_type"),
    (("trailerType", "trailer_type"), "trailer_type"),
    (("trailerSize", "trailer_size"), "trailer_size"),
    (("commodity",), "commodity"),
    (("estimatedWeight", "estimated_weight"), "estimated_weight"),
    (("hazmat", "hazmat_flag"), "hazmat_flag"),
    (("temperatureRequirement", "temperature_requirement"), "temperature_requirement"),
    (("palletCaseCount", "pallet_case_count"), "pallet_case_count"),
    (("rate",), "rate"),
    (("customerRate", "customer_rate"), "customer_rate"),
    (("miles",), "miles"),
    (("draftStops", "stops"), "stops"),
    (("loadReferences", "references"), "references"),
)


def extracted_fields_in_draft(draft_json: dict | None) -> set[str]:
    """Mapped parser fields the dispatcher form actually sent."""
    if not isinstance(draft_json, dict):
        return set()
    found: set[str] = set()
    for keys, extracted in _DRAFT_KEYS_TO_EXTRACTED:
        if any(key in draft_json for key in keys):
            found.add(extracted)
    return found


def _read(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _decimal_or_none(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.replace("$", "").replace(",", "").strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


def values_equivalent(left: Any, right: Any) -> bool:
    """True when the saved JSON already says what the form says."""
    if left is None and (right is None or right == ""):
        return True
    if right is None and (left is None or left == ""):
        return True
    left_num = _decimal_or_none(left)
    right_num = _decimal_or_none(right)
    if left_num is not None and right_num is not None:
        return left_num == right_num
    if isinstance(left, date) and not isinstance(left, datetime):
        left = left.isoformat()
    if isinstance(right, date) and not isinstance(right, datetime):
        right = right.isoformat()
    return str(left).strip() == str(right).strip()


def _json_ready(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return format(Decimal(str(value)), "f")
    return str(value).strip() or None


def _patch_key(target: dict, key: str, form_value: Any) -> None:
    current = target.get(key)
    ready = _json_ready(form_value)
    if values_equivalent(current, ready):
        return
    target[key] = ready


def _reference_pairs(value: Any) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        return []
    pairs: list[tuple[str, str]] = []
    for item in value:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if not isinstance(item, dict):
            continue
        pairs.append((str(item.get("kind") or "").strip(), str(item.get("value") or "").strip()))
    return pairs


def reconcile_accepted_parse_json(
    accepted: dict | None,
    form: Any,
    *,
    only_fields: set[str] | None = None,
) -> dict:
    """Copy the parser JSON and make mapped fields match the final form.

    Fields the form does not map are left as the parser returned them.
    A mapped field that already matches is left unchanged.
    """
    out = copy.deepcopy(accepted) if isinstance(accepted, dict) else {}
    extracted = out.get("extracted")
    if not isinstance(extracted, dict):
        extracted = {}
        out["extracted"] = extracted
    selected = set(_SCALAR_FIELDS) | {"stops", "references"} if only_fields is None else set(only_fields)

    for key in _SCALAR_FIELDS:
        if key not in selected:
            continue
        _patch_key(extracted, key, _read(form, key))

    if "references" in selected:
        form_refs = _read(form, "references")
        if _reference_pairs(extracted.get("references")) != _reference_pairs(form_refs):
            dumped: list[dict] = []
            for item in form_refs or []:
                if hasattr(item, "model_dump"):
                    dumped.append(item.model_dump(mode="json"))
                elif isinstance(item, dict):
                    dumped.append(dict(item))
            extracted["references"] = dumped

    if "stops" in selected:
        form_stops = _read(form, "stops")
        if form_stops is not None:
            json_stops = extracted.get("stops")
            if not isinstance(json_stops, list):
                json_stops = []
            rebuilt: list[dict] = []
            for index, stop in enumerate(form_stops):
                base = json_stops[index] if index < len(json_stops) and isinstance(json_stops[index], dict) else {}
                base = copy.deepcopy(base)
                for key in _STOP_FIELDS:
                    _patch_key(base, key, _read(stop, key))
                rebuilt.append(base)
            extracted["stops"] = rebuilt
    return strip_nul_bytes_from_json_tree(out)


def parse_json_for_compare(accepted: dict | None) -> dict:
    """Verified JSON sent to the comparison call, without stored file pointers."""
    out = copy.deepcopy(accepted) if isinstance(accepted, dict) else {}
    out.pop(_REVISED_PDF_KEY, None)
    out.pop(_REVISED_PDFS_KEY, None)
    out.pop("raw_text", None)
    return out


def revised_pdf_records(accepted: dict | None) -> list[dict]:
    """Accepted revised PDFs, oldest first. The original file is not in this list."""
    if not isinstance(accepted, dict):
        return []
    records = accepted.get(_REVISED_PDFS_KEY)
    if isinstance(records, list):
        return [dict(item) for item in records if isinstance(item, dict) and str(item.get("storage_key") or "").strip()]
    single = accepted.get(_REVISED_PDF_KEY)
    if isinstance(single, dict) and str(single.get("storage_key") or "").strip():
        return [dict(single)]
    return []


def without_client_pdf_pointers(accepted: dict | None) -> dict:
    """Drop file pointers a client might submit inside a parse JSON."""
    out = copy.deepcopy(accepted) if isinstance(accepted, dict) else {}
    out.pop(_REVISED_PDF_KEY, None)
    out.pop(_REVISED_PDFS_KEY, None)
    return out


def append_revised_pdf(verified: dict, prior: dict | None, pointer: dict) -> dict:
    """Keep every previously accepted revised PDF and add the new one."""
    records = revised_pdf_records(prior)
    records.append(dict(pointer))
    verified[_REVISED_PDFS_KEY] = records
    verified.pop(_REVISED_PDF_KEY, None)
    return verified


def _normalize_field_path(field: str) -> str:
    text = field.strip()
    if text.startswith("extracted."):
        text = text[len("extracted.") :]
    return text


def _resolve_extracted(extracted: Any, field: str) -> Any:
    if not isinstance(extracted, dict):
        return _MISSING
    indexed = _INDEXED_FIELD.match(field)
    if indexed:
        name, index_text, child = indexed.group(1), indexed.group(2), indexed.group(3)
        sequence = extracted.get(name, _MISSING)
        if sequence is _MISSING or not isinstance(sequence, list):
            return _MISSING
        index = int(index_text)
        if index >= len(sequence) or not isinstance(sequence[index], dict):
            return _MISSING
        if child is None:
            return sequence[index]
        if child not in sequence[index]:
            return _MISSING
        return sequence[index][child]
    if field not in extracted:
        return _MISSING
    return extracted[field]


def field_is_editable(field: str) -> bool:
    """True when Change can write this path onto the load form."""
    if field in _SCALAR_FIELDS:
        return True
    indexed = _INDEXED_FIELD.match(field)
    if not indexed:
        return False
    name, child = indexed.group(1), indexed.group(3)
    if name == "stops" and child in _STOP_FIELDS:
        return True
    if name == "references" and child in {"kind", "value"}:
        return True
    return False


def ground_reparse_changes(saved: dict | None, revised: dict | None, proposed: list) -> list[dict]:
    """Keep a proposal only when the path exists on the revised extraction.

    Displayed values come from the saved JSON and the revised extraction.
    A path the form cannot edit stays visible and is not marked editable.
    """
    saved_extracted = saved.get("extracted") if isinstance(saved, dict) else None
    revised_extracted = revised.get("extracted") if isinstance(revised, dict) else None
    grounded: list[dict] = []
    seen: set[str] = set()
    for item in proposed or []:
        if not isinstance(item, dict):
            continue
        field = _normalize_field_path(str(item.get("field") or ""))
        if not field or field in seen:
            continue
        revised_value = _resolve_extracted(revised_extracted, field)
        if revised_value is _MISSING:
            continue
        current_value = _resolve_extracted(saved_extracted, field)
        if current_value is _MISSING:
            current_value = None
        if values_equivalent(current_value, revised_value):
            continue
        seen.add(field)
        label = str(item.get("label") or "").strip()
        if not label or len(label) > 80 or "\n" in label:
            label = field
        grounded.append(
            {
                "field": field,
                "label": label,
                "current_value": current_value,
                "revised_value": revised_value,
                "editable": field_is_editable(field),
            }
        )
    return grounded


async def parse_and_attach_workspace_draft_pdf(
    db: AsyncSession,
    tenant_id: int,
    tenant_slug: str,
    draft_id: uuid.UUID,
    file: UploadFile,
    *,
    updated_by_platform_user_id: str | None,
    expected_concurrency_version: int | None = None,
    continue_anyway: bool = False,
) -> tuple[LoadWorkspaceDraft, LoadDocumentParseResponse]:
    current = await db.scalar(
        select(LoadWorkspaceDraft).where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
        )
    )
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")
    await require_workspace_draft_open_for_mutation(db, current)
    server_version = int(current.concurrency_version)
    if expected_concurrency_version is not None and expected_concurrency_version != server_version:
        raise workspace_draft_version_conflict_exception(
            draft_id=draft_id,
            client_version=expected_concurrency_version,
            server_version=server_version,
        )

    pdf_bytes, filename = await _read_bounded_pdf(file)
    try:
        validate_load_parser_pdf(pdf_bytes)
    except UnsafeLoadPdfError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    draft_json = current.draft_json if isinstance(current.draft_json, dict) else {}
    broker_raw = draft_json.get("brokerId") or draft_json.get("broker_id")
    incoming_broker_id: int | None = None
    if broker_raw is not None and str(broker_raw).strip():
        try:
            parsed_broker = int(broker_raw)
            if parsed_broker > 0:
                incoming_broker_id = parsed_broker
        except (TypeError, ValueError):
            incoming_broker_id = None

    parse = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename=filename,
        tenant_id=tenant_id,
        db=db,
        continue_anyway=continue_anyway,
        incoming_broker_id=incoming_broker_id,
    )
    if parse.context.get("semantic_outcome") == "blocked_duplicate_review":
        # Review gate must not store/replace the draft PDF, accepted parse,
        # or increment concurrency. Continue anyway reuses the same draft.
        return current, parse
    ctx = dict(parse.context or {})
    ctx["workspace_draft_id"] = str(draft_id)
    parse = parse.model_copy(update={"context": ctx})

    stored = await get_storage().save_bytes(
        tenant_slug,
        LOAD_WORKSPACE_DRAFT_PDF_MODULE,
        "workspace_draft",
        str(draft_id),
        pdf_bytes,
        filename_hint=filename,
        content_type="application/pdf",
    )

    previous_key = current.pdf_storage_key
    now = datetime.now(timezone.utc)
    accepted = accepted_parse_from_response(parse)

    stmt = (
        update(LoadWorkspaceDraft)
        .where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
            LoadWorkspaceDraft.status == EDITABLE_STATUS,
            LoadWorkspaceDraft.concurrency_version == server_version,
        )
        .values(
            pdf_storage_key=stored.storage_key,
            pdf_sha256=stored.sha256,
            pdf_filename=stored.original_filename,
            pdf_size_bytes=stored.file_size_bytes,
            pdf_upload_state="ready",
            pdf_retention_class="workspace_ttl",
            accepted_parse_json=accepted,
            accepted_parse_schema_version=WORKSPACE_DRAFT_ACCEPTED_PARSE_SCHEMA_VERSION,
            accepted_parse_pdf_sha256=stored.sha256,
            concurrency_version=LoadWorkspaceDraft.concurrency_version + 1,
            updated_by_platform_user_id=updated_by_platform_user_id,
            updated_at=func.now(),
        )
        .returning(LoadWorkspaceDraft)
    )
    result = await db.execute(stmt)
    updated = result.scalar_one_or_none()
    if updated is None:
        await db.rollback()
        get_storage().delete(
            stored.storage_key,
            module=LOAD_WORKSPACE_DRAFT_PDF_MODULE,
            tenant_slug=tenant_slug,
        )
        raise workspace_draft_version_conflict_exception(
            draft_id=draft_id,
            client_version=expected_concurrency_version or server_version,
            server_version=server_version,
        )

    try:
        await db.commit()
        await db.refresh(updated)
    except Exception:
        await db.rollback()
        get_storage().delete(
            stored.storage_key,
            module=LOAD_WORKSPACE_DRAFT_PDF_MODULE,
            tenant_slug=tenant_slug,
        )
        raise

    if previous_key and previous_key != stored.storage_key:
        get_storage().delete(
            previous_key,
            module=LOAD_WORKSPACE_DRAFT_PDF_MODULE,
            tenant_slug=tenant_slug,
        )

    return updated, parse


async def get_workspace_draft_pdf_row(
    db: AsyncSession, tenant_id: int, draft_id: uuid.UUID
) -> LoadWorkspaceDraft:
    row = await db.scalar(
        select(LoadWorkspaceDraft).where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")
    if row.pdf_upload_state != "ready" or not row.pdf_storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No rate confirmation PDF on this draft")
    return row
