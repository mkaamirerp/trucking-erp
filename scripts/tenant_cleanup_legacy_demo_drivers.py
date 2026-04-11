#!/usr/bin/env python3
"""
Deactivate legacy fake / orphan / duplicate operational rows in tenant `drivers`.

Uses the TENANT database only. Do not point at DATABASE_URL (platform).

Run inside API container with secrets (recommended):
  docker exec truckerp-api bash -lc \\
    'set -a && . /run/secrets/truckerp.env && set +a && cd /app && \\
 python scripts/tenant_cleanup_legacy_demo_drivers.py'

Dry-run (default): prints audit + planned deactivations, no writes.
Apply: add --apply

Idempotent: only sets is_active = false where it is currently true for targeted ids.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def _normalize_sync_url(url: str) -> str:
    u = url.strip().replace("+asyncpg", "")
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://") :]
    return u


def _resolve_tenant_url(explicit: str | None) -> str:
    if explicit:
        return _normalize_sync_url(explicit)
    for key in ("TENANT_DATABASE_URL", "ALEMBIC_TENANT_DATABASE_URL"):
        raw = os.environ.get(key)
        if raw:
            return _normalize_sync_url(raw)
    print(
        "ERROR: Set TENANT_DATABASE_URL or ALEMBIC_TENANT_DATABASE_URL to the tenant DB "
        "(postgresql://… or postgresql+asyncpg://…).\n"
        "Do not use platform DATABASE_URL.",
        file=sys.stderr,
    )
    sys.exit(2)


# Explicit demo first names called out for dispatch pollution (case-insensitive).
DEMO_FIRST_NAMES_FROZEN: frozenset[str] = frozenset({"tom", "dick", "harry"})
# Historical seed drivers in tenant_demo used *.@demo.test with no people link.
LEGACY_DEMO_EMAIL_SUFFIX: str = "@demo.test"


def _norm_first(name: str | None) -> str:
    return (name or "").strip().casefold()


def _legacy_demo_test_email(a: DriverAuditRow) -> bool:
    if a.person_id is not None:
        return False
    e = (a.email or "").strip().casefold()
    return e.endswith(LEGACY_DEMO_EMAIL_SUFFIX)


@dataclass(frozen=True)
class DriverAuditRow:
    id: int
    tenant_id: int
    person_id: int | None
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    is_active: bool
    people_exists: bool


def _fetch_audit(session: Session) -> list[DriverAuditRow]:
    q = text(
        """
        SELECT
            d.id,
            d.tenant_id,
            d.person_id,
            d.first_name,
            d.last_name,
            d.email,
            d.phone,
            d.is_active,
            (p.id IS NOT NULL) AS people_exists
        FROM drivers d
        LEFT JOIN people p
            ON p.tenant_id = d.tenant_id AND p.id = d.person_id
        ORDER BY d.tenant_id, d.id
        """
    )
    rows = session.execute(q).mappings().all()
    out: list[DriverAuditRow] = []
    for r in rows:
        out.append(
            DriverAuditRow(
                id=int(r["id"]),
                tenant_id=int(r["tenant_id"]),
                person_id=int(r["person_id"]) if r["person_id"] is not None else None,
                first_name=str(r["first_name"] or ""),
                last_name=str(r["last_name"] or ""),
                email=r["email"],
                phone=r["phone"],
                is_active=bool(r["is_active"]),
                people_exists=bool(r["people_exists"]),
            )
        )
    return out


def _classify(a: DriverAuditRow, *, include_legacy_demo_test_email: bool) -> str:
    if a.person_id is not None and not a.people_exists:
        return "orphan_person_ref"
    # Narrow: do not deactivate a real onboarded driver named Tom/Dick/Harry with a valid people FK.
    if _norm_first(a.first_name) in DEMO_FIRST_NAMES_FROZEN and (
        a.person_id is None or not a.people_exists
    ):
        return "explicit_demo_first_name"
    if include_legacy_demo_test_email and _legacy_demo_test_email(a):
        return "legacy_demo_test_email"
    return "normal"


def _duplicate_extra_ids(session: Session) -> list[int]:
    """Non-survivor driver ids for duplicate (tenant_id, person_id), person_id not null."""
    q = text(
        """
        WITH ranked AS (
            SELECT
                id,
                tenant_id,
                person_id,
                MIN(id) OVER (PARTITION BY tenant_id, person_id) AS keep_id
            FROM drivers
            WHERE person_id IS NOT NULL
        ),
        dup_groups AS (
            SELECT tenant_id, person_id
            FROM drivers
            WHERE person_id IS NOT NULL
            GROUP BY tenant_id, person_id
            HAVING COUNT(*) > 1
        )
        SELECT r.id
        FROM ranked r
        INNER JOIN dup_groups d
            ON d.tenant_id = r.tenant_id AND d.person_id = r.person_id
        WHERE r.id != r.keep_id
        ORDER BY r.id
        """
    )
    return [int(x[0]) for x in session.execute(q).all()]


def _planned_deactivate_ids(
    audit: list[DriverAuditRow],
    dup_extras: Iterable[int],
    *,
    include_legacy_demo_test_email: bool,
) -> set[int]:
    planned: set[int] = set(dup_extras)
    for a in audit:
        if not a.is_active:
            continue
        cls = _classify(a, include_legacy_demo_test_email=include_legacy_demo_test_email)
        if cls in ("orphan_person_ref", "explicit_demo_first_name", "legacy_demo_test_email"):
            planned.add(a.id)
    return planned


def _print_audit(audit: list[DriverAuditRow], *, include_legacy_demo_test_email: bool) -> None:
    print("=== AUDIT: drivers (+ people link) ===")
    for a in audit:
        cls = _classify(a, include_legacy_demo_test_email=include_legacy_demo_test_email)
        print(
            f"id={a.id} tenant_id={a.tenant_id} person_id={a.person_id} "
            f"name={a.first_name!r} {a.last_name!r} email={a.email!r} phone={a.phone!r} "
            f"is_active={a.is_active} people_ok={a.people_exists} class={cls}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        help="Override tenant DB URL (sync postgresql:// preferred).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform deactivation (default is dry-run).",
    )
    parser.add_argument(
        "--demo-names-only",
        action="store_true",
        help="Only Tom/Dick/Harry (no people link) + orphan person refs + duplicate extras. "
        "Omits legacy *@demo.test null-person rows.",
    )
    args = parser.parse_args()
    include_legacy = not args.demo_names_only

    url = _resolve_tenant_url(args.database_url)
    engine: Engine = create_engine(url)

    with Session(engine) as session:
        audit = _fetch_audit(session)
        dup_extra = _duplicate_extra_ids(session)
        planned = _planned_deactivate_ids(
            audit, dup_extra, include_legacy_demo_test_email=include_legacy
        )

        active_before = sum(1 for a in audit if a.is_active)
        print(f"current_database: {session.execute(text('SELECT current_database()')).scalar()}")
        print(f"active_drivers_before: {active_before}")
        print(f"total_driver_rows: {len(audit)}")
        print(f"duplicate_extra_ids (non-survivors): {dup_extra}")
        print(
            "legacy_demo_test_email_rule: "
            + ("on (*@demo.test, person_id IS NULL)" if include_legacy else "off (--demo-names-only)")
        )
        print()

        _print_audit(audit, include_legacy_demo_test_email=include_legacy)
        print()

        to_touch = sorted(planned)
        dup_set = set(dup_extra)
        by_id = {a.id: a for a in audit}
        print("=== PLANNED is_active=false (currently active only) ===")
        for did in to_touch:
            row = by_id.get(did)
            if row and row.is_active:
                tags = _classify(row, include_legacy_demo_test_email=include_legacy)
                if did in dup_set:
                    tags = f"{tags}+duplicate_non_survivor"
                print(
                    f"  id={did} tenant={row.tenant_id} person_id={row.person_id} "
                    f"{row.first_name!r} {row.last_name!r} :: {tags}"
                )

        already_inactive = [did for did in to_touch if not by_id[did].is_active]
        if already_inactive:
            print(f"(skip already inactive: {already_inactive})")

        active_targets = [did for did in to_touch if by_id[did].is_active]

        if not args.apply:
            print()
            print("Dry-run only. Re-run with --apply to deactivate.")
            return 0

        if not active_targets:
            print("Nothing to update (all targets already inactive). Idempotent exit.")
            active_after = sum(1 for a in audit if a.is_active)
            print(f"active_drivers_after: {active_after}")
            return 0

        upd = text(
            """
            UPDATE drivers
            SET is_active = false, updated_at = NOW()
            WHERE id = ANY(:ids) AND is_active = true
            """
        )
        result = session.execute(upd, {"ids": active_targets})
        session.commit()
        print()
        print(f"UPDATE drivers: rowcount={result.rowcount} (expected {len(active_targets)})")

        audit_after = _fetch_audit(session)
        active_after = sum(1 for a in audit_after if a.is_active)
        print(f"active_drivers_after: {active_after}")
        def _is_polluting_demo(a: DriverAuditRow) -> bool:
            return _norm_first(a.first_name) in DEMO_FIRST_NAMES_FROZEN and (
                a.person_id is None or not a.people_exists
            )

        demo_still_active = [a for a in audit_after if a.is_active and _is_polluting_demo(a)]
        if demo_still_active:
            print("WARNING: polluting demo first names still active:", demo_still_active)
        else:
            print(
                "OK: no active drivers with Tom/Dick/Harry lacking a valid people link "
                "(matches dispatch roster cleanup target)."
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
