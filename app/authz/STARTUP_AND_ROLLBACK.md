# Loads pilot startup and rollback

`casbin_load_pilot_enforcement` defaults to false. While it is false, the four routes below keep today's authorization. The pilot dependency does not load a policy, and no request calls `decide()`.

There is no database policy table. Application startup does not load Casbin. The first enforced request in a process loads the policy described below.

## Routes controlled by the switch

Only these operations call `require_pilot_capability`. No other route, and no other module, uses live Casbin enforcement.

| Method | Path | Capability |
|---|---|---|
| `GET` | `/api/v1/loads` | `loads.records` / `view` |
| `GET` | `/api/v1/loads/{load_id}` | `loads.records` / `view` |
| `POST` | `/api/v1/loads` | `loads.records` / `create` |
| `PATCH` | `/api/v1/loads/{load_id}` | `loads.records` / `update` |

Mark Ready, physical DELETE, notes, document confirmation, custody, and parse stay outside the pilot.

## Which policy is enforced

When the switch is on, the pilot validates and uses `app/authz/casbin/policy_prospective.csv` through `load_prospective_policy()`. It does not enforce the Phase 0 shipped policy.

`app/authz/casbin/policy.csv`, with `app/authz/casbin/model.conf`, remains the original foundation policy. `load_shipped_policy()` still reads that pair and is not used by the pilot.

## Process cache and fail closed

A successful prospective load is cached for the life of that API process. A later edit to `policy_prospective.csv` is not read until the process restarts or `reset_pilot_policy_cache()` runs.

While enforcement is enabled, a missing or invalid prospective policy raises `PolicyLoadError`. That failure is not cached. The request is denied with HTTP 403 `AUTHZ_UNAVAILABLE` (`policy_load_failed`). The next request loads again and stays closed until a valid file loads. An unavailable decision is never treated as allow.

## Rollback

1. Set `casbin_load_pilot_enforcement` to false. That is the default. The environment name is `CASBIN_LOAD_PILOT_ENFORCEMENT`.
2. Restart the API and confirm the running process is using that disabled value.
3. Do not stamp, migrate, or edit tenant data. There is nothing in the database to roll back.

With the switch off, the four routes return to today's authorization even if the cached enforcer or the prospective file is wrong. Do not add a fallback allow.

## Dependency

`casbin==1.41.0` is declared in `requirements.in`, `requirements.txt`, and `requirements.lock.txt`. Its dependency `simpleeval==1.0.8` is in the lockfile. Casbin is imported only when a policy loader runs. Startup does not call `load_shipped_policy()` or `load_prospective_policy()`.
