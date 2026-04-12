"""AAMVA / PDF417 text parsing (image decode tested indirectly via synthetic barcode strings)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

import time

from app.services.dl_pdf417 import (
    FAST_DECODE_CANDIDATE_COUNT,
    PDF417_APPLICANT_FAST_BUDGET_SEC,
    PDF417_APPLICANT_THOROUGH_FALLBACK_BUDGET_SEC,
    aamva_intake_from_pdf417_text,
    apply_pdf417_to_intake,
    decode_pdf417_barcode_with_trace,
    meaningful_license_field_count,
    _build_fast_candidates,
    _enumerate_pdf417_image_candidates,
    _extract_field_map,
)


def test_extract_field_map_single_line_compact() -> None:
    # Many decoders return one physical line with no newlines between element ids.
    text = (
        "DL"
        "DAQH010062911981"
        "DCAF"
        "DCSMOTORISTSAMPLE"
        "DACJANEQA"
        "DAD"
        "DBD20160715"
        "DBA20360115"
        "DBB19850520"
        "DAJON"
        "DCGCAN"
    )
    fields = _extract_field_map(text)
    assert fields.get("DAQ") == "H010062911981"
    assert fields.get("DCS") == "MOTORISTSAMPLE"
    assert fields.get("DAC") == "JANEQA"
    assert fields.get("DCA") == "F"
    assert fields.get("DAJ") == "ON"
    assert fields.get("DCG") == "CAN"


def test_aamva_intake_from_pdf417_text_maps_license_fields() -> None:
    text = (
        "DLDAQH010062911981DCAF^DCSMOTORISTSAMPLE^DACJANEQA^DAD^"
        "DBD20160715^DBA20360115^DBB19850520^DAJON^DCGCAN^"
    )
    payload = aamva_intake_from_pdf417_text(text)
    assert payload.get("driver_license_number") == "H010062911981"
    assert payload.get("license_region") == "ON"
    assert payload.get("license_expiry") == "2036-01-15"
    assert payload.get("license_issue_date") == "2016-07-15"
    assert payload.get("date_of_birth") == "1985-05-20"
    assert payload.get("cdl_class") == "F"
    assert payload.get("last_name") == "MOTORISTSAMPLE"
    assert payload.get("first_name") == "JANEQA"
    assert "field_sources" in payload
    assert payload.get("address_postal") is None
    assert payload.get("zip_code") is None


def test_aamva_intake_us_sets_zip_code_and_postal_from_dak() -> None:
    text = (
        "DLDAQH010062911981DCAF^DCSMOTORISTSAMPLE^DACJANEQA^DAD^"
        "DBD20160715^DBA20360115^DBB19850520^DAJTX^DCGUSA^DAK75001^"
    )
    payload = aamva_intake_from_pdf417_text(text)
    assert payload.get("address_country") == "US"
    assert payload.get("address_postal") == "75001"
    assert payload.get("zip_code") == "75001"


def test_meaningful_license_field_count_ignores_metadata() -> None:
    text = (
        "DLDAQH010062911981DCAF^DCSMOTORISTSAMPLE^DACJANEQA^DAD^"
        "DBD20160715^DBA20360115^DBB19850520^DAJON^DCGCAN^"
    )
    payload = aamva_intake_from_pdf417_text(text)
    assert meaningful_license_field_count(payload) >= 1
    assert "field_sources" in payload
    assert meaningful_license_field_count({"field_sources": {}, "pdf417_text": "x"}) == 0


def test_apply_pdf417_success_when_mapped_fields() -> None:
    text = (
        "DLDAQH010062911981DCAF^DCSMOTORISTSAMPLE^DACJANEQA^DAD^"
        "DBD20160715^DBA20360115^DBB19850520^DAJON^DCGCAN^"
    )
    out = apply_pdf417_to_intake({"step": "dl_upload"}, raw_barcode_text=text, technical_error=None)
    assert out["license_extract_status"] == "SUCCESS"
    assert out.get("driver_license_number") == "H010062911981"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("decode_succeeded") is True
    assert dbg.get("meaningful_field_count", 0) >= 1


def test_apply_pdf417_no_fields_when_no_barcode_text() -> None:
    out = apply_pdf417_to_intake({}, raw_barcode_text=None, technical_error=None)
    assert out["license_extract_status"] == "NO_FIELDS_FOUND"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("decode_succeeded") is False
    assert dbg.get("meaningful_field_count") == 0


def test_apply_pdf417_no_fields_when_text_unmapped() -> None:
    out = apply_pdf417_to_intake({}, raw_barcode_text="not an aamva payload", technical_error=None)
    assert out["license_extract_status"] == "NO_FIELDS_FOUND"
    dbg = out.get("license_extract_debug") or {}
    assert dbg.get("decode_succeeded") is True
    assert dbg.get("meaningful_field_count") == 0


def test_apply_pdf417_failed_on_technical_error() -> None:
    out = apply_pdf417_to_intake({}, raw_barcode_text=None, technical_error="decode_timeout")
    assert out["license_extract_status"] == "FAILED"
    assert out.get("license_extract_error") == "decode_timeout"


def test_preprocess_candidate_enumeration_reasonable_range() -> None:
    rgb = Image.new("RGB", (900, 1400), color=(210, 205, 200))
    candidates = _enumerate_pdf417_image_candidates(rgb)
    assert 45 <= len(candidates) <= 220


def test_fast_mode_exactly_eight_candidates() -> None:
    rgb = Image.new("RGB", (900, 1400), color=(210, 205, 200))
    fast = _build_fast_candidates(rgb)
    assert len(fast) == 8
    assert FAST_DECODE_CANDIDATE_COUNT == 8


def test_fast_only_finishes_within_budget_on_blank(tmp_path: Path) -> None:
    p = tmp_path / "blank.jpg"
    Image.new("RGB", (160, 160), "white").save(p, "JPEG")
    t0 = time.perf_counter()
    text, meta = decode_pdf417_barcode_with_trace(p, mode="fast_only")
    elapsed = time.perf_counter() - t0
    assert text is None
    assert meta.pipeline == "fast"
    assert elapsed < PDF417_APPLICANT_FAST_BUDGET_SEC + 0.85


def test_applicant_two_phase_blank_bounded_and_reports_timings(tmp_path: Path) -> None:
    p = tmp_path / "blank.jpg"
    Image.new("RGB", (160, 160), "white").save(p, "JPEG")
    t0 = time.perf_counter()
    text, meta = decode_pdf417_barcode_with_trace(p, mode="applicant_two_phase")
    elapsed = time.perf_counter() - t0
    assert text is None
    assert meta.pipeline == "fast+thorough_fallback"
    assert meta.fast_elapsed_ms is not None
    assert meta.thorough_elapsed_ms is not None
    assert meta.fast_elapsed_ms <= (PDF417_APPLICANT_FAST_BUDGET_SEC + 0.5) * 1000
    assert meta.thorough_elapsed_ms <= (PDF417_APPLICANT_THOROUGH_FALLBACK_BUDGET_SEC + 0.5) * 1000
    assert elapsed < (
        PDF417_APPLICANT_FAST_BUDGET_SEC + PDF417_APPLICANT_THOROUGH_FALLBACK_BUDGET_SEC + 1.25
    )


def test_thorough_mode_allows_many_attempts_on_blank(tmp_path: Path) -> None:
    p = tmp_path / "blank.jpg"
    Image.new("RGB", (160, 160), "white").save(p, "JPEG")
    text, meta = decode_pdf417_barcode_with_trace(p, mode="thorough")
    assert text is None
    assert meta.pipeline == "thorough"
    assert len(meta.attempts) >= 50


def test_decode_trace_on_blank_image_records_attempts(tmp_path: Path) -> None:
    p = tmp_path / "blank.jpg"
    Image.new("RGB", (160, 160), "white").save(p, "JPEG")
    text, meta = decode_pdf417_barcode_with_trace(p, mode="applicant_two_phase")
    assert text is None
    assert meta.winning_engine is None
    assert len(meta.attempts) >= 4
    assert any(a.get("engine") == "zxing" for a in meta.attempts)


def test_multiline_fallback() -> None:
    text = (
        "@\n"
        "ANSI 636000030001DL\n"
        "DAQ12345678\n"
        "DCSPUBLIC\n"
        "DACJANE\n"
        "DBA20301215\n"
        "DBD20151215\n"
        "DAJON\n"
    )
    payload = aamva_intake_from_pdf417_text(text)
    assert payload.get("driver_license_number") == "12345678"
    assert payload.get("license_region") == "ON"
