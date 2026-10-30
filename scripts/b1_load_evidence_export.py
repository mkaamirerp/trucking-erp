#!/usr/bin/env python3
"""Read-only B1 verification export for one load (tenant_demo)."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


async def export(tenant_id: int, load_id: int, tenant_slug: str, label: str, out_dir: Path) -> None:
    from sqlalchemy import select

    from app.core.config import settings
    from app.deps.tenant_db import open_tenant_session_by_id
    from app.models.load import Load, LoadStop
    from app.models.load_commercial_evidence import LoadCommercialEvidence
    from app.services.load_workspace_draft_document import revised_pdf_records
    from app.services.loads import read_load_rate_confirmation_pdf_bytes, read_revised_rate_confirmation_pdf_bytes

    out_dir.mkdir(parents=True, exist_ok=True)
    bundle: dict = {"label": label, "tenant_id": tenant_id, "load_id": load_id}

    async for db in open_tenant_session_by_id(tenant_id):
        load = await db.scalar(select(Load).where(Load.tenant_id == tenant_id, Load.id == load_id))
        evidence = await db.scalar(
            select(LoadCommercialEvidence).where(
                LoadCommercialEvidence.tenant_id == tenant_id,
                LoadCommercialEvidence.load_id == load_id,
            )
        )
        if load is None or evidence is None:
            raise SystemExit("load or evidence missing")
        bundle["loads_row"] = {c.name: getattr(load, c.name) for c in load.__table__.columns}
        stops = (
            await db.scalars(
                select(LoadStop)
                .where(LoadStop.tenant_id == tenant_id, LoadStop.load_id == load_id)
                .order_by(LoadStop.sequence)
            )
        ).all()
        bundle["load_stops"] = [{c.name: getattr(s, c.name) for c in s.__table__.columns} for s in stops]
        bundle["storage_backend"] = (settings.storage_provider or "local").lower()
        bundle["evidence"] = {
            c.name: getattr(evidence, c.name)
            for c in evidence.__table__.columns
            if c.name != "accepted_parse_json"
        }
        bundle["accepted_parse_json"] = evidence.accepted_parse_json
        bundle["revised_pdf_records"] = revised_pdf_records(evidence.accepted_parse_json)

        _ev, ob = await read_load_rate_confirmation_pdf_bytes(db, tenant_id, load_id, tenant_slug=tenant_slug)
        bundle["original_pdf"] = {
            "file_sha256_db": _ev.file_sha256,
            "downloaded_sha256": hashlib.sha256(ob).hexdigest(),
            "byte_size": len(ob),
            "storage_key": _ev.storage_key,
        }
        bundle["revised_downloads"] = []
        for i in range(1, len(bundle["revised_pdf_records"]) + 1):
            fn, rb = await read_revised_rate_confirmation_pdf_bytes(
                db, tenant_id, load_id, revision=i, tenant_slug=tenant_slug
            )
            rec = bundle["revised_pdf_records"][i - 1]
            bundle["revised_downloads"].append(
                {
                    "revision": i,
                    "filename": fn,
                    "pointer": rec,
                    "downloaded_sha256": hashlib.sha256(rb).hexdigest(),
                    "byte_size": len(rb),
                }
            )
        break

    path = out_dir / f"load_{load_id}_{label}.json"
    path.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"export_path": str(path)}, indent=2))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant-id", type=int, default=53)
    p.add_argument("--tenant-slug", default="demo")
    p.add_argument("--load-id", type=int, required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    asyncio.run(export(args.tenant_id, args.load_id, args.tenant_slug, args.label, args.out_dir))


if __name__ == "__main__":
    main()
