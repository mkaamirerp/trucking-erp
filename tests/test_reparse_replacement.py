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
                "unmapped_note": "changed",
                "references": [{"kind": "po", "value": "NEW"}],
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
            "unmapped_note": "keep",
            "references": [{"kind": "po", "value": "OLD"}],
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
                {"field": "rate", "label": "Rate", "current_value": "1", "revised_value": "9999"},
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
    by_field = {item["field"]: item for item in proposal["changes"]}
    assert set(by_field) == {
        "rate",
        "broker_load_reference",
        "stops[0].city",
        "temperature_requirement",
        "references[0].value",
    }
    assert Decimal(by_field["rate"]["revised_value"]) == Decimal("2550")
    assert by_field["rate"]["current_value"] == "2500"
    assert by_field["broker_load_reference"]["revised_value"] == "PO-200"
    assert by_field["references[0].value"]["revised_value"] == "NEW"
    assert by_field["references[0].value"]["editable"] is True
    assert by_field["stops[0].city"]["editable"] is True
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
    verify_reparse_integrity(
        tenant_id=1,
        load_id=9,
        pdf_bytes=b"%PDF-revised",
        revised_parse=proposal["revised_parse"].model_dump(mode="json"),
        token=proposal["integrity"],
    )
    with pytest.raises(LoadReparseError) as mismatched:
        verify_reparse_integrity(
            tenant_id=1,
            load_id=9,
            pdf_bytes=b"%PDF-other",
            revised_parse=proposal["revised_parse"].model_dump(mode="json"),
            token=proposal["integrity"],
        )
    assert mismatched.value.status_code == 422
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
    evidence = SimpleNamespace(accepted_parse_json={"extracted": {"rate": "10"}})
    seen: dict = {}

    async def fake_parser(*_args, **_kwargs):
        return _revised_response()

    async def inner(**kwargs):
        seen["inner"] = kwargs
        return {"changes": []}

    monkeypatch.setattr(settings, "jwt_secret", "unit-reparse-secret")
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
    assert proposal["integrity"]


def _signed_update(monkeypatch: pytest.MonkeyPatch, document: dict, pdf: bytes) -> tuple[LoadUpdate, str]:
    monkeypatch.setattr(settings, "jwt_secret", "unit-reparse-secret")
    token = reparse_integrity_token(tenant_id=1, load_id=9, pdf_bytes=pdf, revised_parse=document)
    payload = LoadUpdate(expected_concurrency_version=3, rate=Decimal("100.00"))
    return payload, token


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
    document = {"extracted": {"rate": "100.00"}, "raw_text": "revised"}
    payload, token = _signed_update(monkeypatch, document, pdf)
    storage = _Storage()
    load = _plain_load()

    async def fake_get(*_args, **_kwargs):
        return load

    monkeypatch.setattr(loads_service, "get_load", fake_get)
    monkeypatch.setattr("app.core.storage.get_storage", lambda: storage)

    class _RejectDb:
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
            raise AssertionError("a version conflict must not replace the JSON")

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
    with pytest.raises(RuntimeError, match="commit failed"):
        await loads_service.update_load(
            commit_db,
            1,
            9,
            payload,
            verified_parse=document,
            revised_pdf_bytes=pdf,
            revised_pdf_filename="revised.pdf",
            tenant_slug="demo",
            reparse_integrity=token,
        )
    assert commit_db.rolled_back is True
    assert evidence.accepted_parse_json == prior
    assert evidence.storage_key == "original-key"
    assert storage.deleted == []
    assert load.rate == Decimal("100.00")


def test_diff_does_not_touch_email_intake_or_the_original_parser() -> None:
    names = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).split()
    unexpected = sorted(set(names) - REPLACEMENT_PATHS)
    assert unexpected == []
    assert not any("email_intake" in name or name.startswith("app/services/email_") for name in names)
    assert "app/services/load_document_parse_rate_con.py" not in names
    assert "app/services/load_document_product_parser.py" not in names
