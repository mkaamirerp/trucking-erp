"""
Seed realistic operational loads for a tenant (default: demo slug → platform tenant_id).

Uses the same service layer as HTTP routes (create_load, update_load, mark_load_ready,
dispatch_trips.lock_trip_prefix) so business rules, CAS, and trip minting stay honest.

Run inside API container with secrets (use bash -c, not bash -lc — login shells may drop DATABASE_URL):
  docker exec truckerp-api bash -c 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -m app.scripts.seed_demo_operational_loads'

Requires: ≥6 active drivers in the tenant. If fewer than 6 active trucks exist, the script creates
additional company trucks (unit DMO-OPS-4xx, realistic VINs) via trucks_service.create_truck.
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
from app.models.driver import Driver
from app.models.load import Load
from app.models.platform import PlatformTenant
from app.models.truck import Truck
from app.schemas.broker import BrokerContactCreateBody, BrokerCreate
from app.schemas.load import LoadCreate, LoadStopCreate, LoadUpdate
from app.schemas.truck import TruckCreate
from app.services import brokers as brokers_service
from app.services import dispatch_trips as dispatch_service
from app.services import loads as loads_service
from app.services import trucks as trucks_service

DEMO_SLUG_DEFAULT = "demo"
LOAD_PREFIX = "DEMO-OPS-"
MIN_ACTIVE_DRIVERS = 6
MIN_ACTIVE_TRUCKS = 6


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


async def _ensure_trip_prefix_locked(db: AsyncSession, tenant_id: int) -> str:
    row = await dispatch_service.get_numbering_public(db, tenant_id)
    if row and row.prefix_locked_at is not None and (row.trip_number_prefix or "").strip():
        return str(row.trip_number_prefix)
    try:
        await dispatch_service.lock_trip_prefix(db, tenant_id, "DMO")
        await db.commit()
    except HTTPException as exc:
        if exc.status_code == 409:
            await db.rollback()
        else:
            raise
    row2 = await dispatch_service.get_numbering_public(db, tenant_id)
    if not row2 or row2.prefix_locked_at is None:
        raise SystemExit(
            "Could not lock trip number prefix — set admin dispatch numbering first, then re-run."
        )
    return str(row2.trip_number_prefix)


async def _ensure_demo_trucks(db: AsyncSession, tenant_id: int, report: list[dict], minimum: int = MIN_ACTIVE_TRUCKS) -> None:
    n_active = int(
        await db.scalar(
            select(func.count())
            .select_from(Truck)
            .where(Truck.tenant_id == tenant_id, Truck.status == "active")
        )
        or 0
    )
    need = minimum - n_active
    if need <= 0:
        return
    base_unit = 401
    added = 0
    slot = 0
    while added < need and slot < need + 30:
        unit = f"DMO-OPS-{base_unit + slot}"
        vin = f"1M1AX07Y5GM{94000 + slot:05d}"
        slot += 1
        exists_u = await db.scalar(
            select(Truck.id).where(Truck.tenant_id == tenant_id, Truck.unit_number == unit).limit(1)
        )
        if exists_u:
            continue
        payload = TruckCreate(
            unit_number=unit,
            vin=vin,
            year=2022,
            make="Freightliner",
            model="Cascadia",
            status="active",
            ownership_type="company",
            notes="Fleet unit added by seed_demo_operational_loads for demo dispatch coverage.",
        )
        try:
            await trucks_service.create_truck(db, tenant_id, payload)
            added += 1
            report.append({"created_truck": unit, "vin_tail": vin[-6:]})
        except HTTPException as e:
            if e.status_code == 409:
                report.append({"truck_seed_skipped_conflict": unit, "detail": str(e.detail)})
            else:
                raise
    if added < need:
        raise SystemExit(
            f"Could not create enough demo trucks (needed {need}, created {added}). "
            "Resolve unit/VIN conflicts or add trucks manually."
        )


async def _pick_fleet(db: AsyncSession, tenant_id: int) -> tuple[list[int], list[int], list[int]]:
    dr = (
        await db.execute(
            select(Driver.id).where(Driver.tenant_id == tenant_id, Driver.is_active.is_(True)).order_by(Driver.id).limit(12)
        )
    ).scalars().all()
    tr = (
        await db.execute(
            select(Truck.id).where(Truck.tenant_id == tenant_id, Truck.status == "active").order_by(Truck.id).limit(12)
        )
    ).scalars().all()
    if len(dr) < MIN_ACTIVE_DRIVERS or len(tr) < MIN_ACTIVE_TRUCKS:
        raise SystemExit(
            f"Need at least {MIN_ACTIVE_DRIVERS} active drivers and {MIN_ACTIVE_TRUCKS} active trucks; "
            f"have {len(dr)} drivers, {len(tr)} trucks."
        )
    # trailers optional for seed; use truck only
    return [int(x) for x in dr], [int(x) for x in tr], []


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


async def _patch(
    db: AsyncSession, tenant_id: int, load_id: int, cv: int, label: str, report: list[dict], **fields: Any
) -> Any:
    payload = LoadUpdate(expected_concurrency_version=cv, **fields)
    try:
        return await loads_service.update_load(db, tenant_id, load_id, payload, source="seed")
    except HTTPException as e:
        report.append({"event": "rejected_transition", "load_id": load_id, "label": label, "detail": str(e.detail)})
        raise


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
        "unassigned": f"On board for planners. {ref} — prefer reefer unit if produce season.",
        "assigned": f"Driver briefed on appt windows. {ref} — macro logs every 4h.",
        "dispatched": f"Rolling. {ref} — track ETA vs appt; customer wants POD photos.",
        "arrived_pickup": f"At shipper gate. {ref} — check seal number vs BOL before departure.",
        "in_transit": f"Linehaul under way. {ref} — weather clear I-35; no construction delays reported.",
        "arrived_delivery": f"At consignee. {ref} — offload started; standby for lumper receipt.",
        "delivered": f"Closed clean. {ref} — POD uploaded; waiting on quick pay.",
        "issue_hold": f"HOLD: OS&D reported at delivery — seal intact but case count short2 pallets. {ref}. "
        "Claims opened with broker; do not deliver remainder until disposition.",
    }
    return notes.get(category, f"Operational note. {ref}")


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
        prefix = await _ensure_trip_prefix_locked(db, tenant_id)
        report.append({"trip_prefix_locked": prefix})
        await _ensure_demo_trucks(db, tenant_id, report)
        drivers, trucks, _ = await _pick_fleet(db, tenant_id)
        di = ti = 0

        def next_fleet() -> tuple[int, int]:
            nonlocal di, ti
            d, t = drivers[di % len(drivers)], trucks[ti % len(trucks)]
            di += 1
            ti += 1
            return d, t

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

        # Helper: full new load → ready → unassigned
        async def seed_ready_unassigned(
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
            load = await _patch(
                db,
                tenant_id,
                load.id,
                load.concurrency_version,
                "ready→unassigned",
                report,
                status="unassigned",
                internal_notes=_notes_for("unassigned", ref),
            )
            await register(load, "create_load+mark_ready+patch (unassigned)", lane_idx)
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

        # Unassigned x4 (one multi-pick)
        u_specs = [(LANES[0], 0, "UA", False), (LANES[1], 1, "UB", False), (LANES[2], 2, "UC", False), (LANES[3], 3, "UD", True)]
        for lane, idx, suf, multi in u_specs:
            await seed_ready_unassigned(lane, idx, idx, suf, multi=multi)

        # Assigned x3
        for k in range(3):
            lane = LANES[(k + 1) % len(LANES)]
            load = await seed_ready_unassigned(lane, k + 1, k + 1, f"AS{k}")
            if load is None:
                continue
            d_id, tr_id = next_fleet()
            load = await _patch(
                db,
                tenant_id,
                load.id,
                load.concurrency_version,
                "unassigned→assigned",
                report,
                driver_id=d_id,
                truck_id=tr_id,
                status="assigned",
                internal_notes=_notes_for("assigned", load.broker_load_reference or load.load_number),
            )
            seeded_rows[-1].update(
                {
                    "status": load.status,
                    "trip_number": load.trip_number,
                    "path": "create_load+mark_ready+unassigned+assign (assigned)",
                }
            )

        # Dispatched x3 (must mint trip)
        for k in range(3):
            lane = LANES[(k + 2) % len(LANES)]
            load = await seed_ready_unassigned(lane, k + 2, k + 2, f"DP{k}")
            if load is None:
                continue
            d_id, tr_id = next_fleet()
            load = await _patch(
                db,
                tenant_id,
                load.id,
                load.concurrency_version,
                "→assigned",
                report,
                driver_id=d_id,
                truck_id=tr_id,
                status="assigned",
            )
            load = await _patch(
                db,
                tenant_id,
                load.id,
                load.concurrency_version,
                "→dispatched",
                report,
                status="dispatched",
                internal_notes=_notes_for("dispatched", load.broker_load_reference or load.load_number),
            )
            seeded_rows[-1].update(
                {
                    "status": load.status,
                    "trip_number": load.trip_number,
                    "path": "…+assign+dispatch (dispatched; trip minted)",
                }
            )

        # Arrived pickup x2
        for k in range(2):
            lane = LANES[k]
            load = await seed_ready_unassigned(lane, k, k, f"AP{k}")
            if load is None:
                continue
            d_id, tr_id = next_fleet()
            load = await _patch(
                db, tenant_id, load.id, load.concurrency_version, "→assigned", report, driver_id=d_id, truck_id=tr_id, status="assigned"
            )
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→dispatched", report, status="dispatched")
            load = await _patch(
                db,
                tenant_id,
                load.id,
                load.concurrency_version,
                "→arrived_pickup",
                report,
                status="arrived_pickup",
                internal_notes=_notes_for("arrived_pickup", load.broker_load_reference or load.load_number),
            )
            seeded_rows[-1].update(
                {
                    "status": load.status,
                    "trip_number": load.trip_number,
                    "path": "…+dispatch+arrived_pickup",
                }
            )

        # In transit x3
        for k in range(3):
            lane = LANES[(k + 2) % len(LANES)]
            load = await seed_ready_unassigned(lane, k + 2, k + 2, f"IT{k}")
            if load is None:
                continue
            d_id, tr_id = next_fleet()
            load = await _patch(
                db, tenant_id, load.id, load.concurrency_version, "→assigned", report, driver_id=d_id, truck_id=tr_id, status="assigned"
            )
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→dispatched", report, status="dispatched")
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→arrived_pickup", report, status="arrived_pickup")
            load = await _patch(
                db,
                tenant_id,
                load.id,
                load.concurrency_version,
                "→in_transit",
                report,
                status="in_transit",
                internal_notes=_notes_for("in_transit", load.broker_load_reference or load.load_number),
            )
            seeded_rows[-1].update(
                {
                    "status": load.status,
                    "trip_number": load.trip_number,
                    "path": "…+arrived_pickup+in_transit",
                }
            )

        # At delivery x2
        for k in range(2):
            lane = LANES[(k + 3) % len(LANES)]
            load = await seed_ready_unassigned(lane, k + 3, k + 3, f"AD{k}")
            if load is None:
                continue
            d_id, tr_id = next_fleet()
            load = await _patch(
                db, tenant_id, load.id, load.concurrency_version, "→assigned", report, driver_id=d_id, truck_id=tr_id, status="assigned"
            )
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→dispatched", report, status="dispatched")
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→arrived_pickup", report, status="arrived_pickup")
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→in_transit", report, status="in_transit")
            load = await _patch(
                db,
                tenant_id,
                load.id,
                load.concurrency_version,
                "→arrived_delivery",
                report,
                status="arrived_delivery",
                internal_notes=_notes_for("arrived_delivery", load.broker_load_reference or load.load_number),
            )
            seeded_rows[-1].update(
                {
                    "status": load.status,
                    "trip_number": load.trip_number,
                    "path": "…+in_transit+arrived_delivery",
                }
            )

        # Delivered x3
        for k in range(3):
            lane = LANES[(k + 4) % len(LANES)]
            load = await seed_ready_unassigned(lane, k + 4, k + 4, f"DV{k}")
            if load is None:
                continue
            d_id, tr_id = next_fleet()
            load = await _patch(
                db, tenant_id, load.id, load.concurrency_version, "→assigned", report, driver_id=d_id, truck_id=tr_id, status="assigned"
            )
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→dispatched", report, status="dispatched")
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→arrived_pickup", report, status="arrived_pickup")
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→in_transit", report, status="in_transit")
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→arrived_delivery", report, status="arrived_delivery")
            load = await _patch(
                db,
                tenant_id,
                load.id,
                load.concurrency_version,
                "→delivered",
                report,
                status="delivered",
                internal_notes=_notes_for("delivered", load.broker_load_reference or load.load_number),
            )
            seeded_rows[-1].update(
                {
                    "status": load.status,
                    "trip_number": load.trip_number,
                    "path": "…+arrived_delivery+delivered",
                }
            )

        # Issue / hold x2 (from in_transit)
        for k in range(2):
            lane = LANES[(k + 1) % len(LANES)]
            load = await seed_ready_unassigned(lane, k + 1, k + 1, f"IH{k}")
            if load is None:
                continue
            d_id, tr_id = next_fleet()
            load = await _patch(
                db, tenant_id, load.id, load.concurrency_version, "→assigned", report, driver_id=d_id, truck_id=tr_id, status="assigned"
            )
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→dispatched", report, status="dispatched")
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→arrived_pickup", report, status="arrived_pickup")
            load = await _patch(db, tenant_id, load.id, load.concurrency_version, "→in_transit", report, status="in_transit")
            load = await _patch(
                db,
                tenant_id,
                load.id,
                load.concurrency_version,
                "→issue_hold",
                report,
                status="issue_hold",
                internal_notes=_notes_for("issue_hold", load.broker_load_reference or load.load_number),
            )
            seeded_rows[-1].update(
                {
                    "status": load.status,
                    "trip_number": load.trip_number,
                    "path": "…+in_transit+issue_hold",
                }
            )

        # Dispatch board verification
        board = await loads_service.list_loads_for_board(db, tenant_id=tenant_id, search=None)
        board_counts = {k: len(v) for k, v in board.items()}
        report.append(
            {
                "dispatch_board_counts_non_draft_tenant_wide": board_counts,
                "note": "Tenant-wide non-draft buckets (includes pre-existing loads, not just DEMO-OPS-).",
            }
        )
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
    print("\n=== Demo operational load seed report ===\n")
    print(f"Tenant slug: {args.slug} (platform id {tenant_id})\n")
    print("Seeded / updated loads:\n")
    for row in sorted(seeded_rows, key=lambda r: r["id"]):
        print(
            f"  id={row['id']}  {row['load_number']!r}  status={row['status']!r}  "
            f"trip={row.get('trip_number')!r}  path={row['path']}"
        )
    print("\nCreation path: all service_layer (loads_service / brokers_service / dispatch_service) — same rules as API.\n")
    print("Trip numbers: minted only on transition to dispatched (system-generated); never set manually.\n")
    if report:
        print("Other notes:", report)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
