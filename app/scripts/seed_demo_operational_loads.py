"""
Seed realistic commercial loads for a tenant (default: demo slug → platform tenant_id).

Uses the same service layer as HTTP routes (create_load, mark_load_ready) so business rules and CAS
stay honest. Loads are commercial truth only: this script creates draft and ready loads. It does not
write legacy Load.status operational values, Load driver/truck/trailer, or dispatch_trips — operational
demo state must be created through Trip APIs (POST /trips, Trip assignment, TripLoad membership).

Run inside API container with secrets (use bash -c, not bash -lc — login shells may drop DATABASE_URL):
  docker exec truckerp-api bash -c 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -m app.scripts.seed_demo_operational_loads'

Optional: existing freight brokers — script creates three named brokers + primary contacts if missing.

Idempotency: uses load_number prefix DEMO-OPS- (skips any load_number already in DB for this tenant).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.deps.tenant_db import open_tenant_session_by_id
from app.models.broker import Broker, BrokerContact
from app.models.load import Load
from app.models.platform import PlatformTenant
from app.schemas.broker import BrokerContactCreateBody, BrokerCreate
from app.schemas.load import LoadCreate, LoadStopCreate
from app.services import brokers as brokers_service
from app.services import loads as loads_service

DEMO_SLUG_DEFAULT = "demo"
LOAD_PREFIX = "DEMO-OPS-"


@dataclass
class Lane:
    pu_facility: str
    pu_street: str
    pu_city: str
    pu_state: str
    pu_postal: str
    pu_country: str
    dr_facility: str
    dr_street: str
    dr_city: str
    dr_state: str
    dr_postal: str
    dr_country: str
    miles: int


LANES: list[Lane] = [
    Lane(
        "H-E-B RDC",
        "4300 S Zarzamora St",
        "San Antonio",
        "TX",
        "78227",
        "US",
        "Costco Depot1089",
        "1235 W Southern Ave",
        "Mesa",
        "AZ",
        "85202",
        "US",
        1050,
    ),
    Lane(
        "Dollar General DC",
        "100 Innovation Way",
        "Alachua",
        "FL",
        "32615",
        "US",
        "Family Dollar RDC",
        "2000 Logistics Pkwy",
        "Matthews",
        "NC",
        "28105",
        "US",
        1380,
    ),
    Lane(
        "Kraft Heinz Plant",
        "801 W 1st St",
        "Davenport",
        "IA",
        "52802",
        "US",
        "Publix DC",
        "5600 Oakley Industrial Blvd",
        "Fairburn",
        "GA",
        "30213",
        "US",
        920,
    ),
    Lane(
        "Ontario Food Terminal",
        "163 The Queensway",
        "Toronto",
        "ON",
        "M8Y 1H1",
        "CA",
        "Metro Richelieu DC",
        "755 Rue Nobel",
        "Boucherville",
        "QC",
        "J4B 6H2",
        "CA",
        540,
    ),
    Lane(
        "Target RDC",
        "32330 Dowe Ave",
        "Fontana",
        "CA",
        "92336",
        "US",
        "Walmart DC 6038",
        "7000 E Lincoln Way",
        "Sparks",
        "NV",
        "89434",
        "US",
        520,
    ),
]


BROKER_SEEDS: list[dict[str, Any]] = [
    {
        "display_name": "Summit Freight Solutions",
        "legal_name": "Summit Freight Solutions LLC",
        "mc_number": "MC-884512",
        "phone": "+1-312-555-0142",
        "email": "carrier@summitfreight.example",
        "address_city": "Chicago",
        "address_region": "IL",
        "address_country": "US",
        "contact": {
            "name": "Rachel Voss",
            "role": "Carrier Sales",
            "phone": "+1-312-555-0198",
            "email": "rvoss@summitfreight.example",
        },
    },
    {
        "display_name": "Arrowline Logistics",
        "legal_name": "Arrowline Logistics Inc.",
        "mc_number": "MC-771903",
        "phone": "+1-214-555-0167",
        "email": "dispatch@arrowlinelogistics.example",
        "address_city": "Dallas",
        "address_region": "TX",
        "address_country": "US",
        "contact": {
            "name": "Marcus Delgado",
            "role": "Operations",
            "phone": "+1-214-555-0104",
            "email": "mdelgado@arrowlinelogistics.example",
        },
    },
    {
        "display_name": "Northern Star Brokerage",
        "legal_name": "Northern Star Brokerage Ltd.",
        "mc_number": "MC-992104",
        "phone": "+1-416-555-0133",
        "email": "loads@northernstar.example",
        "address_city": "Mississauga",
        "address_region": "ON",
        "address_country": "CA",
        "contact": {
            "name": "Priya Nandakumar",
            "role": "Freight Coordinator",
            "phone": "+1-416-555-0175",
            "email": "priya.n@northernstar.example",
        },
    },
]


async def _platform_tenant_id_for_slug(slug: str) -> int:
    async with AsyncSessionLocal() as pdb:
        tid = await pdb.scalar(select(PlatformTenant.id).where(PlatformTenant.slug == slug.lower()))
    if tid is None:
        raise SystemExit(f"Platform tenant slug={slug!r} not found")
    return int(tid)


async def _load_number_exists(db: AsyncSession, tenant_id: int, load_number: str) -> bool:
    q = await db.scalar(select(Load.id).where(Load.tenant_id == tenant_id, Load.load_number == load_number))
    return q is not None


async def _ensure_brokers(db: AsyncSession, tenant_id: int) -> list[tuple[int, int]]:
    """Return list of (broker_id, contact_id) for seed brokers."""
    out: list[tuple[int, int]] = []
    for spec in BROKER_SEEDS:
        name_key = spec["display_name"]
        existing = await db.scalar(
            select(Broker.id).where(Broker.tenant_id == tenant_id, Broker.display_name == name_key).limit(1)
        )
        if existing:
            bid = int(existing)
            cid = await db.scalar(
                select(BrokerContact.id)
                .where(
                    BrokerContact.tenant_id == tenant_id,
                    BrokerContact.broker_id == bid,
                    BrokerContact.is_active.is_(True),
                )
                .limit(1)
            )
            if cid is None:
                body = BrokerContactCreateBody(
                    name=spec["contact"]["name"],
                    role=spec["contact"].get("role"),
                    phone=spec["contact"].get("phone"),
                    email=spec["contact"].get("email"),
                    is_primary=True,
                )
                c = await brokers_service.create_contact(db, tenant_id, bid, body)
                cid = c.id
            out.append((bid, int(cid)))
            continue
        bc = BrokerCreate(
            display_name=spec["display_name"],
            legal_name=spec["legal_name"],
            mc_number=spec.get("mc_number"),
            phone=spec.get("phone"),
            email=spec.get("email"),
            address_city=spec.get("address_city"),
            address_region=spec.get("address_region"),
            address_country=spec.get("address_country"),
        )
        b = await brokers_service.create_broker(db, tenant_id, bc)
        body = BrokerContactCreateBody(
            name=spec["contact"]["name"],
            role=spec["contact"].get("role"),
            phone=spec["contact"].get("phone"),
            email=spec["contact"].get("email"),
            is_primary=True,
        )
        c = await brokers_service.create_contact(db, tenant_id, b.id, body)
        out.append((b.id, c.id))
    return out


def _stops_single_lane(lane: Lane, pu_day: date, dr_day: date) -> list[LoadStopCreate]:
    return [
        LoadStopCreate(
            stop_type="PICKUP",
            sequence=0,
            facility_name=lane.pu_facility,
            street=lane.pu_street,
            city=lane.pu_city,
            state_or_province=lane.pu_state,
            postal_code=lane.pu_postal,
            country=lane.pu_country,
            appointment_type="FCFS",
            appointment_date=pu_day,
            appointment_time_text="08:00–15:00",
            reference_number=f"PU-{lane.pu_city[:3].upper()}",
            notes="Check in at guard; bring PPE.",
        ),
        LoadStopCreate(
            stop_type="DROP",
            sequence=1,
            facility_name=lane.dr_facility,
            street=lane.dr_street,
            city=lane.dr_city,
            state_or_province=lane.dr_state,
            postal_code=lane.dr_postal,
            country=lane.dr_country,
            appointment_type="Appt",
            appointment_date=dr_day,
            appointment_time_text="10:00 appt",
            reference_number=f"DR-{lane.dr_city[:3].upper()}",
            notes="Lumper on site; keep seal intact.",
        ),
    ]


def _stops_multi_pick(lane: Lane, lane2: Lane, pu_day: date, mid_day: date, dr_day: date) -> list[LoadStopCreate]:
    return [
        LoadStopCreate(
            stop_type="PICKUP",
            sequence=0,
            facility_name=lane.pu_facility,
            street=lane.pu_street,
            city=lane.pu_city,
            state_or_province=lane.pu_state,
            postal_code=lane.pu_postal,
            country=lane.pu_country,
            appointment_type="FCFS",
            appointment_date=pu_day,
            appointment_time_text="07:00–12:00",
            notes="First pickup — partial.",
        ),
        LoadStopCreate(
            stop_type="PICKUP",
            sequence=1,
            facility_name=lane2.pu_facility,
            street=lane2.pu_street,
            city=lane2.pu_city,
            state_or_province=lane2.pu_state,
            postal_code=lane2.pu_postal,
            country=lane2.pu_country,
            appointment_type="FCFS",
            appointment_date=mid_day,
            appointment_time_text="13:00–17:00",
            notes="Second pickup — consolidate before linehaul.",
        ),
        LoadStopCreate(
            stop_type="DROP",
            sequence=2,
            facility_name=lane.dr_facility,
            street=lane.dr_street,
            city=lane.dr_city,
            state_or_province=lane.dr_state,
            postal_code=lane.dr_postal,
            country=lane.dr_country,
            appointment_type="Appt",
            appointment_date=dr_day,
            appointment_time_text="09:00",
            notes="Delivery appt — call receiver30 min out.",
        ),
    ]


async def _mark_ready(db: AsyncSession, tenant_id: int, load_id: int, cv: int, report: list[dict]) -> Any:
    try:
        return await loads_service.mark_load_ready(db, tenant_id, load_id, expected_concurrency_version=cv)
    except HTTPException as e:
        report.append({"event": "mark_ready_failed", "load_id": load_id, "detail": str(e.detail)})
        raise


def _notes_for(category: str, ref: str) -> str:
    notes = {
        "draft": f"Rate con pending legal review. Ref {ref}. Watch lumpers at delivery.",
        "ready": f"Carrier packet sent. {ref} — confirm TWIC if required at shipper.",
        "planning": f"Ready for trip planning. {ref} — prefer reefer unit if produce season.",
    }
    return notes.get(category, f"Commercial note. {ref}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default=os.environ.get("SEED_TENANT_SLUG", DEMO_SLUG_DEFAULT))
    args = parser.parse_args()

    tenant_id = await _platform_tenant_id_for_slug(args.slug)
    report: list[dict] = []
    seeded_rows: list[dict] = []
    seq = 0

    async for db in open_tenant_session_by_id(tenant_id):
        broker_pairs = await _ensure_brokers(db, tenant_id)
        base_day = date.today() + timedelta(days=1)

        async def register(load: Any, path: str, lane_idx: int) -> None:
            seeded_rows.append(
                {
                    "id": load.id,
                    "load_number": load.load_number,
                    "status": load.status,
                    "trip_number": load.trip_number,
                    "path": path,
                    "lane": lane_idx,
                }
            )

        # --- Draft x2 ---
        for i, lane in enumerate(LANES[:2]):
            seq += 1
            ln = f"{LOAD_PREFIX}DR-{seq:03d}"
            if await _load_number_exists(db, tenant_id, ln):
                report.append({"skipped_exists": ln})
                continue
            br_id, _c_id = broker_pairs[i % len(broker_pairs)]
            if i == 0:
                # Incomplete draft: snapshots only, no broker_load_reference, no broker_id link
                lc = LoadCreate(
                    status="draft",
                    load_number=ln,
                    broker_name_snapshot=BROKER_SEEDS[i % len(BROKER_SEEDS)]["display_name"],
                    broker_contact_name_snapshot=BROKER_SEEDS[i % len(BROKER_SEEDS)]["contact"]["name"],
                    broker_contact_phone_snapshot=BROKER_SEEDS[i % len(BROKER_SEEDS)]["contact"]["phone"],
                    internal_notes=_notes_for("draft", ln),
                    mode="Truckload",
                    equipment_type="Dry Van",
                    trailer_type="Van",
                    trailer_size="53",
                    commodity="Grocery dry",
                    estimated_weight=38_500,
                    miles=lane.miles,
                    rate=4200.0,
                    stops=_stops_single_lane(lane, base_day, base_day + timedelta(days=2)),
                )
            else:
                # Second draft: linked broker but still missing reference (incomplete)
                lc = LoadCreate(
                    status="draft",
                    load_number=ln,
                    broker_id=br_id,
                    broker_contact_id=broker_pairs[i % len(broker_pairs)][1],
                    broker_name_snapshot=BROKER_SEEDS[1]["display_name"],
                    broker_contact_name_snapshot=BROKER_SEEDS[1]["contact"]["name"],
                    internal_notes=_notes_for("draft", ln) + " Broker ref still being confirmed.",
                    mode="Truckload",
                    equipment_type="Reefer",
                    trailer_type="Reefer",
                    trailer_size="53",
                    commodity="Beverage",
                    estimated_weight=42_000,
                    miles=lane.miles,
                    rate=5100.0,
                    stops=_stops_single_lane(lane, base_day + timedelta(days=1), base_day + timedelta(days=3)),
                )
            load = await loads_service.create_load(db, tenant_id, lc)
            await register(load, "create_load (draft)", i)

        # Helper: full new load → ready (Mark ready gate); Trip planning picks it up from here.
        async def seed_ready_for_planning(
            lane: Lane, lane_idx: int, br_idx: int, ref_suffix: str, multi: bool = False
        ) -> Any:
            nonlocal seq
            seq += 1
            ln = f"{LOAD_PREFIX}{ref_suffix}-{seq:03d}"
            if await _load_number_exists(db, tenant_id, ln):
                report.append({"skipped_exists": ln})
                return None
            br_id, c_id = broker_pairs[br_idx % len(broker_pairs)]
            ref = f"REF-{ref_suffix}-{seq:04d}"
            stops = (
                _stops_multi_pick(lane, LANES[(lane_idx + 1) % len(LANES)], base_day, base_day + timedelta(days=1), base_day + timedelta(days=4))
                if multi
                else _stops_single_lane(lane, base_day, base_day + timedelta(days=3))
            )
            lc = LoadCreate(
                status="draft",
                load_number=ln,
                broker_id=br_id,
                broker_contact_id=c_id,
                broker_load_reference=ref,
                internal_notes=_notes_for("ready", ref),
                mode="Truckload",
                equipment_type="Dry Van",
                trailer_type="Van",
                trailer_size="53",
                commodity="General freight",
                estimated_weight=41_200,
                miles=lane.miles,
                rate=float(3800 + (lane.miles // 4)),
                stops=stops,
            )
            load = await loads_service.create_load(db, tenant_id, lc)
            load = await _mark_ready(db, tenant_id, load.id, load.concurrency_version, report)
            await register(load, "create_load+mark_ready (ready, planning pool)", lane_idx)
            return load

        # Ready x2 (stay ready, not unassigned)
        for j in range(2):
            lane = LANES[(2 + j) % len(LANES)]
            seq += 1
            ln = f"{LOAD_PREFIX}RD-{seq:03d}"
            if await _load_number_exists(db, tenant_id, ln):
                report.append({"skipped_exists": ln})
                continue
            br_id, c_id = broker_pairs[j % len(broker_pairs)]
            ref = f"REF-RDY-{seq:04d}"
            lc = LoadCreate(
                status="draft",
                load_number=ln,
                broker_id=br_id,
                broker_contact_id=c_id,
                broker_load_reference=ref,
                internal_notes=_notes_for("ready", ref),
                mode="Truckload",
                equipment_type="Flatbed",
                trailer_type="Flatbed",
                trailer_size="48",
                commodity="Building materials",
                estimated_weight=45_000,
                miles=lane.miles,
                rate=6200.0,
                stops=_stops_single_lane(lane, base_day + timedelta(days=j), base_day + timedelta(days=j + 4)),
            )
            load = await loads_service.create_load(db, tenant_id, lc)
            load = await _mark_ready(db, tenant_id, load.id, load.concurrency_version, report)
            await register(load, "create_load+mark_ready (ready)", 2 + j)

        # Ready for trip planning x4 (one multi-pick). Operational state is created via Trip APIs, not here.
        u_specs = [(LANES[0], 0, "UA", False), (LANES[1], 1, "UB", False), (LANES[2], 2, "UC", False), (LANES[3], 3, "UD", True)]
        for lane, idx, suf, multi in u_specs:
            await seed_ready_for_planning(lane, idx, idx, suf, multi=multi)

        demo_status_rows = (
            await db.execute(
                select(Load.status, func.count())
                .where(Load.tenant_id == tenant_id, Load.load_number.like(f"{LOAD_PREFIX}%"))
                .group_by(Load.status)
            )
        ).all()
        report.append({"demo_ops_loads_by_status": {str(r[0]): int(r[1]) for r in demo_status_rows}})

        if not seeded_rows:
            existing = (
                await db.execute(
                    select(Load.id, Load.load_number, Load.status, Load.trip_number)
                    .where(Load.tenant_id == tenant_id, Load.load_number.like(f"{LOAD_PREFIX}%"))
                    .order_by(Load.id)
                )
            ).all()
            for rid, lnum, st, trip in existing:
                seeded_rows.append(
                    {
                        "id": rid,
                        "load_number": lnum,
                        "status": st,
                        "trip_number": trip,
                        "path": "existing (idempotent re-run)",
                    }
                )

        break # single yield from open_tenant_session_by_id

    # Console report
    print("\n=== Demo commercial load seed report ===\n")
    print(f"Tenant slug: {args.slug} (platform id {tenant_id})\n")
    print("Seeded / updated loads:\n")
    for row in sorted(seeded_rows, key=lambda r: r["id"]):
        print(
            f"  id={row['id']}  {row['load_number']!r}  status={row['status']!r}  "
            f"trip={row.get('trip_number')!r}  path={row['path']}"
        )
    print("\nCreation path: all service_layer (loads_service / brokers_service) — same rules as API.\n")
    print("Loads are draft/ready only. Trips, trip numbers, and equipment are created via Trip APIs.\n")
    if report:
        print("Other notes:", report)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
