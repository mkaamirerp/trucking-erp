#!/usr/bin/env python3
"""Applicant token storage inventory and reversible token_hash backfill.

Modes (one tenant database per run; URL is read from an env var, never printed):

  inventory (default, read-only)
      Counts application_access_tokens by purpose and storage shape, and live rows.

  --apply --confirm-db <name> --record <file.json>
      Sets token_hash = sha256(token) only where token_hash IS NULL and token IS NOT NULL.
      Plaintext `token` values are NOT cleared. Affected ids are written to <file.json>.

  --revert <file.json> --confirm-db <name>
      Sets token_hash back to NULL for the recorded ids, only where the stored hash still
      equals sha256(token) (rows this backfill wrote and nobody changed since).

Clearing legacy plaintext and onboarding_token_lookup rows is a separate owner decision.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.core.db_url import to_async_pg_url  # noqa: E402

_SHA = "encode(sha256(convert_to(btrim(token), 'UTF8')), 'hex')"

INVENTORY_SQL = text(
    """
    SELECT purpose,
           count(*) AS total,
           count(*) FILTER (WHERE token IS NOT NULL AND token_hash IS NULL) AS plaintext_only,
           count(*) FILTER (WHERE token IS NOT NULL AND token_hash IS NOT NULL) AS plaintext_and_hash,
           count(*) FILTER (WHERE token IS NULL AND token_hash IS NOT NULL) AS hash_only,
           count(*) FILTER (WHERE revoked_at IS NULL AND expires_at > now()) AS live,
           count(*) FILTER (WHERE token IS NOT NULL AND revoked_at IS NULL AND expires_at > now()) AS live_with_plaintext
    FROM application_access_tokens
    GROUP BY purpose
    ORDER BY purpose
    """
)
APPLY_SQL = text(
    f"""
    UPDATE application_access_tokens
    SET token_hash = {_SHA}
    WHERE token_hash IS NULL AND token IS NOT NULL
    RETURNING id
    """
)
REVERT_SQL = text(
    f"""
    UPDATE application_access_tokens
    SET token_hash = NULL
    WHERE id = ANY(:ids) AND token IS NOT NULL AND token_hash = {_SHA}
    RETURNING id
    """
)


async def _run(args: argparse.Namespace) -> int:
    raw_url = os.environ.get(args.url_env) or ""
    if not raw_url:
        print(f"{args.url_env} is not set", file=sys.stderr)
        return 2
    engine = create_async_engine(to_async_pg_url(raw_url))
    try:
        async with engine.begin() as conn:
            db_name = (await conn.execute(text("SELECT current_database()"))).scalar_one()
            print(f"database={db_name}")
            if (args.apply or args.revert) and args.confirm_db != db_name:
                # Raise so engine.begin() rolls back; nothing from this transaction is written.
                raise SystemExit("Refusing to write: --confirm-db must equal the connected database name.")
            if args.apply:
                ids = sorted(int(r[0]) for r in (await conn.execute(APPLY_SQL)).all())
                Path(args.record).write_text(json.dumps({"database": db_name, "ids": ids}), encoding="utf-8")
                print(f"backfilled={len(ids)} record={args.record}")
            elif args.revert:
                data = json.loads(Path(args.revert).read_text(encoding="utf-8"))
                if data.get("database") != db_name:
                    print("Refusing to revert: record belongs to another database.", file=sys.stderr)
                    return 2
                reverted = (await conn.execute(REVERT_SQL, {"ids": list(data.get("ids") or [])})).all()
                print(f"reverted={len(reverted)} of recorded={len(data.get('ids') or [])}")
            rows = (await conn.execute(INVENTORY_SQL)).mappings().all()
            for row in rows:
                print(" ".join(f"{k}={row[k]}" for k in row.keys()))
    finally:
        await engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url-env", default="TENANT_DATABASE_URL")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--revert", metavar="RECORD_JSON")
    parser.add_argument("--confirm-db", default="")
    parser.add_argument("--record", default="")
    args = parser.parse_args(argv)
    if args.apply and not args.record:
        parser.error("--apply requires --record")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
