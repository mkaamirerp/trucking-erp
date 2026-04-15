#!/usr/bin/env python3
"""Operator helper: PDF417 decode + AAMVA mapping on a license-back image with full diagnostics.

Usage:
  python scripts/debug_dl_pdf417_extract.py /path/to/cdl_back.jpg
  python scripts/debug_dl_pdf417_extract.py /path/to/cdl_back.jpg --save-candidates /tmp/dl_dbg
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.services.dl_pdf417 import (  # noqa: E402
    aamva_intake_from_pdf417_text,
    apply_pdf417_to_intake,
    decode_pdf417_barcode_with_trace,
    meaningful_license_field_count,
)


def _final_status(raw: str | None, technical: str | None, fields: dict) -> str:
    if technical:
        return "FAILED"
    if not raw:
        return "NO_FIELDS_FOUND"
    if meaningful_license_field_count(fields) >= 1:
        return "SUCCESS"
    return "NO_FIELDS_FOUND"


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug PDF417 / AAMVA extraction from one image file.")
    parser.add_argument("image_path", type=Path, help="Path to JPG/PNG (typically CDL back)")
    parser.add_argument(
        "--save-candidates",
        type=Path,
        default=None,
        help="Directory to write each preprocessing candidate as PNG (for visual tuning)",
    )
    parser.add_argument(
        "--max-attempt-print",
        type=int,
        default=25,
        help="Max decode attempts to print (full trace is in intake debug / meta)",
    )
    args = parser.parse_args()
    path = args.image_path.expanduser().resolve()

    opened = False
    fmt = None
    dimensions = None
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as im:
            opened = True
            fmt = im.format
            im = ImageOps.exif_transpose(im)
            dimensions = im.size
    except Exception as exc:
        print(f"image opened successfully: no ({type(exc).__name__})")
        print(f"final status classification: FAILED")
        return 1

    print(f"image opened successfully: yes")
    print(f"dimensions: {dimensions[0]}x{dimensions[1]} format: {fmt}")

    save_dir = args.save_candidates
    raw, meta = decode_pdf417_barcode_with_trace(
        path,
        mode="thorough",
        save_candidates_dir=save_dir,
    )
    if save_dir:
        print(f"candidate images saved under: {save_dir.resolve()}")

    print(f"decode result present: {'yes' if raw else 'no'}")
    if raw:
        print(f"  barcode_char_length: {len(raw)}")
        win = meta.winning_candidate
        eng = meta.winning_engine
        print(f"  winning_candidate: {win!r} engine: {eng!r}")
    else:
        print("  winning_candidate: None  engine: None")
        print("  (no PDF417 payload decoded by any candidate)")

    attempts = meta.attempts
    print(f"decode attempts logged: {len(attempts)}")
    for i, row in enumerate(attempts[: max(0, args.max_attempt_print)]):
        print(f"  [{i}] {json.dumps(row, default=str)}")
    successes = [a for a in attempts if a.get("ok")]
    if successes:
        print(f"first success attempt: {json.dumps(successes[0], default=str)}")
    elif attempts:
        print("first success attempt: <none>")

    fields = aamva_intake_from_pdf417_text(raw) if raw else {}
    mcount = meaningful_license_field_count(fields)
    print(f"extracted field count (meaningful): {mcount}")
    print(f"extracted keys: {sorted(k for k in fields.keys() if k not in ('field_sources', 'pdf417_text'))}")

    if fields:
        for key in sorted(fields.keys()):
            val = fields[key]
            if key == "pdf417_text":
                print(f"  {key}: <omitted {len(str(val))} chars>")
            elif key == "field_sources":
                print(f"  {key}: {json.dumps(val, indent=2, default=str)[:2000]}")
            else:
                print(f"  {key}: {val!r}")
    else:
        print("no fields found (decode produced no AAMVA-mapped keys)")

    merged = apply_pdf417_to_intake({}, raw_barcode_text=raw, technical_error=None, decode_meta=meta)
    lic_status = merged.get("license_extract_status")
    print(f"apply_pdf417_to_intake license_extract_status: {lic_status!r}")
    print(f"final status classification: {_final_status(raw, None, fields)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
