"""
Seed realistic dispatch board data for tenant 'demo' (tenant_id=53).
Run from the project root inside the container:
  docker exec -i truckerp-api python /seed_dispatch.py
Or copy to server and run:
  docker cp seed_dispatch.py truckerp-api:/seed_dispatch.py
  docker exec truckerp-api python /seed_dispatch.py
"""

import os, sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

# Strip async driver prefix so psycopg2 (sync) can connect
SYNC_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")

TENANT_ID = 53  # demo tenant

engine = create_engine(
    SYNC_URL,
    connect_args={"options": f"-c search_path=tenant_{TENANT_ID},public"},
)

LOADS = [
    # UNASSIGNED
    dict(
        load_number="L-SEED001",
        broker_name_snapshot="TQL Transport",
        equipment_type="Dry Van",
        estimated_weight=42000,
        rate=2450.00,
        miles=476,
        status="unassigned",
        stops=[
            dict(stop_type="PICKUP", sequence=1, city="Chicago", state_or_province="IL", facility_name="Chicago DC"),
            dict(stop_type="DROP",   sequence=2, city="Atlanta", state_or_province="GA", facility_name="Atlanta Hub"),
        ],
    ),
    dict(
        load_number="L-SEED002",
        broker_name_snapshot="JB Hunt",
        equipment_type="Reefer",
        estimated_weight=38500,
        rate=1875.00,
        miles=452,
        status="unassigned",
        stops=[
            dict(stop_type="PICKUP", sequence=1, city="Dallas",  state_or_province="TX", facility_name="Dallas Cold Storage"),
            dict(stop_type="DROP",   sequence=2, city="Memphis", state_or_province="TN", facility_name="Memphis Warehouse"),
        ],
    ),
    dict(
        load_number="L-SEED003",
        broker_name_snapshot="CH Robinson",
        equipment_type="Flatbed",
        estimated_weight=44000,
        rate=1340.00,
        miles=371,
        status="unassigned",
        stops=[
            dict(stop_type="PICKUP", sequence=1, city="Los Angeles", state_or_province="CA", facility_name="LA Port"),
            dict(stop_type="DROP",   sequence=2, city="Phoenix",     state_or_province="AZ", facility_name="Phoenix Depot"),
        ],
    ),
    dict(
        load_number="L-SEED004",
        broker_name_snapshot="Echo Global",
        equipment_type="Dry Van",
        estimated_weight=31000,
        rate=1120.00,
        miles=602,
        status="unassigned",
        stops=[
            dict(stop_type="PICKUP", sequence=1, city="Denver",      state_or_province="CO", facility_name="Denver Terminal"),
            dict(stop_type="DROP",   sequence=2, city="Kansas City", state_or_province="MO", facility_name="KC Distribution"),
        ],
    ),
    # ASSIGNED (need driver/truck/trailer seeded first)
    dict(
        load_number="L-SEED005",
        broker_name_snapshot="TQL Transport",
        equipment_type="Dry Van",
        estimated_weight=40000,
        rate=1650.00,
        miles=408,
        status="assigned",
        stops=[
            dict(stop_type="PICKUP", sequence=1, city="Nashville",  state_or_province="TN", facility_name="Nashville DC"),
            dict(stop_type="DROP",   sequence=2, city="Charlotte",  state_or_province="NC", facility_name="Charlotte Hub"),
        ],
    ),
    dict(
        load_number="L-SEED006",
        broker_name_snapshot="Coyote Logistics",
        equipment_type="Reefer",
        estimated_weight=36000,
        rate=1290.00,
        miles=349,
        status="assigned",
        stops=[
            dict(stop_type="PICKUP", sequence=1, city="Houston",     state_or_province="TX", facility_name="Houston Cold"),
            dict(stop_type="DROP",   sequence=2, city="New Orleans", state_or_province="LA", facility_name="NOLA Warehouse"),
        ],
    ),
    # DISPATCHED
    dict(
        load_number="L-SEED007",
        broker_name_snapshot="CH Robinson",
        equipment_type="Dry Van",
        estimated_weight=33000,
        rate=780.00,
        miles=280,
        status="dispatched",
        stops=[
            dict(stop_type="PICKUP", sequence=1, city="Miami", state_or_province="FL", facility_name="Miami Port"),
            dict(stop_type="DROP",   sequence=2, city="Tampa", state_or_province="FL", facility_name="Tampa DC"),
        ],
    ),
    dict(
        load_number="L-SEED008",
        broker_name_snapshot="TQL Transport",
        equipment_type="Reefer",
        estimated_weight=39500,
        rate=620.00,
        miles=174,
        status="dispatched",
        stops=[
            dict(stop_type="PICKUP", sequence=1, city="Seattle",  state_or_province="WA", facility_name="Seattle Terminal"),
            dict(stop_type="DROP",   sequence=2, city="Portland", state_or_province="OR", facility_name="Portland Hub"),
        ],
    ),
    dict(
        load_number="L-SEED009",
        broker_name_snapshot="Convoy Inc.",
        equipment_type="Dry Van",
        estimated_weight=37000,
        rate=1100.00,
        miles=408,
        status="dispatched",
        stops=[
            dict(stop_type="PICKUP", sequence=1, city="Minneapolis", state_or_province="MN", facility_name="MSP Terminal"),
            dict(stop_type="DROP",   sequence=2, city="Chicago",     state_or_province="IL", facility_name="Chicago Hub"),
        ],
    ),
]

def run():
    with Session(engine) as session:
        # Check for existing driver/truck/trailer to link assigned/dispatched loads
        driver_id = session.execute(text("SELECT id FROM drivers LIMIT 1")).scalar()
        truck_id  = session.execute(text("SELECT id FROM trucks LIMIT 1")).scalar()
        trailer_id = session.execute(text("SELECT id FROM trailers LIMIT 1")).scalar()

        print(f"Found: driver_id={driver_id}, truck_id={truck_id}, trailer_id={trailer_id}")

        # Remove previous seed loads to allow re-running
        session.execute(text(
            "DELETE FROM loads WHERE load_number LIKE 'L-SEED%' AND tenant_id = :tid"
        ), {"tid": TENANT_ID})
        session.commit()

        for load in LOADS:
            stops = load.pop("stops")
            needs_driver = load["status"] in ("assigned", "dispatched")

            row = session.execute(text("""
                INSERT INTO loads (
                    tenant_id, load_number, broker_name_snapshot,
                    equipment_type, estimated_weight, rate, miles, status,
                    driver_id, truck_id, trailer_id
                ) VALUES (
                    :tenant_id, :load_number, :broker_name_snapshot,
                    :equipment_type, :estimated_weight, :rate, :miles, :status,
                    :driver_id, :truck_id, :trailer_id
                ) RETURNING id
            """), {
                **load,
                "tenant_id": TENANT_ID,
                "driver_id":  driver_id if needs_driver else None,
                "truck_id":   truck_id  if needs_driver else None,
                "trailer_id": trailer_id if needs_driver else None,
            })
            load_id = row.scalar()

            for stop in stops:
                session.execute(text("""
                    INSERT INTO load_stops (
                        tenant_id, load_id, stop_type, sequence,
                        city, state_or_province, facility_name
                    ) VALUES (
                        :tenant_id, :load_id, :stop_type, :sequence,
                        :city, :state_or_province, :facility_name
                    )
                """), {**stop, "tenant_id": TENANT_ID, "load_id": load_id})

            print(f"  Inserted {load['load_number']} ({load['status']}) → load_id={load_id}")

        session.commit()
        print("\nDone. Refresh the dispatch board.")

if __name__ == "__main__":
    run()
