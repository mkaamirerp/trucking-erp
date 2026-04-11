"""
Shim: run the canonical dispatch demo seed from the repo root.

Historically this copy used DATABASE_URL + a non-standard `search_path`, which pointed at the
wrong database and arbitrary `drivers` rows. The root `seed_dispatch.py` uses the tenant DB URL
and tenant-scoped lookups only; it does not insert operational drivers.

Run (from host or container with /app = repo root):
  python tools/seed_dispatch.py
  # or: python /app/seed_dispatch.py
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys


def _load_root_seed():
    root = pathlib.Path(__file__).resolve().parents[1]
    path = root / "seed_dispatch.py"
    if not path.is_file():
        print(f"ERROR: missing canonical seed script: {path}", file=sys.stderr)
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("_seed_dispatch_canonical", path)
    if spec is None or spec.loader is None:
        print("ERROR: could not load canonical seed_dispatch.py", file=sys.stderr)
        sys.exit(1)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    mod = _load_root_seed()
    mod.run()
