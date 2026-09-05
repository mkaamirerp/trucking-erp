#!/usr/bin/env python3
"""Batch-run sandbox OpenCV pipeline on the three verified DL test images."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.applicant_dl_preprocess import run_applicant_dl_opencv  # noqa: E402


SANDBOX_IMAGES = [
    ("05_front_wood.png", "Image_260301_135619.jpeg"),
    ("04_front_dark_bg.png", "IMG_9084(1).jpeg"),
    ("03_front_magenta_glare.png", "IMG_9086(1).jpeg"),
]


def main() -> int:
    in_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tmp/dl_test_in")
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("tmp/dl_sandbox_out")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for local_name, sandbox_name in SANDBOX_IMAGES:
        src = in_dir / local_name
        if not src.is_file():
            print(f"Missing: {src}", file=sys.stderr)
            continue
        outcome = run_applicant_dl_opencv(src)
        dbg = outcome.debug
        row = {
            "sandbox_input": sandbox_name,
            "local_file": local_name,
            "success": outcome.success,
            "status": dbg.get("status"),
            "classification": outcome.classification,
            "correction_applied": outcome.correction_applied,
            "orientation_used": dbg.get("orientation_used"),
            "edge_inliers": dbg.get("edge_inliers") or dbg.get("confirm_diagnostics", {}).get("edge_inliers"),
            "ratio_error_percent": dbg.get("confirm_diagnostics", {}).get("ratio_error_percent"),
            "max_angle_error_from_90": dbg.get("confirm_diagnostics", {}).get("max_angle_error_from_90"),
            "final_dimensions": dbg.get("final_dimensions"),
        }
        rows.append(row)
        if outcome.success and outcome.jpeg_bytes:
            (out_dir / f"{src.stem}_processed.jpg").write_bytes(outcome.jpeg_bytes)

    summary = out_dir / "sandbox_results.json"
    summary.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps(rows, indent=2))
    ok = sum(1 for r in rows if r["success"])
    print(f"\n{ok}/{len(rows)} processed (sandbox expects 3/3)", file=sys.stderr)
    return 0 if ok == len(rows) and len(rows) == 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
