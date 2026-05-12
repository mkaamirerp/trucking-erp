# Driver ID preprocessing — rounded-corner line-intersection prototype

## Status

Save-only prototype. This is **not wired into onboarding yet**.

The existing OCR path is assumed to work. This module is only for preprocessing driver-license / ID-card photos before OCR.

## Locked pipeline

1. Try orientation candidates: original, 90° clockwise, 90° counterclockwise, and 180°.
2. Build multiple masks:
   - preferred blue/green DL security-pattern mask,
   - saturation fallback,
   - bright fallback,
   - edge fallback.
3. Select the best card-shaped connected component.
4. Fit straight top, bottom, left, and right edge lines while ignoring rounded-corner zones.
5. Use line intersections as the true geometric corners:
   - top ∩ left = TL,
   - top ∩ right = TR,
   - bottom ∩ right = BR,
   - bottom ∩ left = BL.
6. Measure geometry before perspective correction:
   - ratio error,
   - top/bottom delta,
   - left/right delta,
   - diagonal delta,
   - max corner-angle error from 90°,
   - border-touch risk.
7. Use ID-1/DL reference geometry:
   - `85.60 / 53.98 ≈ 1.586`,
   - normalized target output `1000 x 630`.
8. If geometry passes, apply perspective first using:
   - `cv2.getPerspectiveTransform`,
   - `cv2.warpPerspective`.
9. If geometry fails or the card touches the image border, return safe crop + orientation fallback.
10. Final output must stay landscape and OCR-safe.

## Why line intersections are required

Driver licenses have rounded physical corners. The visible rounded arc pixel is not the true rectangular perspective corner. Using rounded arc pixels as final corners can pull corners inward and distort or cut the card.

The correct perspective corners are where the straight card edge lines would intersect. The algorithm therefore fits four edge lines and synthesizes the true corners from their intersections.

## Validation gate

The current prototype uses a two-stage gate:

Strict pass:

- ratio error ≤ 5%,
- max angle error ≤ 10°,
- top/bottom delta ≤ 8%,
- left/right delta ≤ 10%,
- diagonal delta ≤ 10%,
- no border touch.

Permissive pass for angled but otherwise coherent photos:

- ratio error ≤ 4%,
- max angle error ≤ 6°,
- top/bottom delta ≤ 4%,
- left/right delta ≤ 15%,
- diagonal delta ≤ 10%,
- no border touch.

This prevents one-off tuning to a single image while still allowing realistic angled photos.

## Current test notes

- Red-background normal DL photo: accepted perspective-first line-intersection warp.
- Tight-cropped DL photo: rejected perspective because of border-touch risk and returned safe crop/orientation fallback.
- Black-background angled image: stress test only; accepted after the permissive geometry gate. Normal production target remains full DL visible, close enough, reasonably lit, and only mildly tilted/perspective-skewed.

## Run locally

```bash
python app/services/driver_id_preprocessing.py input.jpg output.jpg --debug-dir debug_out
```

Debug output:

```text
debug_out/01_best_component_mask.jpg
debug_out/02_best_corners_debug.jpg
debug_out/03_final_selected.jpg
debug_out/candidate_scores.json
debug_out/result.json
```

## Boundaries

This commit must remain save-only:

- no onboarding route wiring,
- no OCR changes,
- no frontend changes,
- no database changes,
- no automatic production use yet.

Future integration should wrap this service behind the driver onboarding document-upload flow and compare OCR quality against the original image before changing production behavior.
