"""Replacement re-parse: one corrected JSON, no write until Save, both PDFs stay readable."""

from __future__ import annotations

import copy
import subprocess
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.authz.routes import binding_for
from app.schemas.load import LoadStopCreate
from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services import loads as loads_service
from app.services.load_document_parse_orchestrator import propose_load_reparse
from app.services.load_workspace_draft_document import (
    extracted_fields_in_draft,
    reconcile_accepted_parse_json,
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
            "extracted": {
                "rate": "2550",
                "broker_load_reference": "PO-200",
                "temperature_requirement": "0",
                "stops": [
                    {"stop_type": "pickup", "sequence": 0, "city": "Boston"},
                    {"stop_type": "delivery", "sequence": 1, "city": "Dallas"},
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
            "broker_load_reference": "PO-100",
            "temperature_requirement": "34",
            "stops": [{"city": "Chicago"}, {"city": "Dallas"}],
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
                {"field": "rate", "label": "Rate", "current_value": "2500", "revised_value": "2550"},
                {"field": "broker_load_reference", "label": "PO number", "current_value": "PO-100", "revised_value": "PO-200"},
                {"field": "stops[0].city", "label": "Pickup city", "current_value": "Chicago", "revised_value": "Boston"},
                {"field": "temperature_requirement", "label": "Temperature", "current_value": "34", "revised_value": "0"},
                {"field": "miles", "label": "Miles", "current_value": "100", "revised_value": "100"},
            ]
        }

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
    assert "different PO" in seen["compare"]["system"]
    assert "PO-100" in seen["compare"]["user_text"]
    assert "PO-200" in seen["compare"]["user_text"]
    assert "old-revised" not in seen["compare"]["user_text"]
    assert seen["compare"]["schema_name"] == "load_reparse_changes"
    fields = {item["field"] for item in proposal["changes"]}
    assert fields == {"rate", "broker_load_reference", "stops[0].city", "temperature_requirement"}
    assert db.writes == []
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


class _Stored:
    storage_key = "tenants/demo/revised-key"
    sha256 = "abc123"
    original_filename = "revised.pdf"


class _Storage:
    def __init__(self) -> None:
        self.saved: tuple | None = None

    async def save_bytes(self, *args, **kwargs):
        self.saved = (args, kwargs)
        return _Stored()

    def delete(self, *_args, **_kwargs):
        raise AssertionError("original or previous file must not be deleted on the first revised save")


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
    replaced = await loads_service._sync_verified_parse_json(
        _SaveDb(evidence),
        1,
        load,
        only_fields=set(),
        replacement=_parser_json(),
        revised_pdf_bytes=b"%PDF-revised",
        revised_pdf_filename="revised.pdf",
        tenant_slug="demo",
    )
    assert replaced is None
    assert evidence.storage_key == "original-key"
    assert evidence.file_sha256 == "original-sha"
    verified = evidence.accepted_parse_json
    assert verified["extracted"]["broker_load_reference"] == "PO-200"
    assert Decimal(verified["extracted"]["rate"]) == Decimal("2550")
    assert verified["extracted"]["temperature_requirement"] == "28"
    assert verified["extracted"]["stops"][0]["city"] == "Boston"
    assert verified["extracted"]["stops"][1]["city"] == "Dallas"
    assert verified["extracted"]["unmapped_note"] == "parser-only"
    assert verified["_revised_pdf"]["storage_key"] == "tenants/demo/revised-key"
    assert verified["raw_text"] == "original pdf text"

    async def evidence_row(*_args, **_kwargs):
        return evidence

    monkeypatch.setattr(loads_service, "get_load_rate_confirmation_pdf_evidence", evidence_row)
    original_row, original_body = await loads_service.read_load_rate_confirmation_pdf_bytes(
        None, 1, 9, tenant_slug="demo"
    )
    revised_name, revised_body = await loads_service.read_revised_rate_confirmation_pdf_bytes(
        None, 1, 9, tenant_slug="demo"
    )
    assert original_row.storage_key == "original-key"
    assert revised_name == "revised.pdf"
    assert reads == ["original-key", "tenants/demo/revised-key"]
    assert original_body == revised_body == b"%PDF-bytes"


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


def test_diff_does_not_touch_email_intake_or_the_original_parser() -> None:
    names = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).split()
    unexpected = sorted(set(names) - REPLACEMENT_PATHS)
    assert unexpected == []
    assert not any("email_intake" in name or name.startswith("app/services/email_") for name in names)
    assert "app/services/load_document_parse_rate_con.py" not in names
    assert "app/services/load_document_product_parser.py" not in names
