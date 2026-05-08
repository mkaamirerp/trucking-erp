"""Stable intake routing_reason helpers."""

from app.constants.email_intake_routing import (
    append_qr_extractions_tag,
    format_duplicate_pdf_sha256,
    format_email_intake_pdf_low_confidence,
    format_email_intake_pdf_parse_review,
    strip_qr_extractions_tag,
)


def test_format_duplicate_pdf_sha256() -> None:
    s = format_duplicate_pdf_sha256(prior_load_id=42)
    assert s == "duplicate_pdf_sha256|prior_load_id=42"
    full = format_duplicate_pdf_sha256(
        prior_load_id=7,
        content_sha256="AbcdEF",
        detection_source="pdf_sha256_match_same_tenant",
    )
    assert full == (
        "duplicate_pdf_sha256|prior_load_id=7|content_sha256=abcdef|"
        "detection_source=pdf_sha256_match_same_tenant"
    )


def test_format_email_intake_pdf_low_confidence_pipe_tail() -> None:
    assert format_email_intake_pdf_low_confidence("extracted_text_too_short") == (
        "email_pdf_not_high_confidence|gate_detail=extracted_text_too_short"
    )


def test_format_email_intake_pdf_parse_review() -> None:
    assert format_email_intake_pdf_parse_review(gate_detail="ok") == (
        "email_intake_pdf_parse_review|gate_detail=ok"
    )


def test_append_qr_extractions_tag_idempotent_strip() -> None:
    base = format_email_intake_pdf_low_confidence("x")
    tagged = append_qr_extractions_tag(base, 3)
    assert tagged.endswith("|qr_extractions=3")
    assert strip_qr_extractions_tag(tagged) == base
