from __future__ import annotations

import pytest

from app.services.toll_file_upload import TollFileUploadError, ingest_toll_upload
from app.services.toll_provider_catalog import (
    INTAKE_NOT_WIRED,
    INTAKE_WIRED,
    get_upload_provider,
    list_upload_providers,
    upload_provider_codes,
)

DROPDOWN_CODES = (
    "EZPASS",
    "PREPASS",
    "TOLLTAG",
    "EZ_TAG",
    "TXTAG",
    "PIKEPASS",
    "IPASS",
    "SUNPASS",
    "EPASS",
    "PEACH_PASS",
    "NC_QUICK_PASS",
    "KTAG",
    "FASTRAK",
    "GOOD_TO_GO",
    "EZPASS_NY",
    "EZPASS_NJ",
    "EZPASS_PA",
)


def test_upload_dropdown_includes_requested_providers() -> None:
    codes = [row.provider_code for row in list_upload_providers()]
    for code in DROPDOWN_CODES:
        assert code in codes
    assert "WVPA" not in codes
    assert upload_provider_codes() == frozenset(codes)
    assert all(row.upload_choice for row in list_upload_providers())


def test_only_ezpass_intake_is_wired() -> None:
    ezpass = get_upload_provider("EZPASS")
    assert ezpass is not None
    assert ezpass.intake_status == INTAKE_WIRED
    for code in DROPDOWN_CODES:
        if code == "EZPASS":
            continue
        row = get_upload_provider(code)
        assert row is not None
        assert row.intake_status == INTAKE_NOT_WIRED
    assert get_upload_provider("WVPA") is None


@pytest.mark.asyncio
async def test_non_ezpass_dropdown_choice_is_not_wired() -> None:
    with pytest.raises(TollFileUploadError) as exc:
        await ingest_toll_upload(
            None,  # type: ignore[arg-type]
            tenant_id=1,
            tenant_slug="demo",
            filename="statement.pdf",
            body=b"%PDF-1.4 fake",
            content_type="application/pdf",
            provider_code="TOLLTAG",
            created_by="tester",
        )
    assert exc.value.code == "TOLL_PROVIDER_NOT_IMPLEMENTED"
    assert "TollTag" in exc.value.message
