"""AAMVA / PDF417 text parsing (image decode tested indirectly via synthetic barcode strings)."""

from __future__ import annotations

from app.services.dl_pdf417 import aamva_intake_from_pdf417_text, _extract_field_map


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
