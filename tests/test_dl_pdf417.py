"""AAMVA / PDF417 text parsing (image decode tested indirectly via synthetic barcode strings)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

import pytest
import re
import time

from app.services.dl_pdf417 import (
    FAST_DECODE_CANDIDATE_COUNT,
    PDF417_APPLICANT_FAST_BUDGET_SEC,
    PDF417_APPLICANT_THOROUGH_FALLBACK_BUDGET_SEC,
    aamva_intake_from_pdf417_text,
    apply_pdf417_to_intake,
    decode_pdf417_barcode_with_trace,
    meaningful_license_field_count,
    _ZXING_TRIES_FAST,
    _ZXING_TRIES_THOROUGH,
    _binarizer_label,
    _build_fast_candidates,
    _decode_loop,
    _enumerate_pdf417_image_candidates,
    _extract_field_map,
    _parse_sex,
)


def test_ontario_dbc_day_delimiter_male() -> None:
    """DAY (eye color) must bound DBC so sex is not contaminated as '1 DAYUNK'."""
    text = "DBC1\nDAYUNK\nDAU160 cm\n"
    fields = _extract_field_map(text)
    assert fields.get("DBC") == "1"
    assert fields.get("DAY") == "UNK"
    assert fields.get("DAU") == "160 cm"
    payload = aamva_intake_from_pdf417_text(text)
    assert payload.get("sex") == "M"
    assert "eye_color" not in payload
    assert payload.get("height") == "160 cm"
    out = apply_pdf417_to_intake({}, raw_barcode_text=text, technical_error=None)
    assert out.get("sex") == "M"
    assert "sex" in (out.get("license_extract_debug") or {}).get("extracted_intake_keys", [])


def test_ontario_dbc_day_delimiter_female() -> None:
    text = "DBC2\nDAYUNK\nDAU165 cm\n"
    fields = _extract_field_map(text)
    assert fields.get("DBC") == "2"
    assert fields.get("DAY") == "UNK"
    assert fields.get("DAU") == "165 cm"
    payload = aamva_intake_from_pdf417_text(text)
    assert payload.get("sex") == "F"
    assert "eye_color" not in payload
    out = apply_pdf417_to_intake({}, raw_barcode_text=text, technical_error=None)
    assert out.get("sex") == "F"


def test_parse_sex_stays_strict_on_contaminated_dbc() -> None:
    assert _parse_sex("1") == "M"
    assert _parse_sex("2") == "F"
    assert _parse_sex("9") == "X"
    assert _parse_sex("1 DAYUNK") is None
    assert _parse_sex("2 DAYUNK") is None


def test_ontario_zxx_does_not_contaminate_dak() -> None:
    """Compact DAK immediately followed by ZOZ must not swallow the extension into postal."""
    text = "DAKN2R0N4ZOZEXTDAQH010062911981DCSMOTORISTSAMPLEDACJANEQA"
    fields = _extract_field_map(text)
    assert fields.get("DAK") == "N2R0N4"
    assert "ZOZ" not in (fields.get("DAK") or "")
    assert fields.get("DAQ") == "H010062911981"
    assert "ZOZ" not in fields
    payload = aamva_intake_from_pdf417_text(text)
    assert payload.get("address_postal") == "N2R0N4"
    assert "ZOZ" not in payload
    assert payload.get("driver_license_number") == "H010062911981"


def test_ontario_zxx_truncates_dck() -> None:
    text = (
        "DCK3088730*ZOZOAKH,TEST,NAMEZOBYZOCZOD"
        "DAQH010062911981DCSMOTORISTSAMPLEDACJANEQA"
    )
    fields = _extract_field_map(text)
    dck = fields.get("DCK") or ""
    assert dck == "3088730"
    assert "ZOZ" not in dck
    assert "ZOB" not in dck
    assert re.search(r"Z[A-Z0-9]{2}", dck) is None
    assert fields.get("DAQ") == "H010062911981"
    payload = aamva_intake_from_pdf417_text(text)
    assert "ZOZ" not in payload
    assert payload.get("driver_license_number") == "H010062911981"


def test_extract_field_map_uses_identity_not_field_count() -> None:
    """Three non-identity fields must not skip Zxx-aware segmentation / line fallback."""
    text = "DBC1DAYUNKDAU160 cmDAKN2R0N4ZOZEXT"
    fields = _extract_field_map(text)
    assert fields.get("DBC") == "1"
    assert fields.get("DAY") == "UNK"
    assert fields.get("DAK") == "N2R0N4"
    assert "ZOZ" not in (fields.get("DAK") or "")
    assert not fields.get("DAQ")
    assert not (fields.get("DCS") and fields.get("DAC"))


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


def test_global_histogram_precedes_local_average() -> None:
    thorough = [_binarizer_label(b) for b, _inv in _ZXING_TRIES_THOROUGH]
    assert thorough.index("GlobalHistogram") < thorough.index("LocalAverage")
    fast = [_binarizer_label(b) for b, _inv in _ZXING_TRIES_FAST]
    assert fast[0] == "GlobalHistogram"
    assert fast.index("GlobalHistogram") < fast.index("LocalAverage")


def test_first_global_histogram_success_stops_later_attempts(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_read(pil_image, *, binarizer, try_invert):
        calls.append(_binarizer_label(binarizer))
        if _binarizer_label(binarizer) == "GlobalHistogram":
            return "ANSI_SYNTHETIC_NO_PII"
        return None

    monkeypatch.setattr("app.services.dl_pdf417._zxing_read", fake_read)
    p = tmp_path / "blank.jpg"
    Image.new("RGB", (80, 80), "white").save(p, "JPEG")
    text, meta = decode_pdf417_barcode_with_trace(p, mode="applicant_two_phase")
    assert text == "ANSI_SYNTHETIC_NO_PII"
    assert calls == ["GlobalHistogram"]
    assert "LocalAverage" not in calls
    zxing_ok = [a for a in meta.attempts if a.get("engine") == "zxing"]
    assert len(zxing_ok) == 1
    assert zxing_ok[0].get("binarizer") == "GlobalHistogram"
    assert zxing_ok[0].get("decoded_char_count") == len("ANSI_SYNTHETIC_NO_PII")
    assert "ANSI_SYNTHETIC_NO_PII" not in str(meta.as_debug_dict())


def test_budget_skips_local_average_when_remaining_too_small(monkeypatch) -> None:
    launched: list[str] = []

    def fake_read(pil_image, *, binarizer, try_invert):
        launched.append(_binarizer_label(binarizer))
        return None

    monkeypatch.setattr("app.services.dl_pdf417._zxing_read", fake_read)
    rgb = Image.new("RGB", (24, 24), "white")
    attempts: list[dict] = []
    deadline = time.monotonic() + 0.05
    _decode_loop(
        [("full_rgb", rgb)],
        attempts,
        deadline_mon=deadline,
        zxing_tries=_ZXING_TRIES_THOROUGH,
        run_pyzbar=False,
        phase="thorough_fallback",
    )
    assert "GlobalHistogram" in launched
    assert "LocalAverage" not in launched
    assert any(a.get("skipped_due_to_budget") and a.get("binarizer") == "LocalAverage" for a in attempts)


def test_successful_decode_diagnostics_omit_barcode_payload() -> None:
    import json

    text = (
        "DLDAQH010062911981DCAF^DCSMOTORISTSAMPLE^DACJANEQA^DAD^"
        "DBD20160715^DBA20360115^DBB19850520^DAJON^DCGCAN^"
    )
    out = apply_pdf417_to_intake({"step": "dl_upload"}, raw_barcode_text=text, technical_error=None)
    dbg = out.get("license_extract_debug") or {}
    dumped = json.dumps(dbg)
    assert "pdf417_text" not in dbg
    assert "H010062911981" not in dumped
    assert "MOTORISTSAMPLE" not in dumped
    assert dbg.get("barcode_char_length") == len(text)
    assert dbg.get("meaningful_field_count", 0) >= 1
    assert out.get("driver_license_number") == "H010062911981"


_IMG0084_ORIGINAL = Path("/tmp/dl_pdf417_regress/img0084_original.jpg")
_IMG6446_PROCESSED = Path("/tmp/dl_pdf417_regress/img6446_processed.jpg")


def _assert_no_zxx_in_value(value: str | None) -> None:
    assert not re.search(r"Z[A-Z0-9]{2}", value or "")


@pytest.mark.skipif(not _IMG0084_ORIGINAL.is_file(), reason="live IMG_0084 original not on host")
def test_frozen_img0084_zxx_truncates_dck_preserves_intake() -> None:
    raw, _meta = decode_pdf417_barcode_with_trace(_IMG0084_ORIGINAL, mode="applicant_two_phase")
    assert raw
    fields = _extract_field_map(raw)
    assert fields.get("DAK") == "N2R0N4"
    _assert_no_zxx_in_value(fields.get("DAK"))
    assert fields.get("DCK")
    _assert_no_zxx_in_value(fields.get("DCK"))
    assert "ZOZ" not in fields
    payload = aamva_intake_from_pdf417_text(raw)
    out = apply_pdf417_to_intake({}, raw_barcode_text=raw, technical_error=None)
    assert out["license_extract_status"] == "SUCCESS"
    assert payload.get("sex") == "M"
    assert payload.get("license_region") == "ON"
    assert payload.get("address_postal") == "N2R0N4"
    assert payload.get("driver_license_number")
    assert payload.get("first_name")
    assert payload.get("last_name")
    assert payload.get("date_of_birth")
    assert payload.get("license_expiry")
    assert payload.get("license_issue_date")


@pytest.mark.skipif(not _IMG6446_PROCESSED.is_file(), reason="live IMG_6446 processed warp not on host")
def test_frozen_img6446_zxx_truncates_dck_preserves_intake() -> None:
    raw, _meta = decode_pdf417_barcode_with_trace(_IMG6446_PROCESSED, mode="applicant_two_phase")
    assert raw
    fields = _extract_field_map(raw)
    assert fields.get("DAK") == "N2R0N4"
    _assert_no_zxx_in_value(fields.get("DAK"))
    assert fields.get("DCK")
    _assert_no_zxx_in_value(fields.get("DCK"))
    assert "ZOZ" not in fields
    payload = aamva_intake_from_pdf417_text(raw)
    out = apply_pdf417_to_intake({}, raw_barcode_text=raw, technical_error=None)
    assert out["license_extract_status"] == "SUCCESS"
    assert payload.get("sex") == "F"
    assert payload.get("license_region") == "ON"
    assert payload.get("address_postal") == "N2R0N4"
    assert payload.get("driver_license_number")
    assert payload.get("first_name")
    assert payload.get("last_name")
    assert payload.get("date_of_birth")
    assert payload.get("license_expiry")
    assert payload.get("license_issue_date")
