"""Issue 0D — mirror catchup SQL includes tenant-safe joins (no backfill execution)."""

from pathlib import Path


def test_trip_mirror_sql_includes_tenant_id_joins():
    text = Path("app/services/trip_mirror_catchup.py").read_text(encoding="utf-8")
    assert "t.tenant_id = dt.tenant_id" in text
    assert "t.tenant_id = l.tenant_id" in text
