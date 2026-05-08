"""Structured parse of routing_reason (intake review bridge)."""

from __future__ import annotations

from app.utils.email_intake_routing_parse import detail_json_normalized, parse_routing_reason_structured


def test_parse_primary_and_review_detail() -> None:
    raw = "intake_broker_conflicting_signals|review_detail=header_broker_vs_supplemental_global|qr_extractions=2"
    primary, detail = parse_routing_reason_structured(raw)
    assert primary == "intake_broker_conflicting_signals"
    assert detail.get("review_detail") == "header_broker_vs_supplemental_global"
    assert "qr_extractions" not in detail  # QR tail stripped before split


def test_parse_strips_trailing_qr_only() -> None:
    raw = "broker_resolve_ambiguous|qr_extractions=3"
    primary, detail = parse_routing_reason_structured(raw)
    assert primary == "broker_resolve_ambiguous"
    assert detail.get("routing_reason_full") == raw


def test_detail_normalized_sorts_keys() -> None:
    assert detail_json_normalized({"b": 1, "a": 2}) == detail_json_normalized({"a": 2, "b": 1})


def test_parse_email_intake_pdf_low_confidence_primary_pipe() -> None:
    raw = "email_pdf_not_high_confidence|gate_detail=pdf_text_extract_failed"
    primary, detail = parse_routing_reason_structured(raw)
    assert primary == "email_pdf_not_high_confidence"
    assert detail.get("gate_detail") == "pdf_text_extract_failed"


def test_parse_duplicate_pdf_tail() -> None:
    raw = (
        "duplicate_pdf_sha256|prior_load_id=99|content_sha256=abc|detection_source=pdf_sha256_match_same_tenant"
    )
    primary, detail = parse_routing_reason_structured(raw)
    assert primary == "duplicate_pdf_sha256"
    assert detail.get("prior_load_id") == "99"
    assert detail.get("content_sha256") == "abc"
    assert detail.get("detection_source") == "pdf_sha256_match_same_tenant"
