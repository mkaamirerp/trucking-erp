"""
Seed realistic dispatch board data for tenant 'demo' (tenant_id=53).

IMPORTANT: Tenant business tables (loads, load_stops, drivers, …) live in the
per-tenant PostgreSQL database (e.g. tenant_demo), NOT in the platform DATABASE_URL.
This script must use TENANT_DATABASE_URL or ALEMBIC_TENANT_DATABASE_URL from the
same secrets the API uses — not DATABASE_URL alone.

Run inside the API container with secrets loaded, e.g.:
  docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && python /app/seed_dispatch.py'

Or copy to the container:
  docker cp seed_dispatch.py truckerp-api:/seed_dispatch.py
  docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && python /seed_dispatch.py'

Optional explicit override:
  SEED_TENANT_DATABASE_URL=postgresql://... python /app/seed_dispatch.py
"""

from __future__ import annotations

import copy
import os
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def _normalize_sync_postgres_url(url: str) -> str:
    """Match scripts/tenant_migrate_preflight.sh: async -> sync, postgres:// -> postgresql://."""
    u = url.replace("+asyncpg", "")
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://") :]
    return u


def _tenant_database_url() -> str | None:
    """Resolve URL for the tenant DB where loads/load_stops exist."""
    for key in ("SEED_TENANT_DATABASE_URL", "TENANT_DATABASE_URL", "ALEMBIC_TENANT_DATABASE_URL"):
        raw = os.environ.get(key)
        if raw:
            return _normalize_sync_postgres_url(raw.strip())
    return None


def _database_url() -> str | None:
    """Legacy fallback only — usually platform DB; do not use for tenant seeding."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    secrets_path = "/run/secrets/truckerp.env"
    if os.path.isfile(secrets_path):
        with open(secrets_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _resolve_engine_url() -> str:
    tenant = _tenant_database_url()
    if tenant:
        return tenant
    plat = _database_url()
    if not plat:
        print(
            "ERROR: No tenant DB URL. Set TENANT_DATABASE_URL or ALEMBIC_TENANT_DATABASE_URL\n"
            "       (or SEED_TENANT_DATABASE_URL). DATABASE_URL alone is the platform DB and\n"
            "       will not contain tenant loads.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        "WARNING: Using DATABASE_URL — this is normally the platform database.\n"
        "         Prefer TENANT_DATABASE_URL / ALEMBIC_TENANT_DATABASE_URL for seeding loads.",
        file=sys.stderr,
    )
    return _normalize_sync_postgres_url(
        plat.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")
    )


DATABASE_URL = _resolve_engine_url()
SYNC_URL = _normalize_sync_postgres_url(
    DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")
)

engine = create_engine(SYNC_URL)
TENANT_ID = 53  # demo tenant row id (loads.tenant_id)

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
            dict(stop_type="DROP", sequence=2, city="Atlanta", state_or_province="GA", facility_name="Atlanta Hub"),
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
            dict(stop_type="PICKUP", sequence=1, city="Dallas", state_or_province="TX", facility_name="Dallas Cold Storage"),
            dict(stop_type="DROP", sequence=2, city="Memphis", state_or_province="TN", facility_name="Memphis Warehouse"),
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
            dict(stop_type="DROP", sequence=2, city="Phoenix", state_or_province="AZ", facility_name="Phoenix Depot"),
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
            dict(stop_type="PICKUP", sequence=1, city="Denver", state_or_province="CO", facility_name="Denver Terminal"),
            dict(stop_type="DROP", sequence=2, city="Kansas City", state_or_province="MO", facility_name="KC Distribution"),
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
            dict(stop_type="PICKUP", sequence=1, city="Nashville", state_or_province="TN", facility_name="Nashville DC"),
            dict(stop_type="DROP", sequence=2, city="Charlotte", state_or_province="NC", facility_name="Charlotte Hub"),
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
            dict(stop_type="PICKUP", sequence=1, city="Houston", state_or_province="TX", facility_name="Houston Cold"),
            dict(stop_type="DROP", sequence=2, city="New Orleans", state_or_province="LA", facility_name="NOLA Warehouse"),
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
            dict(stop_type="DROP", sequence=2, city="Tampa", state_or_province="FL", facility_name="Tampa DC"),
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
            dict(stop_type="PICKUP", sequence=1, city="Seattle", state_or_province="WA", facility_name="Seattle Terminal"),
            dict(stop_type="DROP", sequence=2, city="Portland", state_or_province="OR", facility_name="Portland Hub"),
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
            dict(stop_type="DROP", sequence=2, city="Chicago", state_or_province="IL", facility_name="Chicago Hub"),
        ],
    ),
]


def run() -> None:
    with Session(engine) as session:
        # Per-tenant DB: tables live in public schema (not tenant_<id> PostgreSQL schemas).
        session.execute(text("SET search_path TO public"))

        dbname = session.execute(text("SELECT current_database()")).scalar()
        print(f"Connected: database={dbname}")

        has_loads = session.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'loads')"
            )
        ).scalar()
        if not has_loads:
            print("ERROR: Table public.loads not found. Wrong database URL (platform DB?)", file=sys.stderr)
            sys.exit(1)

        # Check for existing driver/truck/trailer to link assigned/dispatched loads
        driver_id = session.execute(text("SELECT id FROM drivers WHERE tenant_id = :tid LIMIT 1"), {"tid": TENANT_ID}).scalar()
        truck_id = session.execute(text("SELECT id FROM trucks WHERE tenant_id = :tid LIMIT 1"), {"tid": TENANT_ID}).scalar()
        trailer_id = session.execute(text("SELECT id FROM trailers WHERE tenant_id = :tid LIMIT 1"), {"tid": TENANT_ID}).scalar()

        print(f"Found: driver_id={driver_id}, truck_id={truck_id}, trailer_id={trailer_id}")

        # Remove previous seed loads to allow re-running (CASCADE removes load_stops)
        session.execute(
            text("DELETE FROM loads WHERE load_number LIKE 'L-SEED%' AND tenant_id = :tid"),
            {"tid": TENANT_ID},
        )
        session.commit()

        n_unassigned = n_assigned = n_dispatched = 0

        for load_template in LOADS:
            load = copy.deepcopy(load_template)
            stops = load.pop("stops")
            needs_driver = load["status"] in ("assigned", "dispatched")
            st = load["status"]
            if st == "unassigned":
                n_unassigned += 1
            elif st == "assigned":
                n_assigned += 1
            elif st == "dispatched":
                n_dispatched += 1

            row = session.execute(
                text(
                    """
                INSERT INTO loads (
                    tenant_id, load_number, broker_name_snapshot,
                    equipment_type, estimated_weight, rate, miles, status,
                    driver_id, truck_id, trailer_id
                ) VALUES (
                    :tenant_id, :load_number, :broker_name_snapshot,
                    :equipment_type, :estimated_weight, :rate, :miles, :status,
                    :driver_id, :truck_id, :trailer_id
                ) RETURNING id
            """
                ),
                {
                    **load,
                    "tenant_id": TENANT_ID,
                    "driver_id": driver_id if needs_driver else None,
                    "truck_id": truck_id if needs_driver else None,
                    "trailer_id": trailer_id if needs_driver else None,
                },
            )
            load_id = row.scalar()

            for stop in stops:
                session.execute(
                    text(
                        """
                    INSERT INTO load_stops (
                        tenant_id, load_id, stop_type, sequence,
                        city, state_or_province, facility_name
                    ) VALUES (
                        :tenant_id, :load_id, :stop_type, :sequence,
                        :city, :state_or_province, :facility_name
                    )
                """
                    ),
                    {**stop, "tenant_id": TENANT_ID, "load_id": load_id},
                )

            print(f"  Inserted {load['load_number']} ({load['status']}) → load_id={load_id}")

        session.commit()
        print("\n--- Summary ---")
        print(f"  database:     {dbname}")
        print(f"  tenant_id:    {TENANT_ID}")
        print(f"  unassigned:   {n_unassigned}")
        print(f"  assigned:     {n_assigned}")
        print(f"  dispatched:   {n_dispatched}")
        print("\nDone. Refresh the dispatch board.")


if __name__ == "__main__":
    run()
