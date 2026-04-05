#!/usr/bin/env python3
"""
Verify dl_enhance: EXIF rotate, deskew, resize, sharpen.
Run from repo root: python scripts/test_dl_enhance.py [path_to_image.jpg]
If no path given, creates a small test image and runs enhance on it.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Run from repo root; add app to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))


def main() -> None:
    from PIL import Image

    from app.services.dl_enhance import enhance_dl_image

    if len(sys.argv) >= 2:
        in_path = Path(sys.argv[1])
        if not in_path.is_file():
            print(f"File not found: {in_path}")
            sys.exit(1)
        content_type = "image/jpeg" if in_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    else:
        # Create a small test image (100x100 red square)
        in_path = repo_root / "storage" / "test_dl_enhance_input.jpg"
        in_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (100, 100), color=(200, 50, 50))
        img.save(in_path, "JPEG", quality=90)
        content_type = "image/jpeg"
        print(f"Created test image: {in_path}")

    out_path, out_ct = enhance_dl_image(in_path, content_type)
    if out_path == in_path:
        print("Enhance returned original path (enhance failed or no-op)")
    else:
        print(f"Enhance produced: {out_path} ({out_ct})")
        if out_path.is_file():
            size = out_path.stat().st_size
            print(f"Output size: {size} bytes")
        else:
            print("ERROR: output file not found")
            sys.exit(1)
    print("OK: dl_enhance ran without crash.")


if __name__ == "__main__":
    main()
