"""Replacement re-parse: one corrected JSON, no write until Save, both PDFs stay readable."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.authz.routes import binding_for
from app.schemas.load import LoadStopCreate
from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services import loads as loads_service
from app.core.config import settings
from app.schemas.load import LoadUpdate
from app.services.load_document_parse_orchestrator import (
    LoadReparseError,
    propose_load_reparse,
    reparse_integrity_token,
    verify_reparse_integrity,
)
from app.services.load_workspace_draft_document import (
    extracted_fields_in_draft,
    ground_reparse_changes,
    parse_json_for_compare,
    reconcile_accepted_parse_json,
    validate_ai_reparse_changes,
)
from app.services.load_workspace_draft_mapper import draft_json_to_load_create

ROOT = Path(__file__).resolve().parents[1]

REPLACEMENT_PATHS = {
    "app/authz/routes.py",
    "app/routers/loads.py",
    "app/schemas/load_document_parse.py",
    "app/services/load_document_parse_orchestrator.py",
    "app/services/load_workspace_draft_document.py",
    "app/services/load_workspace_draft_promotion.py",
    "app/services/loads.py",
    "apps/web/src/api.ts",
    "apps/web/src/loadWorkspace/RateConfirmationPdfPanel.tsx",
    "apps/web/src/loadWorkspace/ReparseChangesDialog.tsx",
    "apps/web/src/pages/LoadWorkspacePage.tsx",
    "tests/test_reparse_replacement.py",
    "tests/test_verified_parse_reconcile.py",
}


def _stop(stop_type: str, sequence: int, city: str, state: str, facility: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        stop_type=stop_type,
        sequence=sequence,
        facility_name=facility,
        street=None,
        city=city,
        state_or_province=state,
        postal_code=None,
        country="US",
        reference_number=None,
        appointment_type=None,
        appointment_date=None,
        appointment_time_text=None,
        notes=None,
    )


def _full_draft() -> dict:
    return {
        "brokerNameSnapshot": "Acme Freight",
        "brokerContactNameSnapshot": "Ann Agent",
        "brokerContactPhoneSnapshot": "555-0100",
        "brokerContactExtensionSnapshot": "12",
        "brokerContactEmailSnapshot": "ann@acme.test",
        "brokerLoadReference": "PO-200",
        "freightMode": "FTL",
        "equipmentType": "Reefer 53",
        "trailerType": "Reefer",
        "trailerSize": "53",
        "commodity": "Food",
        "estimatedWeight": "40000",
        "hazmat": "no",
        "temperatureRequirement": "28",
        "palletCaseCount": "10",
        "rate": "2550",
        "customerRate": "2600",
        "miles": "412",
        "draftStops": [
            {
                "stop_type": "pickup",
                "sequence": 0,
                "city": "Boston",
                "state_or_province": "MA",
                "facility_name": "Boston Dock",
            },
            {
                "stop_type": "delivery",
                "sequence": 1,
                "city": "Dallas",
                "state_or_province": "TX",
                "facility_name": "Dallas Dock",
            },
        ],
        "loadReferences": [{"kind": "po", "value": "PO-200"}],
    }


def _parser_json() -> dict:
    return {
        "raw_text": "original pdf text",
        "context": {"engine": "keep-me"},
        "warnings": ["parser warning"],
        "extracted": {
            "broker_name_snapshot": "Wrong Broker",
            "broker_contact_name_snapshot": "Wrong Person",
            "broker_contact_phone_snapshot": "000",
            "broker_contact_extension_snapshot": "1",
            "broker_contact_email_snapshot": "wrong@example.test",
            "broker_load_reference": "PO-100",
            "mode": "LTL",
            "equipment_type": "Van",
            "trailer_type": "Dry",
            "trailer_size": "48",
            "commodity": "Paper",
            "estimated_weight": 1000,
            "hazmat_flag": True,
            "temperature_requirement": "34",
            "pallet_case_count": "1",
            "rate": "1800.00",
            "customer_rate": "1800.00",
            "miles": 10,
            "unmapped_note": "parser-only",
            "stops": [
                {"stop_type": "pickup", "sequence": 0, "city": "Chicago", "state_or_province": "IL", "facility_code": "CHI-1"},
                {"stop_type": "delivery", "sequence": 1, "city": "Houston", "state_or_province": "TX", "facility_code": "HOU-1"},
            ],
            "references": [{"kind": "other", "value": "OLD", "source_label": "keep-if-unchanged"}],
        },
    }


def test_create_load_json_matches_every_mapped_field_and_keeps_unmapped_fields() -> None:
    draft_json = _full_draft()
    load_create = draft_json_to_load_create(draft_json)
    verified = reconcile_accepted_parse_json(
        _parser_json(),
        load_create,
        only_fields=extracted_fields_in_draft(draft_json),
    )
    extracted = verified["extracted"]
    assert extracted["broker_name_snapshot"] == "Acme Freight"
    assert extracted["broker_contact_name_snapshot"] == "Ann Agent"
    assert extracted["broker_contact_phone_snapshot"] == "555-0100"
    assert extracted["broker_contact_extension_snapshot"] == "12"
    assert extracted["broker_contact_email_snapshot"] == "ann@acme.test"
    assert extracted["broker_load_reference"] == "PO-200"
    assert extracted["mode"] == "FTL"
    assert extracted["equipment_type"] == "Reefer 53"
    assert extracted["trailer_type"] == "Reefer"
    assert extracted["trailer_size"] == "53"
    assert extracted["commodity"] == "Food"
    assert extracted["estimated_weight"] == 40000
    assert extracted["hazmat_flag"] is False
    assert extracted["temperature_requirement"] == "28"
    assert extracted["pallet_case_count"] == "10"
    assert Decimal(extracted["rate"]) == Decimal("2550")
    assert Decimal(extracted["customer_rate"]) == Decimal("2600")
    assert extracted["miles"] == 412
    assert extracted["stops"][0]["city"] == "Boston"
    assert extracted["stops"][0]["state_or_province"] == "MA"
    assert extracted["stops"][0]["facility_name"] == "Boston Dock"
    assert extracted["stops"][0]["facility_code"] == "CHI-1"
    assert extracted["stops"][1]["city"] == "Dallas"
    assert extracted["stops"][1]["facility_code"] == "HOU-1"
    assert [(item["kind"], item["value"]) for item in extracted["references"]] == [("po", "PO-200")]
    assert extracted["unmapped_note"] == "parser-only"
    assert verified["raw_text"] == "original pdf text"
    assert verified["context"] == {"engine": "keep-me"}
    assert verified["warnings"] == ["parser warning"]


def test_rejected_rate_temperature_and_stop_stay_while_accepted_po_changes() -> None:
    revised = {
        "raw_text": "revised pdf text",
        "extracted": {
            "rate": "2550",
            "customer_rate": "2550",
            "broker_load_reference": "PO-200",
            "temperature_requirement": "0",
            "unmapped_note": "still here",
            "stops": [
                {"city": "Boston", "state_or_province": "MA", "facility_code": "BOS-9"},
                {"city": "Dallas", "state_or_province": "TX", "facility_code": "DAL-9"},
            ],
        },
    }
    form = SimpleNamespace(
        rate=Decimal("2500.00"),
        customer_rate=Decimal("2500.00"),
        broker_load_reference="PO-200",
        temperature_requirement="34",
        stops=[
            _stop("pickup", 0, "Chicago", "IL"),
            _stop("delivery", 1, "Dallas", "TX"),
        ],
        references=[],
    )
    out = reconcile_accepted_parse_json(
        revised,
        form,
        only_fields={"rate", "customer_rate", "broker_load_reference", "temperature_requirement", "stops"},
    )
    extracted = out["extracted"]
    assert Decimal(extracted["rate"]) == Decimal("2500")
    assert Decimal(extracted["customer_rate"]) == Decimal("2500")
    assert extracted["broker_load_reference"] == "PO-200"
    assert extracted["temperature_requirement"] == "34"
    assert extracted["stops"][0]["city"] == "Chicago"
    assert extracted["stops"][0]["facility_code"] == "BOS-9"
    assert extracted["stops"][1]["city"] == "Dallas"
    assert extracted["unmapped_note"] == "still here"
    assert out["raw_text"] == "revised pdf text"


class _ReadDb:
    def __init__(self, evidence: SimpleNamespace) -> None:
        self.evidence = evidence
        self.writes: list[str] = []

    async def scalar(self, _stmt):
        return self.evidence

    async def commit(self):
        self.writes.append("commit")

    async def execute(self, *_args, **_kwargs):
        self.writes.append("execute")

    def add(self, _obj):
        self.writes.append("add")


def _revised_response() -> LoadDocumentParseResponse:
    return LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "revised.pdf"},
            "raw_text": "normalized revised text",
            "context": {
                "document_type": "rate_confirmation",
                "classification_reasoning": "Broker rate confirmation with pickup and delivery.",
                "document_date": "2026-02-02",
            },
            "extracted": {
                "rate": "2550",
                "broker_name_snapshot": "Armstrong",
                "broker_load_reference": "PO-200",
                "temperature_requirement": "0",
                "unmapped_note": "changed",
                "references": [{"kind": "po", "value": "NEW"}],
                "stops": [
                    {"stop_type": "pickup", "sequence": 0, "city": "Boston", "state_or_province": "MA"},
                    {"stop_type": "delivery", "sequence": 1, "city": "Dallas", "state_or_province": "TX"},
                ],
            },
        }
    )


@pytest.mark.asyncio
async def test_reparse_uses_existing_parser_and_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    saved = {
        "raw_text": "original",
        "_revised_pdf": {"storage_key": "old-revised"},
        "extracted": {
            "rate": "2500",
            "broker_name_snapshot": "Armstrong",
            "broker_load_reference": "PO-100",
            "temperature_requirement": "34",
            "unmapped_note": "keep",
            "references": [{"kind": "po", "value": "OLD"}],
            "stops": [
                {"stop_type": "pickup", "city": "Chicago", "state_or_province": "IL"},
                {"stop_type": "delivery", "city": "Dallas", "state_or_province": "TX"},
            ],
        },
    }
    evidence = SimpleNamespace(accepted_parse_json=copy.deepcopy(saved))
    before = copy.deepcopy(evidence.accepted_parse_json)
    db = _ReadDb(evidence)
    seen: dict = {}

    async def fake_parser(pdf_bytes, **kwargs):
        seen["pdf"] = pdf_bytes
        seen["parser"] = kwargs
        return _revised_response()

    async def fake_compare(**kwargs):
        seen["compare"] = kwargs
        return {
            "changes": [
                {"field": "rate", "label": "Linehaul increased", "current_value": "1", "revised_value": "9999"},
                {"field": "broker_load_reference", "label": "PO number", "current_value": "nope", "revised_value": "also-nope"},
                {"field": "stops[0].city", "label": "Pickup city", "current_value": "Chicago", "revised_value": "Boston"},
                {"field": "temperature_requirement", "label": "Temperature", "current_value": "34", "revised_value": "0"},
                {"field": "references[0].value", "label": "Reference", "current_value": "FAKE", "revised_value": "FAKE-2"},
                {"field": "unmapped_note", "label": "Note", "current_value": "ai", "revised_value": "ai-2"},
                {"field": "not_a_field", "label": "Nope", "current_value": "a", "revised_value": "b"},
                {"field": "miles", "label": "Miles", "current_value": "100", "revised_value": "100"},
            ]
        }

    monkeypatch.setattr(settings, "jwt_secret", "unit-reparse-secret")

    async def no_other_load(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.services.load_parser_duplicate_precheck.find_exact_pdf_duplicate_candidates",
        no_other_load,
    )
    monkeypatch.setattr(
        "app.services.load_document_parse_orchestrator.parse_load_workspace_document_orchestrated",
        fake_parser,
    )
    proposal = await propose_load_reparse(
        db,
        tenant_id=1,
        load_id=9,
        pdf_bytes=b"%PDF-revised",
        filename="revised.pdf",
        openai_chat_json_schema=fake_compare,
    )
    assert seen["pdf"] == b"%PDF-revised"
    assert seen["parser"]["load_id"] == 9
    assert seen["parser"]["tenant_id"] == 1
    assert "Ignore fields that exist only in JSON 2" in seen["compare"]["system"]
    assert "input_file_bytes" not in seen["compare"]
    assert "You are a TruckERP product parser" not in seen["compare"]["system"]
    baseline_text, revised_text = seen["compare"]["user_text"].split("JSON 2:\n", 1)
    baseline = json.loads(baseline_text.split("JSON 1:\n", 1)[1])
    assert {item["path"] for item in baseline["fields"]} >= {"rate", "broker_load_reference", "stops[0].city"}
    assert all(item["path"] != "unmapped_note" for item in baseline["fields"])
    assert "keep" not in baseline_text
    assert Decimal(json.loads(revised_text)["extracted"]["rate"]) == Decimal("2550")
    assert "old-revised" not in seen["compare"]["user_text"]
    assert seen["compare"]["schema_name"] == "load_reparse_changes"
    by_field = {item["field"]: item for item in proposal["changes"]}
    assert by_field["rate"]["editable"] is True
    assert Decimal(by_field["rate"]["revised_value"]) == Decimal("2550")
    assert by_field["rate"]["current_value"] == "2500"
    assert "9999" not in str(by_field["rate"]["revised_value"])
    assert by_field["temperature_requirement"]["editable"] is True
    assert by_field["temperature_requirement"]["revised_value"] == "0"
    assert by_field["temperature_requirement"]["label"] == "Temperature"
    assert by_field["stops.review.saved.0"]["editable"] is False
    assert "stops[0].city" not in by_field
    assert by_field["broker_load_reference"]["current_value"] == "PO-100"
    assert by_field["broker_load_reference"]["revised_value"] == "PO-200"
    assert "also-nope" not in str(by_field["broker_load_reference"]["revised_value"])
    assert by_field["references[0].value"]["current_value"] == "OLD"
    assert by_field["references[0].value"]["revised_value"] == "NEW"
    assert "FAKE" not in str(by_field["references[0].value"]["revised_value"])
    assert "not_a_field" not in by_field
    assert "unmapped_note" not in by_field
    informational = ground_reparse_changes(
        {"extracted": {"unmapped_note": "keep", "rate": "10"}},
        {"extracted": {"unmapped_note": "changed", "rate": "10"}},
        [
            {"field": "unmapped_note", "label": "Note", "current_value": "ai", "revised_value": "ai-2"},
            {"field": "missing_path", "label": "Missing", "current_value": "a", "revised_value": "b"},
        ],
    )
    assert informational == [
        {
            "field": "unmapped_note",
            "label": "Note",
            "current_value": "keep",
            "revised_value": "changed",
            "editable": False,
        }
    ]
    verify_kwargs = {
        "tenant_id": 1,
        "load_id": 9,
        "revised_parse": proposal["revised_parse"].model_dump(mode="json"),
        "token": proposal["integrity"],
        "baseline": parse_json_for_compare(saved),
        "concurrency_version": 1,
        "acknowledgement_required": proposal["acknowledgement_required"],
        "expires_at": proposal["expires_at"],
    }
    verify_reparse_integrity(pdf_bytes=b"%PDF-revised", **verify_kwargs)
    with pytest.raises(LoadReparseError) as mismatched:
        verify_reparse_integrity(pdf_bytes=b"%PDF-other", **verify_kwargs)
    assert mismatched.value.status_code == 422
    assert "commit" not in db.writes
    assert "add" not in db.writes
    assert evidence.accepted_parse_json == before


def test_popup_change_and_reparse_do_not_hydrate_or_call_save() -> None:
    page = (ROOT / "apps/web/src/pages/LoadWorkspacePage.tsx").read_text()
    reparse = page[page.index("async function onReparsePdf") : page.index("async function onSave")]
    change = page[page.index("function applyReparseChange") : page.index("async function onReparsePdf")]
    dialog = (ROOT / "apps/web/src/loadWorkspace/ReparseChangesDialog.tsx").read_text()
    assert "hydrateLoadWorkspaceFromParseResponse" not in reparse
    assert "updateLoad" not in reparse
    assert "saveLoadReparse" not in reparse
    assert "fetch(" not in change
    assert "updateLoad" not in change
    assert "saveLoadReparse" not in change
    assert "change.editable !== true" in change
    assert "references\\\\[" in change or 'references\\[' in change
    assert "hazmat_flag" in change
    assert "editable === true" in dialog
    assert "For review" in dialog
    assert "hydrate" not in dialog
    assert "fetch(" not in dialog
    assert "updateLoad" not in dialog


class _SaveDb:
    def __init__(self, evidence: SimpleNamespace) -> None:
        self.evidence = evidence

    async def scalar(self, _stmt):
        return self.evidence

    async def refresh(self, _obj, attribute_names=None):
        return None


class _Storage:
    def __init__(self) -> None:
        self.saved = 0
        self.deleted: list[str] = []

    async def save_bytes(self, *args, **kwargs):
        self.saved += 1
        return SimpleNamespace(
            storage_key=f"revised-{self.saved}",
            sha256=f"sha-{self.saved}",
            original_filename=f"revised-{self.saved}.pdf",
        )

    def delete(self, key, **_kwargs):
        self.deleted.append(str(key))


@pytest.mark.asyncio
async def test_save_replaces_json_and_keeps_original_and_revised_pdfs_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = _full_draft()
    form = draft_json_to_load_create(draft)
    load = SimpleNamespace(id=9, stops=form.stops, **form.model_dump(exclude={"stops", "references", "status"}))
    load.references = form.references
    evidence = SimpleNamespace(
        storage_key="original-key",
        file_sha256="original-sha",
        filename="original.pdf",
        accepted_parse_json=_parser_json(),
    )
    storage = _Storage()
    monkeypatch.setattr("app.core.storage.get_storage", lambda: storage)
    reads: list[str] = []

    def fake_read(storage_key, **_kwargs):
        reads.append(storage_key)
        return b"%PDF-bytes"

    monkeypatch.setattr(loads_service, "read_object_bytes", fake_read)
    db = _SaveDb(evidence)
    prior, _row = await loads_service._sync_verified_parse_json(
        db,
        1,
        load,
        only_fields=set(),
        replacement=_parser_json(),
        revised_pdf_bytes=b"%PDF-revised-1",
        revised_pdf_filename="revised-1.pdf",
        tenant_slug="demo",
    )
    assert prior is not None
    assert "_revised_pdfs" not in prior
    second = _parser_json()
    second["_revised_pdfs"] = [{"storage_key": "client-injected", "sha256": "nope", "filename": "nope.pdf"}]
    await loads_service._sync_verified_parse_json(
        db,
        1,
        load,
        only_fields=set(),
        replacement=second,
        revised_pdf_bytes=b"%PDF-revised-2",
        revised_pdf_filename="revised-2.pdf",
        tenant_slug="demo",
    )
    assert storage.deleted == []
    assert evidence.storage_key == "original-key"
    assert evidence.file_sha256 == "original-sha"
    verified = evidence.accepted_parse_json
    assert verified["extracted"]["broker_load_reference"] == "PO-200"
    assert Decimal(verified["extracted"]["rate"]) == Decimal("2550")
    assert verified["extracted"]["temperature_requirement"] == "28"
    assert verified["extracted"]["stops"][0]["city"] == "Boston"
    assert verified["extracted"]["stops"][1]["city"] == "Dallas"
    assert verified["extracted"]["unmapped_note"] == "parser-only"
    assert [item["storage_key"] for item in verified["_revised_pdfs"]] == ["revised-1", "revised-2"]
    assert "_revised_pdf" not in verified
    assert verified["raw_text"] == "original pdf text"

    async def evidence_row(*_args, **_kwargs):
        return evidence

    monkeypatch.setattr(loads_service, "get_load_rate_confirmation_pdf_evidence", evidence_row)
    original_row, original_body = await loads_service.read_load_rate_confirmation_pdf_bytes(
        None, 1, 9, tenant_slug="demo"
    )
    first_name, first_body = await loads_service.read_revised_rate_confirmation_pdf_bytes(
        None, 1, 9, tenant_slug="demo", revision=1
    )
    second_name, second_body = await loads_service.read_revised_rate_confirmation_pdf_bytes(
        None, 1, 9, tenant_slug="demo", revision=2
    )
    assert original_row.storage_key == "original-key"
    assert first_name == "revised-1.pdf"
    assert second_name == "revised-2.pdf"
    assert reads == ["original-key", "revised-1", "revised-2"]
    assert original_body == first_body == second_body == b"%PDF-bytes"
    with pytest.raises(HTTPException):
        await loads_service.read_revised_rate_confirmation_pdf_bytes(
            None, 1, 9, tenant_slug="demo", revision=3
        )


def test_reparse_routes_keep_existing_load_authorization() -> None:
    suggest = binding_for("POST", "/api/v1/loads/{load_id}/rate-confirmation-reparse")
    save = binding_for("POST", "/api/v1/loads/{load_id}/rate-confirmation-reparse/save")
    update = binding_for("PATCH", "/api/v1/loads/{load_id}")
    assert suggest.resource == "loads.documents"
    assert suggest.action == "parse"
    assert suggest.kind == "write"
    assert save.resource == update.resource == "loads.records"
    assert save.action == update.action == "update"
    with pytest.raises(HTTPException) as raised:
        loads_service._guard_update_payload(
            SimpleNamespace(status="draft"),
            __import__("app.schemas.load", fromlist=["LoadUpdate"]).LoadUpdate(
                expected_concurrency_version=1,
                status="ready",
            ),
        )
    assert raised.value.status_code == 409


@pytest.mark.asyncio
async def test_production_compare_call_passes_configured_key_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = SimpleNamespace(
        accepted_parse_json={
            "context": {"document_date": "2026-01-01"},
            "extracted": {
                "rate": "10",
                "broker_name_snapshot": "Armstrong",
                "broker_load_reference": "PO-200",
                "stops": [
                    {"stop_type": "pickup", "sequence": 0, "city": "Boston", "state_or_province": "MA"},
                    {"stop_type": "delivery", "sequence": 1, "city": "Dallas", "state_or_province": "TX"},
                ],
            },
        }
    )
    seen: dict = {}

    async def fake_parser(*_args, **_kwargs):
        return _revised_response()

    async def inner(**kwargs):
        seen["inner"] = kwargs
        return {"changes": []}

    monkeypatch.setattr(settings, "jwt_secret", "unit-reparse-secret")

    async def no_other_load(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.services.load_parser_duplicate_precheck.find_exact_pdf_duplicate_candidates",
        no_other_load,
    )
    monkeypatch.setattr(
        "app.services.load_document_parse_orchestrator.parse_load_workspace_document_orchestrated",
        fake_parser,
    )
    monkeypatch.setattr("app.services.load_document_parse_semantic_llm.load_parser_semantic_provider", lambda: "openai")
    monkeypatch.setattr("app.services.load_document_parse_semantic_llm.load_parser_semantic_api_key", lambda: "test-key")
    monkeypatch.setattr("app.services.load_document_parse_semantic_llm.load_parser_semantic_model", lambda: "test-model")
    monkeypatch.setattr("app.services.load_document_parse_semantic_llm.openai_chat_json_schema_content", inner)
    proposal = await propose_load_reparse(
        _ReadDb(evidence),
        tenant_id=1,
        load_id=9,
        pdf_bytes=b"%PDF-revised",
        filename="revised.pdf",
    )
    assert seen["inner"]["api_key"] == "test-key"
    assert seen["inner"]["model"] == "test-model"
    assert seen["inner"]["schema_name"] == "load_reparse_changes"
    assert seen["inner"].get("input_file_bytes") is None
    assert "You are a TruckERP product parser" not in seen["inner"]["system"]
    assert "JSON 1:" in seen["inner"]["user_text"]
    rate_review = next(item for item in proposal["changes"] if item["field"] == "rate")
    assert rate_review["editable"] is True
    assert rate_review["current_value"] == "10"
    assert Decimal(rate_review["revised_value"]) == Decimal("2550")
    assert proposal["integrity"]


def _signed_update(
    monkeypatch: pytest.MonkeyPatch,
    document: dict,
    pdf: bytes,
    baseline: dict,
    *,
    acknowledgement_required: bool = False,
    expires_at: int | None = None,
) -> tuple[LoadUpdate, str, int]:
    monkeypatch.setattr(settings, "jwt_secret", "unit-reparse-secret")
    expires = int(time.time()) + 600 if expires_at is None else expires_at
    token = reparse_integrity_token(
        tenant_id=1,
        load_id=9,
        pdf_bytes=pdf,
        revised_parse=document,
        baseline=baseline,
        concurrency_version=3,
        acknowledgement_required=acknowledgement_required,
        expires_at=expires,
    )
    payload = LoadUpdate(expected_concurrency_version=3, rate=Decimal("100.00"))
    return payload, token, expires


def _plain_load() -> SimpleNamespace:
    return SimpleNamespace(
        id=9,
        tenant_id=1,
        status="draft",
        concurrency_version=4,
        rate=Decimal("100.00"),
        customer_rate=Decimal("100.00"),
        driver_id=None,
        customs_broker_id=None,
        broker_id=None,
        promotion_origin_workspace_draft_id=None,
        stops=[],
    )


@pytest.mark.asyncio
async def test_rejected_save_conflict_and_failed_commit_keep_json_and_pdfs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = b"%PDF-revised"
    baseline = {"extracted": {"rate": "100.00", "broker_name_snapshot": "Armstrong"}}
    document = {"extracted": {"rate": "100.00"}, "raw_text": "revised"}
    payload, token, expires = _signed_update(monkeypatch, document, pdf, baseline)
    storage = _Storage()
    load = _plain_load()

    async def fake_get(*_args, **_kwargs):
        return load

    monkeypatch.setattr(loads_service, "get_load", fake_get)
    monkeypatch.setattr("app.core.storage.get_storage", lambda: storage)

    class _RejectDb:
        async def scalar(self, *_args, **_kwargs):
            return SimpleNamespace(accepted_parse_json=baseline)

        async def execute(self, *_args, **_kwargs):
            raise AssertionError("rejected save must not write")

    with pytest.raises(HTTPException) as rejected:
        await loads_service.update_load(
            _RejectDb(),
            1,
            9,
            payload,
            verified_parse={"extracted": {"rate": "9999"}},
            revised_pdf_bytes=pdf,
            revised_pdf_filename="bad.pdf",
            tenant_slug="demo",
            reparse_integrity=token,
            reparse_expires_at=expires,
        )
    assert rejected.value.status_code == 422
    assert storage.saved == 0

    class _ConflictResult:
        rowcount = 0

    class _ConflictDb:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def execute(self, *_args, **_kwargs):
            self.calls.append("execute")
            return _ConflictResult()

        async def rollback(self):
            self.calls.append("rollback")

        async def scalar(self, *_args, **_kwargs):
            return SimpleNamespace(accepted_parse_json=copy.deepcopy(baseline))

        async def commit(self):
            raise AssertionError("a version conflict must not commit")

    conflict_db = _ConflictDb()
    monkeypatch.setattr(
        loads_service.LoadResponse,
        "model_validate",
        lambda _obj: SimpleNamespace(model_dump=lambda mode="json": {"id": 9}),
    )
    with pytest.raises(HTTPException) as conflict:
        await loads_service.update_load(
            conflict_db,
            1,
            9,
            payload,
            verified_parse=document,
            revised_pdf_bytes=pdf,
            revised_pdf_filename="revised.pdf",
            tenant_slug="demo",
            reparse_integrity=token,
            reparse_expires_at=expires,
        )
    assert conflict.value.status_code == 409
    assert conflict_db.calls == ["execute", "rollback"]
    assert storage.saved == 0

    prior = {"extracted": {"rate": "100.00", "unmapped_note": "stay"}, "raw_text": "active"}
    evidence = SimpleNamespace(
        storage_key="original-key",
        file_sha256="original-sha",
        filename="original.pdf",
        accepted_parse_json=copy.deepcopy(prior),
    )

    class _CommitResult:
        rowcount = 1

    class _CommitDb:
        def __init__(self) -> None:
            self.rolled_back = False

        async def execute(self, *_args, **_kwargs):
            return _CommitResult()

        async def flush(self):
            return None

        async def refresh(self, *_args, **_kwargs):
            return None

        async def scalar(self, *_args, **_kwargs):
            return evidence

        async def commit(self):
            raise RuntimeError("commit failed")

        async def rollback(self):
            self.rolled_back = True

    commit_db = _CommitDb()
    _commit_payload, commit_token, commit_expires = _signed_update(monkeypatch, document, pdf, prior)

    async def allow_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(loads_service, "_write_load_audit", allow_audit)
    with pytest.raises(RuntimeError, match="commit failed"):
        await loads_service.update_load(
            commit_db,
            1,
            9,
            _commit_payload,
            verified_parse=document,
            revised_pdf_bytes=pdf,
            revised_pdf_filename="revised.pdf",
            tenant_slug="demo",
            reparse_integrity=commit_token,
            reparse_expires_at=commit_expires,
        )
    assert commit_db.rolled_back is True
    assert evidence.accepted_parse_json == prior
    assert evidence.storage_key == "original-key"
    assert storage.deleted == []
    assert load.rate == Decimal("100.00")


def _shipment(broker: str, reference: str, pickup: tuple[str, str], delivery: tuple[str, str], **extra) -> dict:
    extracted = {
        "broker_name_snapshot": broker,
        "broker_load_reference": reference,
        "rate": extra.pop("rate", "1800"),
        "customer_rate": extra.pop("customer_rate", "1800"),
        "commodity": extra.pop("commodity", "Food"),
        "equipment_type": extra.pop("equipment", "Reefer"),
        "stops": [
            {
                "stop_type": "pickup",
                "city": pickup[0],
                "state_or_province": pickup[1],
                "appointment_date": extra.pop("pickup_date", "2026-03-01"),
                "appointment_time_text": extra.pop("pickup_time", "08:00"),
                "facility_code": extra.pop("pickup_code", "PU-1"),
            },
            {
                "stop_type": "delivery",
                "city": delivery[0],
                "state_or_province": delivery[1],
                "facility_code": extra.pop("delivery_code", "DEL-1"),
            },
        ],
        "references": extra.pop("references", [{"kind": "po", "value": reference, "source_label": "kept"}]),
    }
    extracted.update(extra)
    return {
        "context": {
            "document_type": "rate_confirmation",
            "classification_reasoning": "Carrier rate confirmation.",
            "document_date": extra.pop("document_date", "2026-03-02") if False else "2026-03-02",
        },
        "extracted": extracted,
    }


def test_ai_comparison_is_authoritative_and_validated() -> None:
    saved = {
        "extracted": {
            "rate": "1800",
            "customer_rate": "1800",
            "mode": "FTL",
            "equipment_type": "Reefer",
            "temperature_requirement": "34F",
            "broker_load_reference": "PO# 48211903",
            "stops": [
                {"stop_type": "PICKUP", "city": "Chicago", "state_or_province": "IL", "street": "100 Main"},
                {"stop_type": "DELIVERY", "city": "Dallas", "state_or_province": "TX"},
            ],
            "references": [{"kind": "po", "value": "00123"}],
        }
    }
    revised = {
        "extracted": {
            "rate": "2000",
            "customer_rate": "1800",
            "mode": "Full Truckload",
            "equipment_type": "Reefer",
            "temperature_requirement": "34 °F",
            "broker_load_reference": "48211903",
            "commodity": "only on the revised PDF",
            "stops": [
                {"stop_type": "pickup", "city": "Chicago", "state_or_province": "IL", "street": "100 Main"},
                {"stop_type": "delivery", "city": "Dallas", "state_or_province": "TX"},
            ],
            "references": [{"kind": "po", "value": "00123"}],
        }
    }
    only_rate = validate_ai_reparse_changes(
        saved,
        revised,
        [{"field": "rate", "label": "Linehaul increased", "current_value": "$1,800", "revised_value": "$2,000"}],
    )
    assert [item["field"] for item in only_rate] == ["rate"]
    assert only_rate[0]["editable"] is True
    assert only_rate[0]["current_value"] == "1800"
    assert only_rate[0]["revised_value"] == "2000"
    assert only_rate[0]["explanation"] == "Linehaul increased"
    customer_only = copy.deepcopy(revised)
    customer_only["extracted"]["rate"] = "1800"
    customer_only["extracted"]["customer_rate"] = "900"
    untouched = validate_ai_reparse_changes(
        saved,
        customer_only,
        [{"field": "customer_rate", "label": "Customer rate", "current_value": "1800", "revised_value": "900"}],
    )
    assert untouched == []

    same_money = copy.deepcopy(revised)
    same_money["extracted"]["rate"] = "1800"
    false_changes = validate_ai_reparse_changes(
        saved,
        same_money,
        [
            {"field": "mode", "label": "Mode", "current_value": "FTL", "revised_value": "Full Truckload"},
            {"field": "stops[0].stop_type", "label": "Type", "current_value": "PICKUP", "revised_value": "pickup"},
            {"field": "stops[1].stop_type", "label": "Type", "current_value": "DELIVERY", "revised_value": "delivery"},
            {"field": "temperature_requirement", "label": "Temp", "current_value": "34F", "revised_value": "34 °F"},
            {"field": "broker_load_reference", "label": "PO", "current_value": "PO# 48211903", "revised_value": "48211903"},
            {"field": "commodity", "label": "Commodity", "current_value": None, "revised_value": "only on the revised PDF"},
            {"field": "miles", "label": "Miles", "current_value": "100", "revised_value": None},
        ],
    )
    assert false_changes == []

    invented = validate_ai_reparse_changes(
        saved,
        revised,
        [{"field": "rate", "label": "Rate", "current_value": "1", "revised_value": "9999"}],
    )
    assert invented[0]["editable"] is True
    assert invented[0]["revised_value"] == "2000"
    omitted = validate_ai_reparse_changes(saved, revised, [])
    assert omitted[0]["field"] == "rate" and omitted[0]["editable"] is True

    other_city = copy.deepcopy(revised)
    other_city["extracted"]["stops"][0]["city"] = "Boston"
    other_city["extracted"]["rate"] = "1800"
    same_stop = validate_ai_reparse_changes(
        saved,
        other_city,
        [{"field": "stops[0].city", "label": "Pickup city", "current_value": "Chicago", "revised_value": "Boston"}],
    )
    assert same_stop[0]["field"] == "stops[0].city"
    assert same_stop[0]["editable"] is True
    assert same_stop[0]["revised_value"] == "Boston"
    unnamed = copy.deepcopy(saved)
    unnamed["extracted"]["stops"][0].pop("street")
    moved = copy.deepcopy(other_city)
    moved["extracted"]["stops"][0].pop("street")
    ambiguous = validate_ai_reparse_changes(
        unnamed,
        moved,
        [{"field": "stops[0].city", "label": "Pickup city", "current_value": "Chicago", "revised_value": "Boston"}],
    )
    assert ambiguous[0]["field"] == "stops.review.saved.0"
    assert ambiguous[0]["editable"] is False
    assert "stops[0].city" not in {item["field"] for item in ambiguous}

    zeros = copy.deepcopy(saved)
    plain = copy.deepcopy(revised)
    plain["extracted"]["rate"] = "1800"
    plain["extracted"]["references"] = [{"kind": "po", "value": "123"}]
    leading = validate_ai_reparse_changes(
        zeros,
        plain,
        [{"field": "references[0].value", "label": "Reference", "current_value": "00123", "revised_value": "123"}],
    )
    assert leading[0]["field"] == "references[0].value"
    assert leading[0]["editable"] is True
    assert leading[0]["revised_value"] == "123"


def test_reparse_comparison_shows_omitted_json_differences() -> None:
    saved = {
        "extracted": {
            "rate": "1800",
            "customer_rate": "1500",
            "mode": "FTL",
            "temperature_requirement": "34F",
            "broker_load_reference": "PO# 48211903",
            "stops": [
                {
                    "stop_type": "PICKUP",
                    "facility_name": "Main Dock",
                    "street": "100 Main",
                    "city": "Chicago",
                    "state_or_province": "IL",
                    "postal_code": "60601",
                    "appointment_time_text": "08:00",
                }
            ],
        }
    }
    revised = {
        "extracted": {
            "rate": "$2,000",
            "customer_rate": "2600",
            "mode": "Full Truckload",
            "temperature_requirement": "34 °F",
            "broker_load_reference": "48211903",
            "dispatcher_note": "not a verified field",
            "stops": [
                {
                    "stop_type": "pickup",
                    "facility_name": "Main Dock",
                    "street": "100 Main",
                    "city": "Boston",
                    "state_or_province": "IL",
                    "postal_code": "02101",
                    "appointment_time_text": "15:30",
                }
            ],
        }
    }
    omitted = {row["field"]: row for row in validate_ai_reparse_changes(saved, revised, [])}
    assert omitted["rate"]["editable"] is True
    assert omitted["rate"]["current_value"] == "1800"
    assert omitted["rate"]["revised_value"] == "$2,000"
    assert omitted["stops[0].appointment_time_text"]["revised_value"] == "15:30"
    assert omitted["stops[0].postal_code"]["revised_value"] == "02101"
    assert omitted["stops[0].city"]["editable"] is True
    assert omitted["stops[0].city"]["revised_value"] == "Boston"
    assert "customer_rate" not in omitted
    assert "dispatcher_note" not in omitted
    assert "mode" not in omitted
    assert "temperature_requirement" not in omitted
    assert "broker_load_reference" not in omitted

    partial = {row["field"]: row for row in validate_ai_reparse_changes(
        saved,
        revised,
        [{"field": "rate", "label": "Linehaul increased", "current_value": "$1,800", "revised_value": "$2,000"}],
    )}
    assert partial["rate"]["explanation"] == "Linehaul increased"
    assert partial["stops[0].postal_code"]["revised_value"] == "02101"
    assert partial["stops[0].appointment_time_text"]["editable"] is True

    equivalent = copy.deepcopy(revised)
    equivalent["extracted"]["rate"] = "1,800.00"
    equivalent["extracted"]["stops"][0]["city"] = "Chicago"
    equivalent["extracted"]["stops"][0]["postal_code"] = "60601"
    equivalent["extracted"]["stops"][0]["appointment_time_text"] = "08:00"
    assert validate_ai_reparse_changes(saved, equivalent, []) == []

    ambiguous_saved = copy.deepcopy(saved)
    ambiguous_revised = copy.deepcopy(revised)
    ambiguous_saved["extracted"]["stops"][0].pop("facility_name")
    ambiguous_saved["extracted"]["stops"][0].pop("street")
    ambiguous_revised["extracted"]["stops"][0].pop("facility_name")
    ambiguous_revised["extracted"]["stops"][0].pop("street")
    ambiguous = validate_ai_reparse_changes(ambiguous_saved, ambiguous_revised, [])
    assert any(row["field"] == "stops.review.saved.0" and row["editable"] is False for row in ambiguous)
    assert all(row["field"] != "stops[0].city" for row in ambiguous)

    amended_facility = copy.deepcopy(saved)
    amended_facility["extracted"]["stops"][0]["facility_name"] = "Dock A"
    amended_revised = copy.deepcopy(equivalent)
    amended_revised["extracted"]["stops"][0]["facility_name"] = "Dock B"
    amended_rows = validate_ai_reparse_changes(amended_facility, amended_revised, [])
    assert any(row["field"] == "stops[0].facility_name" and row["editable"] is True for row in amended_rows)
    assert all(not str(row["field"]).startswith("stops.review.") for row in amended_rows)

    invented = validate_ai_reparse_changes(
        saved,
        revised,
        [
            {"field": "rate", "label": "Rate", "current_value": "1", "revised_value": "9999"},
            {"field": "customer_rate", "label": "Customer rate", "current_value": "1500", "revised_value": "2600"},
            {"field": "dispatcher_note", "label": "Note", "current_value": "a", "revised_value": "b"},
        ],
    )
    invented_fields = {row["field"]: row for row in invented}
    assert invented_fields["rate"]["revised_value"] == "$2,000"
    assert "9999" not in str(invented_fields["rate"]["revised_value"])
    assert "customer_rate" not in invented_fields
    assert "dispatcher_note" not in invented_fields


def test_reparse_stop_identity_limits_editable_changes() -> None:
    city_only = validate_ai_reparse_changes(
        {"extracted": {"stops": [{"stop_type": "pickup", "city": "Chicago", "state_or_province": "IL", "postal_code": "60601"}]}},
        {"extracted": {"stops": [{"stop_type": "pickup", "city": "Chicago", "state_or_province": "IL", "postal_code": "60606"}]}},
        [],
    )
    postal = next(row for row in city_only if row["field"] == "stops[0].postal_code")
    assert postal["editable"] is False
    assert postal["current_value"] == "60601"
    assert postal["revised_value"] == "60606"
    assert "not identified confidently" in postal["explanation"]

    generic = validate_ai_reparse_changes(
        {
            "extracted": {
                "stops": [
                    {
                        "stop_type": "pickup",
                        "facility_name": "Warehouse",
                        "street": "100 Main St",
                        "city": "Chicago",
                        "state_or_province": "IL",
                    }
                ]
            }
        },
        {
            "extracted": {
                "stops": [
                    {
                        "stop_type": "pickup",
                        "facility_name": "Warehouse",
                        "street": "900 Dock Rd",
                        "city": "Boston",
                        "state_or_province": "MA",
                    }
                ]
            }
        },
        [],
    )
    generic_fields = {row["field"]: row for row in generic}
    assert generic_fields["stops[0].street"]["editable"] is False
    assert generic_fields["stops[0].street"]["revised_value"] == "900 Dock Rd"
    assert generic_fields["stops[0].city"]["editable"] is False
    assert "stops.review.saved.0" not in generic_fields

    stable = validate_ai_reparse_changes(
        {
            "extracted": {
                "customer_rate": "900",
                "stops": [
                    {
                        "stop_type": "pickup",
                        "facility_name": "Main Dock",
                        "street": "100 Main St",
                        "city": "Chicago",
                        "state_or_province": "IL",
                        "postal_code": "60601",
                        "reference_number": "PU-1",
                    }
                ],
            }
        },
        {
            "extracted": {
                "customer_rate": "1400",
                "stops": [
                    {
                        "stop_type": "pickup",
                        "facility_name": "Main Dock",
                        "street": "100 Main St",
                        "city": "Chicago",
                        "state_or_province": "IL",
                        "postal_code": "60632",
                        "reference_number": "PU-1",
                    }
                ],
            }
        },
        [],
    )
    assert stable[0]["field"] == "stops[0].postal_code"
    assert stable[0]["editable"] is True
    assert stable[0]["revised_value"] == "60632"
    assert all(row["field"] != "customer_rate" for row in stable)

    similar = validate_ai_reparse_changes(
        {
            "extracted": {
                "stops": [
                    {"stop_type": "pickup", "city": "Chicago", "state_or_province": "IL", "postal_code": "60601"},
                    {"stop_type": "pickup", "city": "Chicago", "state_or_province": "IL", "postal_code": "60602"},
                ]
            }
        },
        {
            "extracted": {
                "stops": [
                    {"stop_type": "pickup", "city": "Chicago", "state_or_province": "IL", "postal_code": "60609"},
                ]
            }
        },
        [{"field": "stops[0].postal_code", "label": "ZIP", "current_value": "60601", "revised_value": "60609"}],
    )
    assert all(row["editable"] is False for row in similar)
    assert all(row["field"] != "stops[0].postal_code" for row in similar)
    assert any(row["field"] == "stops.review.saved.0" for row in similar)
    assert any(row["field"] == "stops.review.saved.1" for row in similar)
    assert any(row["field"] == "stops.review.revised.0" for row in similar)


def test_reparse_duplicate_street_follows_the_unique_reference() -> None:
    saved_stops = [
        {
            "stop_type": "pickup",
            "street": "100 Main St",
            "reference_number": "PU-101",
            "postal_code": "60601",
            "appointment_time_text": "08:00",
        },
        {
            "stop_type": "pickup",
            "street": "100 Main St",
            "reference_number": "PU-202",
            "city": "Chicago",
            "state_or_province": "IL",
            "facility_name": "Main Dock",
            "postal_code": "60601",
            "appointment_time_text": "08:00",
        },
    ]
    revised = {
        "extracted": {
            "stops": [
                {
                    "stop_type": "pickup",
                    "street": "100 Main St",
                    "reference_number": "PU-202",
                    "city": "Boston",
                    "state_or_province": "MA",
                    "facility_name": "North Dock",
                    "postal_code": "02101",
                    "appointment_time_text": "15:30",
                }
            ]
        }
    }
    rows = {row["field"]: row for row in validate_ai_reparse_changes({"extracted": {"stops": saved_stops}}, revised, [])}
    assert rows["stops[1].postal_code"]["editable"] is True
    assert rows["stops[1].postal_code"]["revised_value"] == "02101"
    assert rows["stops[1].appointment_time_text"]["editable"] is True
    assert rows["stops[1].appointment_time_text"]["revised_value"] == "15:30"
    assert rows["stops[1].city"]["editable"] is True
    assert rows["stops[1].facility_name"]["editable"] is True
    assert "stops[0].postal_code" not in rows
    assert "stops[0].reference_number" not in rows
    assert rows["stops.review.saved.0"]["editable"] is False

    reversed_stops = list(reversed(saved_stops))
    reversed_rows = {
        row["field"]: row
        for row in validate_ai_reparse_changes({"extracted": {"stops": reversed_stops}}, revised, [])
    }
    assert reversed_rows["stops[0].postal_code"]["editable"] is True
    assert reversed_rows["stops[0].postal_code"]["revised_value"] == "02101"
    assert "stops[1].postal_code" not in reversed_rows
    assert reversed_rows["stops.review.saved.1"]["editable"] is False

    duplicate = validate_ai_reparse_changes(
        {
            "extracted": {
                "stops": [
                    {"stop_type": "pickup", "street": "100 Main St", "postal_code": "60601"},
                    {"stop_type": "pickup", "street": "100 Main St", "postal_code": "60602"},
                ]
            }
        },
        {"extracted": {"stops": [{"stop_type": "pickup", "street": "100 Main St", "postal_code": "60609"}]}},
        [],
    )
    assert all(row["editable"] is False for row in duplicate)
    assert all(not str(row["field"]).endswith("postal_code") for row in duplicate)
    assert {row["field"] for row in duplicate} >= {
        "stops.review.saved.0",
        "stops.review.saved.1",
        "stops.review.revised.0",
    }

    confirmed = {
        row["field"]: row
        for row in validate_ai_reparse_changes(
            {
                "extracted": {
                    "stops": [
                        {
                            "stop_type": "pickup",
                            "street": "100 Main St",
                            "reference_number": "PU-202",
                            "facility_name": "Main Dock",
                            "city": "Chicago",
                            "state_or_province": "IL",
                            "postal_code": "60601",
                            "appointment_time_text": "08:00",
                        }
                    ]
                }
            },
            revised,
            [],
        )
    }
    assert confirmed["stops[0].postal_code"]["editable"] is True
    assert confirmed["stops[0].appointment_time_text"]["editable"] is True
    assert confirmed["stops[0].facility_name"]["editable"] is True
    assert confirmed["stops[0].city"]["editable"] is True
    assert all(not str(field).startswith("stops.review.") for field in confirmed)

    contradicted = validate_ai_reparse_changes(
        {
            "extracted": {
                "stops": [
                    {
                        "stop_type": "pickup",
                        "street": "100 Main St",
                        "reference_number": "PU-101",
                        "postal_code": "60601",
                    }
                ]
            }
        },
        {"extracted": {"stops": [{"stop_type": "pickup", "street": "100 Main St", "reference_number": "PU-202", "postal_code": "02101"}]}},
        [],
    )
    contradicted_fields = {row["field"]: row for row in contradicted}
    assert contradicted_fields["stops[0].reference_number"]["editable"] is False
    assert contradicted_fields["stops[0].postal_code"]["editable"] is False
    assert contradicted_fields["stops[0].reference_number"]["revised_value"] == "PU-202"


def test_reparse_popup_hides_default_omissions_and_duplicate_broker_reference() -> None:
    saved = {
        "extracted": {
            "broker_load_reference": "3872125-1",
            "hazmat_flag": False,
            "temperature_requirement": "34F",
        }
    }
    po_only = {
        "extracted": {
            "broker_load_reference": "3872199-1",
            "temperature_requirement": "34F",
            "references": [{"kind": "other", "value": "3872199-1"}],
        }
    }
    po_rows = validate_ai_reparse_changes(saved, po_only, [])
    assert [row["field"] for row in po_rows] == ["broker_load_reference"]
    assert po_rows[0]["editable"] is True
    assert po_rows[0]["current_value"] == "3872125-1"
    assert po_rows[0]["revised_value"] == "3872199-1"
    assert all(row["field"] != "hazmat_flag" for row in po_rows)
    assert all(not str(row["field"]).startswith("references.review.revised.") for row in po_rows)

    omitted_temperature = validate_ai_reparse_changes(
        saved,
        {"extracted": {"broker_load_reference": "3872125-1", "hazmat_flag": False}},
        [],
    )
    assert len(omitted_temperature) == 1
    assert omitted_temperature[0]["field"] == "temperature_requirement"
    assert omitted_temperature[0]["editable"] is False
    assert omitted_temperature[0]["current_value"] == "34F"
    assert omitted_temperature[0]["revised_value"] is None
    assert "not treated as a deletion" in omitted_temperature[0]["explanation"]

    extra_saved = copy.deepcopy(saved)
    extra_saved["extracted"]["references"] = [{"kind": "po", "value": "3872125-1"}]
    extra_reference = validate_ai_reparse_changes(
        extra_saved,
        {
            "extracted": {
                "broker_load_reference": "3872125-1",
                "temperature_requirement": "34 °F",
                "hazmat_flag": None,
                "references": [
                    {"kind": "po", "value": "3872125-1"},
                    {"kind": "bol", "value": "BOL-555"},
                ],
            }
        },
        [],
    )
    assert [row["field"] for row in extra_reference] == ["references.review.revised.1"]
    assert extra_reference[0]["editable"] is False
    assert extra_reference[0]["revised_value"] == "BOL-555"

    same_po = validate_ai_reparse_changes(
        {"extracted": {"broker_load_reference": "3872125-1", "rate": "1800", "hazmat_flag": False}},
        {
            "extracted": {
                "broker_load_reference": "3872125-1",
                "rate": "2000",
                "references": [{"kind": "po", "value": "3872125-1"}],
            }
        },
        [],
    )
    assert [row["field"] for row in same_po] == ["rate"]
    assert same_po[0]["editable"] is True
    assert same_po[0]["revised_value"] == "2000"


def test_reparse_money_exception_requires_valid_both_document_amounts() -> None:
    saved = {"extracted": {"rate": "1800", "customer_rate": "1800", "temperature_requirement": "34"}}
    revised = {"extracted": {"rate": "2000", "customer_rate": None, "temperature_requirement": None}}
    proposed = [
        {"field": "rate", "label": "Rate", "current_value": "1800", "revised_value": "9999"},
        {"field": "customer_rate", "label": "Customer rate", "current_value": "1800", "revised_value": None},
        {"field": "temperature_requirement", "label": "Temperature", "current_value": "34", "revised_value": None},
    ]
    changes = validate_ai_reparse_changes(saved, revised, proposed)
    by_field = {row["field"]: row for row in changes}
    assert "customer_rate" not in by_field
    assert by_field["rate"]["editable"] is True
    assert by_field["rate"]["current_value"] == "1800"
    assert by_field["rate"]["revised_value"] == "2000"
    assert by_field["temperature_requirement"]["editable"] is False
    assert by_field["temperature_requirement"]["revised_value"] is None
    assert "not treated as a deletion" in by_field["temperature_requirement"]["explanation"]

    omitted = validate_ai_reparse_changes(saved, revised, [])
    omitted_fields = {row["field"]: row for row in omitted}
    assert omitted_fields["rate"]["editable"] is True
    assert omitted_fields["temperature_requirement"]["editable"] is False
    assert "customer_rate" not in omitted_fields

    nonnumeric = {"extracted": {"rate": "not parsed"}}
    unsafe = {row["field"]: row for row in validate_ai_reparse_changes(
        saved,
        nonnumeric,
        [{"field": "rate", "label": "Rate", "current_value": "1800", "revised_value": "not parsed"}],
    )}
    assert unsafe["rate"]["editable"] is False
    assert unsafe["rate"]["revised_value"] == "not parsed"
    assert unsafe["temperature_requirement"]["editable"] is False

    nonfinite = {"extracted": {"rate": "NaN"}}
    nonfinite_rows = {row["field"]: row for row in validate_ai_reparse_changes(saved, nonfinite, [])}
    assert nonfinite_rows["rate"]["editable"] is False

    no_rate = {"extracted": {"rate": None}}
    missing_rate = {row["field"]: row for row in validate_ai_reparse_changes(saved, no_rate, [])}
    assert missing_rate["rate"]["editable"] is False
    assert missing_rate["rate"]["revised_value"] is None
    assert "not treated as a deletion" in missing_rate["rate"]["explanation"]


def test_reparse_close_or_cancel_restores_changed_fields_and_drops_the_pdf() -> None:
    page = (ROOT / "apps/web/src/pages/LoadWorkspacePage.tsx").read_text()
    cancel = page[page.index("function cancelReparseReview") : page.index("function applyReparseChange")]
    assert "reparseFieldUndoRef.current.values()" in cancel
    assert "setReparseProposal(null);" in cancel
    assert "setReparseFile(null);" in cancel
    assert "setReparseReason(\"\");" in cancel
    assert "Nothing was changed." in cancel
    assert "saveLoadReparse" not in cancel
    assert "updateLoad" not in cancel
    start = page.index("{reparseDialogOpen && reparseProposal ? (")
    fragment = page[start : page.index("<RateConfirmationPdfPanel", start)]
    assert "onClose={cancelReparseReview}" in fragment
    dialog = (ROOT / "apps/web/src/loadWorkspace/ReparseChangesDialog.tsx").read_text()
    assert "Close" in dialog
    assert "Cancel" in dialog
    assert "puts those fields back" in dialog


def test_reparse_proposal_uses_load_update_pilot_permission() -> None:
    from app.routers.loads import router

    route = next(
        item
        for item in router.routes
        if getattr(item, "path", "").endswith("/{load_id}/rate-confirmation-reparse")
        and "POST" in getattr(item, "methods", set())
    )
    assert any(
        getattr(dep.call, "pilot_capability", None) == ("loads.records", "update")
        for dep in route.dependant.dependencies
    )


def test_reparse_gates_cover_identity_classification_and_field_differences() -> None:
    from app.services.load_workspace_draft_document import (
        align_replacement_to_form,
        assess_same_load,
        deterministic_reparse_changes,
        known_pdf_reuse_message,
        preserve_matched_reference_extras,
        reparse_document_block_reason,
    )

    armstrong = _shipment("Armstrong", "3872125-1", ("Greensboro", "NC"), ("Dallas", "TX"), rate="1800", customer_rate="1800")
    revised = _shipment("Armstrong Transport", "3872125-1", ("Greensboro", "NC"), ("Dallas", "TX"), rate="2000", customer_rate="2000")
    revised["context"].pop("document_date", None)
    identity = assess_same_load(armstrong, revised)
    assert identity["verdict"] == "strong"
    assert identity["summary"] == "Strong match — Armstrong, Load #3872125-1, pickup and delivery match. Rate changed from $1,800 to $2,000."
    assert "later" not in identity["summary"].casefold()
    assert "older" not in identity["summary"].casefold()
    equal_dates = copy.deepcopy(revised)
    equal_dates["context"]["document_date"] = armstrong["context"]["document_date"]
    equal_identity = assess_same_load(armstrong, equal_dates)
    assert equal_identity["verdict"] == "strong"
    assert "older" not in " ".join(equal_identity["reasons"]).casefold()
    omitted = deterministic_reparse_changes(armstrong, revised)
    assert any(item["field"] == "rate" and Decimal(item["revised_value"]) == Decimal("2000") for item in omitted)
    assert all(item["field"] != "customer_rate" for item in omitted)

    original_again = SimpleNamespace(file_sha256=hashlib.sha256(b"%PDF-original").hexdigest(), accepted_parse_json={})
    assert known_pdf_reuse_message(original_again, b"%PDF-original") == "This PDF is already on the Load."
    older = SimpleNamespace(
        file_sha256="original",
        accepted_parse_json={
            "_revised_pdfs": [
                {"storage_key": "r1", "sha256": hashlib.sha256(b"%PDF-old").hexdigest(), "filename": "old.pdf"},
                {"storage_key": "r2", "sha256": hashlib.sha256(b"%PDF-new").hexdigest(), "filename": "new.pdf"},
            ]
        },
    )
    assert known_pdf_reuse_message(older, b"%PDF-old") == "This is a previously accepted version, not a new revision."

    tql = _shipment("TQL", "999", ("Chicago", "IL"), ("Miami", "FL"), rate="900")
    wrong = assess_same_load(armstrong, tql)
    assert wrong["verdict"] == "blocked"
    assert wrong["summary"] == "Wrong document — the broker does not match this Load."
    tql_same_route = _shipment("TQL", "3872125-1", ("Greensboro", "NC"), ("Dallas", "TX"), rate="2000")
    same_route = assess_same_load(armstrong, tql_same_route)
    assert same_route["verdict"] == "blocked"
    assert same_route["summary"] == "Wrong document — the broker does not match this Load."
    alias_match = assess_same_load(armstrong, tql_same_route, broker_aliases=["Armstrong", "TQL"])
    assert alias_match["verdict"] != "blocked"

    fuel = {"context": {"document_type": "invoice", "classification_reasoning": "BVD fuel invoice"}, "extracted": {}}
    assert reparse_document_block_reason(fuel) == (
        "This appears to be a fuel invoice, not a carrier rate confirmation. No Load information has changed."
    )
    assert reparse_document_block_reason({"context": {}, "extracted": {}}) == (
        "This PDF could not be classified as a carrier rate confirmation. No Load information has changed."
    )

    po_change = _shipment("Armstrong", "PO-200", ("Greensboro", "NC"), ("Dallas", "TX"), rate="1800")
    po_change["context"]["document_date"] = "2026-03-05"
    po_saved = _shipment("Armstrong", "PO-100", ("Greensboro", "NC"), ("Dallas", "TX"), rate="1800")
    po_saved["context"]["document_date"] = "2026-03-01"
    po_identity = assess_same_load(po_saved, po_change)
    assert po_identity["verdict"] == "needs_confirmation"
    assert po_identity["summary"] == "Needs confirmation — PO changed, but broker, addresses and pickup dates match."
    assert po_identity["acknowledgement_required"] is True

    other_route = _shipment("Armstrong", "PO-100", ("Seattle", "WA"), ("Miami", "FL"), rate="1800")
    blocked_route = assess_same_load(po_saved, other_route)
    assert blocked_route["verdict"] == "blocked"

    later_pickup = _shipment(
        "Armstrong",
        "3872125-1",
        ("Greensboro", "NC"),
        ("Dallas", "TX"),
        rate="1800",
        pickup_date="2026-03-04",
        pickup_time="8:00 AM",
    )
    later_pickup["context"]["document_date"] = "2026-03-05"
    date_identity = assess_same_load(armstrong, later_pickup)
    assert date_identity["verdict"] == "needs_confirmation"
    date_change = deterministic_reparse_changes(armstrong, later_pickup)
    assert any(item["field"] == "stops[0].appointment_date" and item["editable"] is False for item in date_change)

    zeros = _shipment("Armstrong", "00123", ("Greensboro", "NC"), ("Dallas", "TX"), rate="1800")
    zeros["extracted"]["references"] = [{"kind": "po", "value": "00123"}]
    plain = _shipment("Armstrong", "00123", ("Greensboro", "NC"), ("Dallas", "TX"), rate="1800")
    plain["extracted"]["references"] = [{"kind": "po", "value": "123"}]
    assert any(item["field"] == "references[0].value" and item["revised_value"] == "123" for item in deterministic_reparse_changes(zeros, plain))

    reordered = _shipment("Armstrong", "3872125-1", ("Greensboro", "NC"), ("Dallas", "TX"), rate="1800")
    reordered["extracted"]["stops"] = list(reversed(reordered["extracted"]["stops"]))
    form = SimpleNamespace(
        stops=[
            SimpleNamespace(stop_type="pickup", city="Greensboro", state_or_province="NC"),
            SimpleNamespace(stop_type="delivery", city="Dallas", state_or_province="TX"),
        ]
    )
    aligned = align_replacement_to_form(reordered, form)
    assert aligned["extracted"]["stops"][0]["facility_code"] == "PU-1"
    assert aligned["extracted"]["stops"][1]["facility_code"] == "DEL-1"
    inserted = copy.deepcopy(armstrong)
    inserted["extracted"]["stops"].insert(
        1,
        {"stop_type": "pickup", "city": "Atlanta", "state_or_province": "GA", "facility_code": "EXTRA", "street": "9 New St"},
    )
    review = deterministic_reparse_changes(armstrong, inserted)
    assert any(item["editable"] is False and item["label"] == "Stop" for item in review)
    inserted_form = SimpleNamespace(
        stops=[
            SimpleNamespace(stop_type="pickup", city="Greensboro", state_or_province="NC", street=None, facility_name=None, reference_number=None),
            SimpleNamespace(stop_type="delivery", city="Dallas", state_or_province="TX", street=None, facility_name=None, reference_number=None),
        ]
    )
    kept_extra = align_replacement_to_form(inserted, inserted_form)
    assert kept_extra["extracted"]["unmatched_revised_stops"][0]["facility_code"] == "EXTRA"
    assert all(stop.get("facility_code") != "EXTRA" for stop in kept_extra["extracted"]["stops"])
    same_city = copy.deepcopy(armstrong)
    same_city["extracted"]["stops"][0]["street"] = "100 Main St"
    other_dock = copy.deepcopy(same_city)
    other_dock["extracted"]["stops"][0]["street"] = "900 Dock Rd"
    other_dock["extracted"]["stops"][0]["facility_code"] = "OTHER"
    street_identity = assess_same_load(same_city, other_dock)
    assert street_identity["verdict"] == "needs_confirmation"
    street_changes = deterministic_reparse_changes(same_city, other_dock)
    assert any(item["editable"] is False and "100 Main" in str(item["current_value"]) for item in street_changes)
    two_pickups = copy.deepcopy(armstrong)
    two_pickups["extracted"]["stops"] = [
        {"stop_type": "pickup", "city": "Chicago", "state_or_province": "IL", "facility_code": "A", "street": "1 First"},
        {"stop_type": "pickup", "city": "Chicago", "state_or_province": "IL", "facility_code": "B", "street": "2 Second"},
        two_pickups["extracted"]["stops"][1],
    ]
    swapped = copy.deepcopy(two_pickups)
    swapped["extracted"]["stops"] = [two_pickups["extracted"]["stops"][1], two_pickups["extracted"]["stops"][0], two_pickups["extracted"]["stops"][2]]
    multi_form = SimpleNamespace(
        stops=[
            SimpleNamespace(stop_type="pickup", city="Chicago", state_or_province="IL", street="1 First", facility_name=None, reference_number=None),
            SimpleNamespace(stop_type="pickup", city="Chicago", state_or_province="IL", street="2 Second", facility_name=None, reference_number=None),
            SimpleNamespace(stop_type="delivery", city="Dallas", state_or_province="TX", street=None, facility_name=None, reference_number=None),
        ]
    )
    multi_aligned = align_replacement_to_form(swapped, multi_form)
    assert multi_aligned["extracted"]["stops"][0]["facility_code"] == "A"
    assert multi_aligned["extracted"]["stops"][1]["facility_code"] == "B"
    time_only = copy.deepcopy(armstrong)
    time_only["extracted"]["stops"][0]["appointment_time_text"] = "15:30"
    time_identity = assess_same_load(armstrong, time_only)
    assert time_identity["verdict"] == "needs_confirmation"
    assert "appointment" in time_identity["summary"].casefold()
    assert any(item["field"] == "stops[0].appointment_time_text" and item["editable"] is False for item in deterministic_reparse_changes(armstrong, time_only))
    kept = {"extracted": {"references": [{"kind": "po", "value": "00123"}]}}
    preserve_matched_reference_extras(kept, {"extracted": {"references": [{"kind": "po", "value": "00123", "source_label": "kept"}]}})
    assert kept["extracted"]["references"][0]["source_label"] == "kept"


@pytest.mark.asyncio
async def test_expired_token_and_unchanged_form_still_records_pdf_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = b"%PDF-same"
    baseline = {"extracted": {"rate": "100.00"}}
    document = {"extracted": {"rate": "100.00"}, "raw_text": "same"}
    payload, token, _expires = _signed_update(monkeypatch, document, pdf, baseline, expires_at=int(time.time()) - 5)
    evidence = SimpleNamespace(accepted_parse_json=copy.deepcopy(baseline), storage_key="original-key", file_sha256="sha", filename="a.pdf")

    class _Db:
        async def scalar(self, *_args, **_kwargs):
            return evidence

        async def execute(self, *_args, **_kwargs):
            raise AssertionError("expired save must not write")

    async def fake_get(*_args, **_kwargs):
        return _plain_load()

    monkeypatch.setattr(loads_service, "get_load", fake_get)
    with pytest.raises(HTTPException) as expired:
        await loads_service.update_load(
            _Db(),
            1,
            9,
            payload,
            verified_parse=document,
            revised_pdf_bytes=pdf,
            reparse_integrity=token,
            reparse_expires_at=int(time.time()) - 5,
            tenant_slug="demo",
        )
    assert expired.value.status_code == 422
    assert "expired" in str(expired.value.detail).casefold()

    fresh_payload, fresh_token, fresh_expires = _signed_update(monkeypatch, document, pdf, baseline)
    seen: dict = {}

    async def record_audit(*_args, **kwargs):
        seen["action"] = kwargs.get("action")
        seen["context"] = kwargs.get("context_json")

    class _Ok:
        async def scalar(self, *_args, **_kwargs):
            return evidence

        async def execute(self, *_args, **_kwargs):
            return SimpleNamespace(rowcount=1)

        async def flush(self):
            return None

        async def refresh(self, *_args, **_kwargs):
            return None

        async def commit(self):
            return None

        async def rollback(self):
            raise AssertionError("successful acceptance should commit")

    monkeypatch.setattr(loads_service, "_write_load_audit", record_audit)
    monkeypatch.setattr("app.core.storage.get_storage", lambda: _Storage())
    load = _plain_load()
    load.concurrency_version = 3
    load.stops = []

    async def get_ready(*_args, **_kwargs):
        return load

    monkeypatch.setattr(loads_service, "get_load", get_ready)
    await loads_service.update_load(
        _Ok(),
        1,
        9,
        fresh_payload,
        verified_parse=document,
        revised_pdf_bytes=pdf,
        revised_pdf_filename="same.pdf",
        tenant_slug="demo",
        reparse_integrity=fresh_token,
        reparse_expires_at=fresh_expires,
        actor_user_id=7,
    )
    assert seen["action"] == "load_reparse_pdf_accepted"
    assert seen["context"]["revision_position"] == 1
    assert seen["context"]["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert "app.services.payroll" not in (ROOT / "app/services/load_document_parse_orchestrator.py").read_text()
    assert "app.routers.trips" not in (ROOT / "app/routers/loads.py").read_text()


def test_local_rate_confirmation_fixtures_stay_out_of_a_second_classifier() -> None:
    bvd = ROOT / "docs/fixtures/fuel/BVD_invoice_972201.pdf"
    armstrong = ROOT / "docs/_review/fixtures/pdf/Armstrong.pdf"
    assert bvd.is_file() and bvd.read_bytes().startswith(b"%PDF")
    assert armstrong.is_file() and armstrong.read_bytes().startswith(b"%PDF")
    page = (ROOT / "app/services/load_document_parse_orchestrator.py").read_text()
    assert "openai_chat_json_schema" in page
    assert "document_type" not in page or "reparse_document_block_reason" in page


def test_diff_does_not_touch_email_intake_or_the_original_parser() -> None:
    names = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).split()
    unexpected = sorted(set(names) - REPLACEMENT_PATHS)
    assert unexpected == []
    assert not any("email_intake" in name or name.startswith("app/services/email_") for name in names)
    assert "app/services/load_document_parse_rate_con.py" not in names
    assert "app/services/load_document_product_parser.py" not in names
