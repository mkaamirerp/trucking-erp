"""Slice 2: proposed Load rate-con OpenAI handoff v2 builder (no OpenAI call)."""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any

import pytest

from app.services.load_parser_openai_handoff_v2 import (
    FORBIDDEN_DIAGNOSTIC_MARKERS,
    build_load_rate_con_openai_handoff_v2,
    build_load_rate_con_openai_handoff_v2_payload,
    build_proposed_openai_request_body_v2,
    handoff_contains_forbidden_diagnostics,
)
from app.services.load_parser_rate_con_field_rules import get_load_rate_con_field_rules


def _run(coro):
    return asyncio.run(coro)


def _sample_exclusion() -> dict[str, Any]:
    return {
        "names": ["Demo Tenant"],
        "mc_numbers": ["111"],
        "usdot_numbers": ["222"],
        "phones": ["4165550100"],
        "emails": ["ops@demo.example"],
        "email_domains": ["demo.example"],
        "addresses": [{"street": "1 Main", "city": "Toronto", "postal": "M5V1A1"}],
    }


def test_handoff_includes_exclusion_shape_without_tenant_id() -> None:
    excl = _sample_exclusion()
    excl_with_tid = {**excl, "tenant_id": 53}
    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=excl_with_tid,
        pages=[{"page_number": 1, "text": "page one"}, {"page_number": 2, "text": "page two"}],
        filename="Armstrong.pdf",
        size_bytes=100,
    )
    assert "tenant_identity_exclusion" in handoff
    te = handoff["tenant_identity_exclusion"]
    assert te == excl
    assert "tenant_id" not in te
    assert "tenant_id" not in te.keys()
    # Key must not appear as a JSON object key (substring of tenant_identity_exclusion is OK).
    assert '"tenant_id"' not in json.dumps(handoff)
    assert set(te.keys()) == {
        "names",
        "mc_numbers",
        "usdot_numbers",
        "phones",
        "emails",
        "email_domains",
        "addresses",
    }


def test_field_rules_present_with_required_sections() -> None:
    from app.services.load_parser_rate_con_field_rules import APPROVED_FIELD_RULE_KEYS

    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=_sample_exclusion(),
        pages=["only"],
        filename="x.pdf",
    )
    rules = handoff["field_rules"]["rules"]
    assert list(rules.keys()) == list(APPROVED_FIELD_RULE_KEYS)
    assert set(rules.keys()) == set(APPROVED_FIELD_RULE_KEYS)
    for key in APPROVED_FIELD_RULE_KEYS:
        assert "rules" in rules[key] and isinstance(rules[key]["rules"], list)
        assert "exclusions" not in rules[key]
    blob = json.dumps(handoff)
    assert "observed_document_terminology" not in blob
    assert "observed_examples" not in blob
    assert "broker_authority" not in rules
    assert "equipment_type" not in rules
    assert "customer_rate_guardrail" in rules
    assert "pickup_semantics" in rules
    assert "delivery_semantics" in rules
    body = build_proposed_openai_request_body_v2(handoff, model="gpt-4o-mini")
    sys_msg = body["messages"][0]["content"]
    user_msg = body["messages"][1]["content"]
    guidance = (
        "Only use field_rules as the authoritative semantic guidance for fields covered by "
        "those rules. Do not infer new business rules from the response schema itself."
    )
    assert guidance in sys_msg
    assert guidance in user_msg


def test_page_order_and_boundaries_preserved() -> None:
    pages_in = [
        {"page": 1, "text": "AAA"},
        {"page": 2, "text": "BBB"},
        {"page": 3, "text": "CCC"},
    ]
    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=_sample_exclusion(),
        pages=pages_in,
        filename="Armstrong.pdf",
    )
    pages = handoff["document"]["pages"]
    assert [p["page_number"] for p in pages] == [1, 2, 3]
    assert [p["text"] for p in pages] == ["AAA", "BBB", "CCC"]
    assert handoff["document"]["page_count"] == 3


def test_old_diagnostics_absent() -> None:
    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=_sample_exclusion(),
        pages=[{"page_number": 1, "text": "Load #1 Rate $100"}],
        filename="x.pdf",
    )
    found = handoff_contains_forbidden_diagnostics(handoff)
    assert found == [], f"unexpected markers: {found}"
    body = build_proposed_openai_request_body_v2(handoff)
    found_body = handoff_contains_forbidden_diagnostics(body)
    assert found_body == [], f"unexpected markers in request body: {found_body}"
    blob = json.dumps(body)
    for m in FORBIDDEN_DIAGNOSTIC_MARKERS:
        assert m not in blob


def test_builder_does_not_mutate_inputs() -> None:
    excl = _sample_exclusion()
    excl_copy = copy.deepcopy(excl)
    pages = [{"page_number": 1, "text": "orig"}]
    pages_copy = copy.deepcopy(pages)
    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=excl,
        pages=pages,
        filename="x.pdf",
    )
    handoff["tenant_identity_exclusion"]["names"].append("MUTATED")
    handoff["document"]["pages"][0]["text"] = "changed"
    assert excl == excl_copy
    assert pages == pages_copy


def test_serialized_payload_has_no_auth_or_api_key() -> None:
    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=_sample_exclusion(),
        pages=["t"],
        filename="x.pdf",
    )
    body = build_proposed_openai_request_body_v2(handoff)
    blob = json.dumps({"_meta": {}, "openai_request_body": body}).lower()
    for needle in ("authorization", "bearer ", "api_key", "sk-", "openai-api-key"):
        assert needle not in blob


def test_async_builder_uses_injected_cached_exclusion_loader_path() -> None:
    """Async entry calls get_load_parser_tenant_identity_exclusion (via monkeypatch)."""
    calls: list[int] = []

    async def fake_get(platform_db, *, tenant_id: int, **_kwargs):
        calls.append(tenant_id)
        return _sample_exclusion()

    import app.services.load_parser_openai_handoff_v2 as mod

    original = mod.get_load_parser_tenant_identity_exclusion
    mod.get_load_parser_tenant_identity_exclusion = fake_get  # type: ignore[assignment]
    try:
        handoff = _run(
            build_load_rate_con_openai_handoff_v2(
                None,
                tenant_id=53,
                pages=["p1", "p2"],
                filename="Armstrong.pdf",
                size_bytes=10,
            )
        )
    finally:
        mod.get_load_parser_tenant_identity_exclusion = original  # type: ignore[assignment]

    assert calls == [53]
    assert handoff["tenant_identity_exclusion"]["names"] == ["Demo Tenant"]
    assert handoff["document"]["pages"][0]["page_number"] == 1
    assert handoff["document"]["pages"][1]["text"] == "p2"


def test_field_rules_factory_is_independent_copy() -> None:
    a = get_load_rate_con_field_rules()
    b = get_load_rate_con_field_rules()
    a["rules"]["broker_company"]["meaning"] = "changed"
    assert b["rules"]["broker_company"]["meaning"] != "changed"
