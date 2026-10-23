#!/usr/bin/env python3
"""Owner demo workflow smoke for §9A FMP on tenant_demo (leaves TEST_FMP data)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx

API = os.environ.get("FMP_DEMO_API_BASE", "http://127.0.0.1:8000")
HOST = "demo.truckerp.me"
TENANT_ID = 53
USER_ID = os.environ.get("FMP_DEMO_USER_ID", "164f1125-95f0-4e9f-9706-efc4bc81db50")
SV = int(os.environ.get("FMP_DEMO_SESSION_VERSION", "1"))


def _headers(token: str) -> dict[str, str]:
    return {"host": HOST, "authorization": f"Bearer {token}", "content-type": "application/json"}


async def main() -> int:
    from app.utils.jwt_auth import create_access_token

    token = create_access_token(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        tenant_slug="demo",
        roles=["TENANT_ADMIN"],
        sv=SV,
    )
    tag = f"TEST_FMP_{date.today().isoformat().replace('-', '')}"
    planned = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0).isoformat()

    async with httpx.AsyncClient(base_url=API, timeout=120.0) as client:
        # Scenario A — single load
        load_a = 574  # L-READY-ND-37e4fc21
        terminal_id = 2
        r = await client.post(
            "/api/v1/future-movement-plans",
            headers=_headers(token),
            json={
                "notes": f"{tag} scenario A unassigned",
                "pickup_terminal_id": terminal_id,
                "planned_start_at": planned,
                "lines": [{"load_id": load_a}],
            },
        )
        print("CREATE_A", r.status_code, r.text[:500])
        if r.status_code != 201:
            return 1
        plan_a = r.json()
        plan_a_id = int(plan_a["id"])
        assert plan_a.get("status") == "unassigned"
        assert plan_a.get("converted_trip_id") is None

        cv = int(plan_a.get("concurrency_version") or 1)
        r2 = await client.put(
            f"/api/v1/future-movement-plans/{plan_a_id}",
            headers=_headers(token),
            json={
                "driver_id": 7,
                "notes": f"{tag} scenario A assigned driver 7",
                "concurrency_version": cv,
            },
        )
        print("UPDATE_A", r2.status_code, r2.text[:400])
        if r2.status_code != 200:
            return 1

        idem = str(uuid.uuid4())
        r3 = await client.post(
            f"/api/v1/future-movement-plans/{plan_a_id}/convert",
            headers=_headers(token),
            json={"conversion_idempotency_key": idem},
        )
        print("CONVERT_A", r3.status_code, r3.text[:600])
        if r3.status_code != 200:
            return 1
        trip_a = r3.json()
        trip_a_num = trip_a.get("trip_number") or trip_a.get("number")

        r3b = await client.post(
            f"/api/v1/future-movement-plans/{plan_a_id}/convert",
            headers=_headers(token),
            json={"conversion_idempotency_key": idem},
        )
        print("CONVERT_A_IDEM", r3b.status_code)

        # Scenario B — multi-load (4 + 6)
        pool = [573, 572, 567, 566, 565, 563, 585, 578, 600, 623]
        plan_b1_loads = pool[:4]
        plan_b2_loads = pool[4:10]

        r4 = await client.post(
            "/api/v1/future-movement-plans",
            headers=_headers(token),
            json={
                "notes": f"{tag} scenario B plan A (4 loads)",
                "pickup_terminal_id": terminal_id,
                "planned_start_at": planned,
                "driver_id": 8,
                "lines": [{"load_id": lid} for lid in plan_b1_loads],
            },
        )
        print("CREATE_B1", r4.status_code)
        if r4.status_code != 201:
            return 1
        plan_b1_id = int(r4.json()["id"])
        r5 = await client.post(
            f"/api/v1/future-movement-plans/{plan_b1_id}/convert",
            headers=_headers(token),
            json={"conversion_idempotency_key": str(uuid.uuid4())},
        )
        print("CONVERT_B1", r5.status_code)
        trip_b1 = r5.json() if r5.status_code == 200 else {}

        r6 = await client.post(
            "/api/v1/future-movement-plans",
            headers=_headers(token),
            json={
                "notes": f"{tag} scenario B plan B (6 loads)",
                "pickup_terminal_id": terminal_id,
                "planned_start_at": planned,
                "driver_id": 9,
                "lines": [{"load_id": lid} for lid in plan_b2_loads],
            },
        )
        print("CREATE_B2", r6.status_code)
        if r6.status_code != 201:
            return 1
        plan_b2_id = int(r6.json()["id"])
        r7 = await client.post(
            f"/api/v1/future-movement-plans/{plan_b2_id}/convert",
            headers=_headers(token),
            json={"conversion_idempotency_key": str(uuid.uuid4())},
        )
        print("CONVERT_B2", r7.status_code)
        trip_b2 = r7.json() if r7.status_code == 200 else {}

        # Competing reservation 409
        r8 = await client.post(
            "/api/v1/future-movement-plans",
            headers=_headers(token),
            json={
                "notes": f"{tag} conflict probe",
                "pickup_terminal_id": terminal_id,
                "lines": [{"load_id": load_a}],
            },
        )
        print("CONFLICT_EXPECT_409", r8.status_code, r8.text[:200])

        summary = {
            "tag": tag,
            "plan_a_id": plan_a_id,
            "load_a": load_a,
            "trip_a_number": trip_a_num,
            "plan_b1_id": plan_b1_id,
            "plan_b2_id": plan_b2_id,
            "trip_b1_number": trip_b1.get("trip_number"),
            "trip_b2_number": trip_b2.get("trip_number"),
            "b1_members": [x.get("load_id") for x in (trip_b1.get("member_loads") or [])],
            "b2_members": [x.get("load_id") for x in (trip_b2.get("member_loads") or [])],
        }
        print("SUMMARY", json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
