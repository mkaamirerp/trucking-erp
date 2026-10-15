# Phase 0 startup and rollback (not wired)

This package is not imported from `app/main.py`. Loading a valid policy does not change live authorization.

## Later-phase startup (one step, not this change)

When a future change is approved to enforce policy:

1. Call `load_shipped_policy()` once, after settings load and before the process accepts requests.
2. If it raises `PolicyLoadError`, log the error and exit non-zero. Do not serve with an empty enforcer, a previous in-memory policy, or an implicit allow.
3. Keep the returned enforcer in one process-local variable. Do not reload from disk on each request in that phase.
4. Only after that load succeeds, attach a dependency that calls `decide(...)`. That attachment is a separate change and is out of scope here.

There is no database policy table. The files `app/authz/casbin/model.conf` and `app/authz/casbin/policy.csv` are the only policy source.

## Rollback

1. `git revert` the commit that changed `model.conf` or `policy.csv` (and the loader, if the contract changed with them).
2. Restart the API process so it loads the restored files.
3. Do not stamp, migrate, or edit tenant data. There is nothing in the database to roll back.

If the reverted files fail validation, the later-phase startup rule still applies: the process stays down until a valid pair is deployed. Do not add a fallback allow.

## Dependency

`casbin` is not listed in `requirements.txt` or `requirements.lock.txt`. This package imports it only inside `load_policy`. Adding `casbin==1.41.0` (which requires `simpleeval==1.0.8`) needs a separate approval before it is declared or installed in the API image.
