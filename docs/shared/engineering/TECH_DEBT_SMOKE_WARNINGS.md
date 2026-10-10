# Tech debt: pytest warnings on canonical smoke run

**Ticket-style follow-up (separate from login hardening).**

When running:

```bash
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -m pytest tests/test_login_hardening_smoke.py tests/test_admin_sign_in_unlock_smoke.py -q'
```

pytest may report many **warnings** (e.g. Pydantic v2 `Config` deprecations, FastAPI `on_event`, SQLAlchemy `datetime.utcnow`).

## Goal

Reduce noise and future breakage by migrating those call sites to supported APIs — **outside** the canonical login smoke files unless a warning originates there.

## Out of scope for this item

- Expanding `tests/test_login_hardening_smoke.py` or `tests/test_admin_sign_in_unlock_smoke.py` into a larger matrix.
- Changing login security behavior under the guise of “warning cleanup.”
- Using warning noise as an excuse to weaken assertions, delete scenarios, or merge unrelated behavior changes into the canonical smoke files.

**Boundary:** Login product changes belong in their own PRs and **must** keep the two canonical smoke tests passing and contract-accurate (see `.cursor/rules/login-smoke-suite-canonical.mdc`). Warning cleanup PRs touch **app / shared test code**, not the login contract, unless a warning is literally **in** a smoke file line you are tidying without changing what is asserted.

## Suggested approach

1. Re-run the two-file smoke command with `pytest -W error::DeprecationWarning` (or per-module) to find the highest-volume sources.
2. Fix deprecations in **app code** and shared **test utilities**, not by weakening smoke assertions.
