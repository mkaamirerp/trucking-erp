"""Issue I21 — tenant identity exclusion lookup failure is explicit."""

from __future__ import annotations

import pytest

from app.services.load_document_parse_rate_con import _exclusion_for_mechanical_validation
from app.services.load_parser_tenant_identity_exclusion import (
    build_load_parser_tenant_identity_exclusion_for_tenant,
)


@pytest.mark.asyncio
async def test_missing_tenant_marks_exclusion_lookup_failed():
    class _Db:
        async def scalar(self, stmt):
            return None

    out = await build_load_parser_tenant_identity_exclusion_for_tenant(_Db(), tenant_id=999999)
    assert out.get("_exclusion_lookup_failed") is True
    assert _exclusion_for_mechanical_validation(out) is None
