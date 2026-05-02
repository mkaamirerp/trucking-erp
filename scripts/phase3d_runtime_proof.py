#!/usr/bin/env python3
"""
Phase 3D runtime proof: real ASGI + tenant DB (run inside truckerp-api container).

**Safety:** No secrets in this file. Reads DB URL from ALEMBIC_TENANT_DATABASE_URL /
TENANT_DATABASE_URL at runtime. Performs REAL writes (trips, trip_loads, numbering, cancel)
against whatever database that URL points to — use a demo/disposable tenant only.

**Defaults:** Host `demo.truckerp.me` and SQL tenant_id **53** match the standard demo
workspace in many TruckERP installs. Override without editing the script:

  export PHASE3D_PROOF_HOST=demo.truckerp.me
  export PHASE3D_PROOF_TENANT_ID=53

Usage (from host):
  docker cp scripts/phase3d_runtime_proof.py truckerp-api:/tmp/
  docker exec truckerp-api bash -lc '
    set -a && . /run/secrets/truckerp.env && set +a &&
    export ENVIRONMENT=test TEST_BYPASS_AUTH=1 ALLOW_TENANT_RESOLUTION_SHORTCUTS=true &&
    export PYTHONPATH=/app &&
    python3 /tmp/phase3d_runtime_proof.py
  '
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

# Must be set before importing app
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("TEST_BYPASS_AUTH", "1")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.main import app  # noqa: E402
from tests.support.integration_auth import (  # noqa: E402
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)


def _j(x: Any) -> str:
    return json.dumps(x, indent=2, default=str)


async def _sql(session: AsyncSession, q: str, params: dict | None = None):
    r = await session.execute(text(q), params or {})
    rows = r.fetchall()
    cols = r.keys()
    return [dict(zip(cols, row, strict=True)) for row in rows]


async def main() -> int:
    tenant_url = os.environ.get("ALEMBIC_TENANT_DATABASE_URL") or os.environ.get("TENANT_DATABASE_URL")
    if not tenant_url:
        print("FAIL: ALEMBIC_TENANT_DATABASE_URL not set", file=sys.stderr)
        return 2

    proof_tid = int(os.environ.get("PHASE3D_PROOF_TENANT_ID", "53"))
    proof_host = (os.environ.get("PHASE3D_PROOF_HOST") or "demo.truckerp.me").strip()

    install_host_aligned_current_user_and_tenant(app)
    hdrs = {"Host": proof_host}

    engine = create_async_engine(tenant_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with Session() as sq:
            t53 = (
                await sq.execute(
                    text("SELECT COUNT(*)::int FROM loads WHERE tenant_id = :tid"),
                    {"tid": proof_tid},
                )
            ).scalar()
            if int(t53 or 0) < 1:
                print(f"FAIL: need at least one load with tenant_id={proof_tid}", file=sys.stderr)
                return 1
            nt = (
                await _sql(
                    sq,
                    "SELECT tenant_id, next_numeric, trip_number_prefix, prefix_locked_at IS NOT NULL AS locked FROM tenant_dispatch_numbering ORDER BY tenant_id",
                )
            )
            print("=== (2) tenant_dispatch_numbering BEFORE ===")
            print(_j(nt))

        trip_id = None
        trip_number = None
        load_id = None
        seq_before = None
        async with Session() as sq:
            rnum = await _sql(
                sq,
                "SELECT tenant_id, next_numeric FROM tenant_dispatch_numbering WHERE tenant_id = :tid LIMIT 1",
                {"tid": proof_tid},
            )
            seq_before = int(rnum[0]["next_numeric"]) if rnum else None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # (2)(3) Create planned trip zero loads
            r = await client.post(
                "/api/v1/trips",
                headers=hdrs,
                json={"status": "planned", "job_type": "freight_load", "load_ids": []},
            )
            print("=== POST /api/v1/trips (zero loads) ===")
            print("status:", r.status_code)
            body = r.json() if r.content else {}
            print(_j(body))
            if r.status_code != 201:
                print("FAIL: expected 201")
                return 1
            trip_id = int(body["id"])
            trip_number = body["trip_number"]

            async with Session() as sq:
                v = await _sql(
                    sq,
                    """
                    SELECT id, trip_number, status, legacy_dispatch_trip_id IS NULL AS legacy_null,
                           (SELECT COUNT(*)::int FROM trip_loads tl WHERE tl.trip_id = t.id) AS tl_count
                    FROM trips t WHERE t.id = :tid
                    """,
                    {"tid": trip_id},
                )
                print("=== (3) SQL trips row + trip_loads count ===")
                print(_j(v))

                dtc = (
                    await _sql(
                        sq,
                        "SELECT id, trip_number, load_id FROM dispatch_trips WHERE trip_number = :tn",
                        {"tn": trip_number},
                    )
                )
                print("=== (2) dispatch_trips for minted trip_number (expect []) ===")
                print(_j(dtc))

                rnum_after = await _sql(
                    sq,
                    "SELECT tenant_id, next_numeric FROM tenant_dispatch_numbering WHERE tenant_id = :tid LIMIT 1",
                    {"tid": proof_tid},
                )
                print("=== (2) tenant_dispatch_numbering AFTER create ===")
                print(_j(rnum_after))
                seq_after = int(rnum_after[0]["next_numeric"])
                if seq_before is not None and seq_after != seq_before + 1:
                    print(f"FAIL: next_numeric expected {seq_before + 1}, got {seq_after}")
                    return 1

            # pick load for proof_tid without active trip_loads on another trip
            async with Session() as sq:
                candidates = await _sql(
                    sq,
                    """
                    SELECT l.id, l.load_number, l.active_trip_id, l.status
                    FROM loads l
                    WHERE l.tenant_id = :tenant_id
                      AND NOT EXISTS (
                        SELECT 1 FROM trip_loads tl
                        WHERE tl.load_id = l.id AND tl.tenant_id = :tenant_id AND tl.removed_at IS NULL
                          AND tl.trip_id <> :trip_id
                      )
                    ORDER BY l.id DESC
                    LIMIT 5
                    """,
                    {"tenant_id": proof_tid, "trip_id": trip_id},
                )
                print(f"=== candidate loads (tenant_id={proof_tid}) ===")
                print(_j(candidates))
                if not candidates:
                    print("FAIL: no suitable load")
                    return 1
                load_id = int(candidates[0]["id"])
                load_status_before = candidates[0].get("status")

            # (4) add load
            r2 = await client.post(
                f"/api/v1/trips/{trip_id}/loads",
                headers=hdrs,
                json={"load_id": load_id, "sequence_hint": 10},
            )
            print("=== POST add load ===")
            print("status:", r2.status_code)
            print(_j(r2.json() if r2.content else {}))
            if r2.status_code != 200:
                print("FAIL: add load")
                return 1

            async with Session() as sq:
                tl = await _sql(
                    sq,
                    """
                    SELECT id, trip_id, load_id, status_within_trip, removed_at IS NULL AS active
                    FROM trip_loads WHERE trip_id = :tid AND load_id = :lid
                    ORDER BY id DESC LIMIT 2
                    """,
                    {"tid": trip_id, "lid": load_id},
                )
                print("=== (4) trip_loads rows ===")
                print(_j(tl))
                ld = await _sql(
                    sq,
                    "SELECT id, active_trip_id, status FROM loads WHERE id = :lid",
                    {"lid": load_id},
                )
                print("=== (4) load active_trip_id / status ===")
                print(_j(ld))

            # (5) duplicate same trip
            rdup = await client.post(
                f"/api/v1/trips/{trip_id}/loads",
                headers=hdrs,
                json={"load_id": load_id},
            )
            print("=== (5) duplicate same trip ===")
            print("status:", rdup.status_code, rdup.text[:500])

            # second planned trip for cross-trip duplicate
            r3 = await client.post(
                "/api/v1/trips",
                headers=hdrs,
                json={"load_ids": []},
            )
            if r3.status_code != 201:
                print("FAIL: second trip", r3.text)
                return 1
            trip2_id = int(r3.json()["id"])
            rcross = await client.post(
                f"/api/v1/trips/{trip2_id}/loads",
                headers=hdrs,
                json={"load_id": load_id},
            )
            print("=== (5) add same load to other trip ===")
            print("status:", rcross.status_code, rcross.text[:500])

            async with Session() as sq:
                active_cnt = (
                    await _sql(
                        sq,
                        """
                        SELECT COUNT(*)::int AS c FROM trip_loads
                        WHERE tenant_id = :tenant_id AND load_id = :lid AND removed_at IS NULL
                        """,
                        {"tenant_id": proof_tid, "lid": load_id},
                    )
                )[0]["c"]
                print("=== (5) active trip_loads count for load (expect 1) ===", active_cnt)
                if int(active_cnt) != 1:
                    return 1

            # (6) remove load
            rrm = await client.post(
                f"/api/v1/trips/{trip_id}/loads/{load_id}/remove",
                headers=hdrs,
            )
            print("=== (6) remove load ===")
            print("status:", rrm.status_code)
            print(_j(rrm.json() if rrm.content else {}))
            async with Session() as sq:
                tl2 = await _sql(
                    sq,
                    "SELECT id, status_within_trip, removed_at IS NOT NULL AS has_removed_at FROM trip_loads WHERE trip_id = :tid AND load_id = :lid ORDER BY id DESC",
                    {"tid": trip_id, "lid": load_id},
                )
                print("=== (6) trip_loads after remove ===")
                print(_j(tl2))
                ls = await _sql(sq, "SELECT active_trip_id, status FROM loads WHERE id = :lid", {"lid": load_id})
                print("=== (6) load after remove ===")
                print(_j(ls))
                if ls[0]["status"] != load_status_before:
                    print("FAIL: load.status changed")
                    return 1

            # (7) re-add
            r4 = await client.post(
                f"/api/v1/trips/{trip_id}/loads",
                headers=hdrs,
                json={"load_id": load_id},
            )
            print("=== (7) re-add load ===")
            print("status:", r4.status_code)
            async with Session() as sq:
                active_cnt2 = (
                    await _sql(
                        sq,
                        """
                        SELECT COUNT(*)::int AS c FROM trip_loads
                        WHERE tenant_id = :tenant_id AND trip_id = :tid AND load_id = :lid AND removed_at IS NULL
                        """,
                        {"tenant_id": proof_tid, "tid": trip_id, "lid": load_id},
                    )
                )[0]["c"]
                print("active memberships trip+load:", active_cnt2)

            # (8) cancel
            rc = await client.post(f"/api/v1/trips/{trip_id}/cancel", headers=hdrs)
            print("=== (8) cancel ===")
            print("status:", rc.status_code)
            cj = rc.json()
            print(_j(cj))
            tn_after = cj.get("trip_number")
            if tn_after != trip_number:
                print("FAIL: trip_number changed")
                return 1
            rc2 = await client.post(f"/api/v1/trips/{trip_id}/cancel", headers=hdrs)
            print("=== (8) second cancel ===")
            print("status:", rc2.status_code, rc2.text[:300])

            async with Session() as sq:
                tr = await _sql(
                    sq,
                    "SELECT status, cancelled_at IS NOT NULL AS has_cancelled, trip_number FROM trips WHERE id = :tid",
                    {"tid": trip_id},
                )
                print("=== (8) trips row ===")
                print(_j(tr))
                ld2 = await _sql(sq, "SELECT status, active_trip_id FROM loads WHERE id = :lid", {"lid": load_id})
                print("=== (8) load after cancel (status must not be cancelled) ===")
                print(_j(ld2))
                if str(ld2[0]["status"]).lower() == "cancelled":
                    print("FAIL: commercial load cancelled")
                    return 1

            # (9) list/detail
            gl = await client.get("/api/v1/trips?page=1&size=5", headers=hdrs)
            gd = await client.get(f"/api/v1/trips/{trip_id}", headers=hdrs)
            print("=== (9) GET list ===", gl.status_code)
            if gl.status_code == 200:
                items = gl.json().get("items") or []
                hit = next((x for x in items if int(x.get("id")) == trip_id), None)
                print("list item for trip:", _j(hit) if hit else "not on first page")
            print("=== (9) GET detail ===", gd.status_code)
            if gd.status_code == 200:
                dj = gd.json()
                print("detail cancelled_at:", dj.get("cancelled_at"))

        print("\n=== Phase 3D runtime proof: PASS ===")
        return 0
    finally:
        clear_current_user_and_tenant_overrides(app)
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
