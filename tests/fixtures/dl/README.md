# DL OpenCV test fixtures

## CI (hermetic)

Working-scale invariants are tested with **generated, non-sensitive** images in
`tests/test_applicant_dl_opencv.py`. Those tests do **not** read `tmp/` and
must pass on a clean checkout.

They cover:

- `WORKING_COPY_MAX_SIDE == 1544`
- source long side > 1544 → working copy long side exactly 1544
- source ≤ 1544 → no working-copy downscale
- stored source file is not overwritten by the working-copy resize
- confirmed synthetic processing → final output 1000×631

## Private operator battery (not a CI gate)

Real driver-licence images must live **outside every git worktree**. Do not
place them under the repo (including `tests/fixtures/dl/` or `tmp/`).

Install the IMG6446 regression separately, then point tests at that directory:

```bash
export DL_PRIVATE_FIXTURE_DIR=/path/to/private/dl/fixtures
```

Expected private filename (inside that directory):

`IMG_6446_normalized.jpg`

When `DL_PRIVATE_FIXTURE_DIR` is set and that file exists, private tests assert
Canny working-scale 1544, output 1000×631, and PDF417 meaningful-field count.

When the env var is unset or the file is absent, those tests **skip** with:

`private DL regression fixture not installed`

They are not a universal CI gate. Hermetic CI tests still always run.
