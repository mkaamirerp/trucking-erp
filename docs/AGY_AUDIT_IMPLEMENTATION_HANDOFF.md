# TruckERP — AGY Audit & API Runtime Safety: Implementation Handoff

**Date:** 2026-10-17  
**Status:** Documentation / backlog ready; **no implementation or deployment authorized by this document**.  
**Owner goal:** Fix *silent* isolation/security/data-integrity failures before broad cleanup or refactoring. Keep existing TruckERP V1 as one integrated proprietary application with stable module boundaries.

## Source register and limits

1. **Published AGY report (preserve unchanged):** [Module Onboarding Architecture Audit](module_onboarding_audit.md), published at [19822b3](https://github.com/mkaamirerp/trucking-erp/blob/19822b3a9b95ab7f842b6112ce9d9149ab70ff9d/docs/module_onboarding_audit.md).
2. **AGY runtime inspection reported in the owner discussion (not independently reproduced in this handoff):** 371 registered routes; eight non-`/api/v1/` paths; no dev-tools routes; one `truckerp-api` container and one Uvicorn worker; protected platform testing endpoints; weak-secret classification on unknown environment names. Reverify against the **actual image** when resuming.
3. **AGY revised `api_boundary_runtime_safety_verification_plan.md`:** reported as an AGY local/plan artifact; **not found in committed `docs/` on `main` during this review**. Exact diffs and test definitions in that artifact were not available to verify. The implementation requirements below are reconstructed from the owner's conversation and current repository code, **not represented as the original AGY artifact**.
4. **Current repo observations, 2026-10-17:** `app/core/config.py`, `app/main.py`, `app/services/password_reset_links.py`, `app/utils/login_trust_cookie.py`, `scripts/start_api_with_ssm.sh`, `app/scripts/tenant_fleet_upgrade_head.py`, `scripts/tenant_upgrade_head.sh`, `app/services/tenant_provisioning.py`, `app/services/tenant_schema_validation.py`, tenant CI scripts/tests, and `AGENTS.md`.

**Precedence:** `AGENTS.md` and its STOP rule; for Load/Trip behavior, `docs/load_trip/MASTER.md` remains sole authority. An audit proposal is **not** owner authorization and is **not** proof of an implementation-safe design.

## A. Work order and status

| Order | Work package | Status | Boundary |
| --- | --- | --- | --- |
| P0-A | Production environment identity + JWT/reset-link/trust-cookie fail-closed gates | **Design accepted conditionally; implementation NOT started here** | Config/auth/startup only |
| P0-B | Read-only fleet tenant schema/revision inventory (including migration-graph reality) | Investigate first | No DDL/data writes |
| P0-C | Repair tenant-safety CI dead-path checks and add negative proof tests | Plan / review existing exceptions | No indiscriminate ban on platform routes |
| P0-D | Audit field ownership, data propagation, and cross-module schema dependency contracts | Read-only investigation | People/Drivers/Dispatch/Payroll and other consumers |
| P1-A | New tenant READY eligibility and schema compatibility verification | Design after inventory | No blind 'all tables' or 'head' assumptions |
| P1-B | Migration automation controlled remediation | Design after inventory and explicit approval | Do **not** run fleet upgrades as first step |
| P1-C | Automated shared-core STOP approval gate and contract regression matrix | Design only | Commit tag alone is not owner approval |
| P1-D | Platform/tenant Alembic autogenerate separation | Validate actual filters/graphs first | Never delete historical revisions |
| P1-E | Route guard and startup-import regression tests | Add with security work where scoped | Preserve existing URL paths |
| P2-A | Domain outbox multi-worker/SSE delivery redesign | Deferred until scaling | Single worker currently reported |
| P2-B | Fuel dual-DB provider credential write consistency | Investigate transaction/compensation | Do not automatically relocate secrets |
| P2-C | Frontend boundaries, lazy route chunks, entitlement navigation | Incremental, tied to Casbin | No mass API rewrite |
| HOLD | Payroll driver foreign key migration; root Alembic/legacy deletion; mass route-prefix cleanup | **Do not implement from AGY audit** | Needs separate approved migration/contract plans |

### Defect language

- **Confirmed in code:** unknown environment names can skip strong JWT policy; password reset and familiar-device cookie helpers use permissive 'not production/staging' paths; existing tenant CI has dead paths; Fuel commits to two DBs separately; domain dispatcher is single-process fan-out.
- **Reported by AGY runtime, not independently reproduced here:** exact deployed process count, eight-path list, no dev-tool routes, and live SSM values.
- **Not yet established:** actual per-tenant schema drift in production, a current multi-process event delivery defect, or real-world data leakage. Do not claim those without read-only evidence.

## B. P0-A — Exact security implementation contract (small, isolated slice)

**Candidate files (only when independently approved for code change):**
- `app/core/config.py`
- `app/services/password_reset_links.py`
- `app/utils/login_trust_cookie.py`
- `scripts/start_api_with_ssm.sh`
- `app/main.py`
- `tests/test_api_boundary_and_runtime_safety.py` (new); extend focused existing tests if justified.

**Required behavior:**
1. Classify environment explicitly: production = `production|prod|prd`; staging = `staging|stage|stg|preprod`; test = `test|testing|ci`; development = `development|dev|local`. Trim/case-normalize for classification, but reject empty/unknown/typos. Validate **before** weakened behavior is reachable. Keep `TENANT_RESOLUTION_SHORTCUT_SAFE_ENVIRONMENTS` restricted to automated test names; recognizing `dev` is **not** permission to enable powerful tools.
2. JWT secret policy: all environments except the three explicit automated-test names must require a nonempty, non-placeholder secret of at least 32 UTF-8 bytes; test still requires an explicitly present secret. Preserve production/staging protections and run existing JWT encode/decode tests.
3. Password-reset origin: a server-configured override is only permitted for explicitly recognized development/test environments. Unknown/empty/prod/staging must never take that path. Preserve tenant slug and HTTPS domain construction.
4. Login-trust cookie: dedicated configured signing secret takes precedence; JWT fallback only when explicit dev fallback flag **and** recognized dev/test environment are both true; never on unknown/prod/staging. Preserve the existing cookie format and signature checks.
5. Production SSM guard: before **platform Alembic migrations**, when `SSM_ENV=prod`, require `ENVIRONMENT` in the production names, reject test bypass and `ALLOW_TENANT_RESOLUTION_SHORTCUTS` if enabled; distinguish unset/disabled from true and reject malformed/ambiguous values safely. `main.py` startup gate must provide defense in depth. Do not log secrets.
6. No changes to backend worker count, dispatcher, Nginx, `/dashboard`, `/static`, route prefixes, DB schemas, Casbin, or Load/Dispatch behavior in this slice.

**Test matrix (fresh processes for route-registration tests):**

| Case | Expected result |
| --- | --- |
| production/prod/prd and staging aliases, valid strong secret | Normal startup; dev tools absent |
| development/dev/local, valid strong secret | Normal startup; dev tools still absent unless a **separately approved** future tools policy exists |
| test/testing/ci, explicitly configured secret | Existing CI/dev fixture behavior remains possible under explicit flags |
| empty, unknown, `prodcution`, `uat`, `live` | Fail startup; no reduced JWT/reset/cookie path |
| any non-test environment with short or placeholder JWT secret | Startup rejects |
| prod SSM with `ENVIRONMENT=test`, bypass enabled, or shortcuts enabled | Fail **before migration invocation** |
| prod SSM with unset/false/0 bypass flags and valid prod environment | Allowed through preflight, preserving existing requirements |
| trust-cookie and reset link: valid prod/test cases + invalid unknown | Existing successful behavior preserved; unsafe fallback absent |
| platform testing endpoints without admin key and with bad key | 503 when server key missing; 401 for invalid client key |
| route inventory | Enumerate and explicitly account for expected non-API routes; unknown/empty env **fails import/startup**, not a successful eight-route count |

**Regression proof:** run focused policy tests, `tests/test_jwt_secret_startup.py`, `tests/test_login_trust_cookie.py`, `tests/test_tenant_resolution_shortcuts_enforcement.py`, password-reset tests discovered in repo, API import-smoke check `scripts/api_import_smoke.sh`, and route registration/auth-related tests. Confirm expected prod values **without disclosing secrets**. Show diff/test reports before commit. No push/deploy without owner authorization.

## C. P0-B / P1 — Tenant schema consistency: new repo evidence overrides an audit assumption

**IMPORTANT DISCOVERY:** `app/scripts/tenant_fleet_upgrade_head.py` **already exists** and enumerates ACTIVE + READY tenants, invoking `scripts/tenant_upgrade_head.sh` sequentially. AGY's assertion that there is no fleet migration script is incomplete for current `main`. **Do not create a duplicate `migrate_all_active_tenants.py` blindly.**

The current wrapper `scripts/tenant_upgrade_head.sh` explicitly rejects `upgrade head` if the tenant Alembic graph has multiple heads; it instructs operators to use an explicit revision. `app/core/config.py` currently sets `tenant_alembic_target_rev = "i14_load_pod_evidence_x5"` and provisioning uses that target. Read `docs/load_trip/POD_MIGRATION_TARGETS.md` and current Alembic heads **before proposing any mass migration**. The audit's generic 'one head' recommendations cannot simply be applied to this revision state.

**First deliver a READ-ONLY fleet inventory:** tenant ID, slug, DB status, DB name, reachable/unreachable, `alembic_version` revision(s), expected *approved* compatible target, missing required schema anchors/constraints for enabled modules, and code/image SHA. Mask database credentials and customer-sensitive data. Identify multi-head/branch scenarios and incompatible revision chains; no DDL and no upgrade.

**Next design:** new-tenant `READY` validation should check *expected approved compatibility*, not merely that `alembic_version` exists or an indiscriminate `head` matches. Investigate the current provisioning validator's three anchor tables and its existing Alembic-version presence check. Evaluate current fleet runner's lack of dry-run/approval/backup gates and continuation-after-failure policy before using it. Then define backup verification, per-tenant explicit target, canary, stop policy, reporting and recovery; owner approves execution per phase.

**Separate data integrity:** schema upgrade does **not** synchronize business data. Before touching People, Driver, Trip, Payee, Payroll, Fuel, or shared tables, produce a field/table ownership and consumer registry: source-of-truth, linked projections/duplicates, every write path, transactional or outbox propagation rule, historical data handling, migration/backfill plan, and regression proofs. Audit People core → operational Drivers as an initial worked example. NEVER assume a foreign key propagates field values.

## D. P0-C / P1-C — Safety enforcement and STOP

- Inspect `scripts/ci_tenant_safety_grep.sh`, `tests/ci/test_no_platform_db_in_tenant_code.py` and repository contracts. They presently inspect missing `app/routers/tenant` and `app/services/tenant` paths and can silently pass. Introduce live-code coverage with explicit, **reviewed** platform exceptions. Assert the gate actually runs and that an intentionally forbidden use fails. Do not simply reject every legitimate platform DB dependency.
- Design independent owner-approved shared-core change gate for models, migrations, APIs, auth, tenant resolution, service contracts and consumers. A `CORE-CHANGE:` marker in an agent's own message/commit alone is **not** approval. Direct-to-`main` pushes require a preventive approval mechanism before push or deployment, not merely CI failure afterward.
- Preserve `AGENTS.md` STOP → REPORT → INVESTIGATE → WAIT, and its requirement to run dependent-module tests. Reject automated Payroll `drivers.id` FK substitution, mass router prefix rewrites, root Alembic deletion, and mandatory-security-settings becoming optional.

## E. Other AGY findings — disposition

| Audit finding | Follow-up |
| --- | --- |
| 1. Dead tenant CI scan | P0-C; fix with negative and positive tests |
| 2. Fuel platform/tenant dual commits | P2-B; investigate compensation/idempotency, encryption and ownership |
| 3. Shared Alembic metadata | P1-D; examine actual autogenerate config and generated DDL, add correctly scoped metadata filters only with tests |
| 4. Incomplete provisioning validation | P1-A; expected revision AND critical schema/contract probes |
| 5. Existing tenant upgrades | P0-B / P1-B; inspect **existing fleet script**, multi-head constraints; dry-run first |
| 6. Unenforced STOP rule | P1-C; real approval, broad dependency contract coverage |
| 7. Static frontend imports/large API client | P2-C; incremental, module-level error boundaries; permissions belong to Casbin |
| 8. Backend static imports | P1-E; reuse existing `scripts/api_import_smoke.sh` and validate it is actually required in deployment |
| 9. Module settings at import | P0-A; retain required fail-closed security settings while isolating optional integrations |
| 10. Mixed route prefix conventions | P1-E; test collisions/non-API escapes, do not bulk rename |
| Runtime: in-process event dispatcher | P2-A; single worker reported, lock/claim + cross-worker SSE needed before scale |
| Runtime: `/dashboard` HTML | Deferred cleanup; keep currently stable endpoints |
| Runtime: public webhooks, platform testing | Inspect and regression-test existing sender verification, keys, and privilege boundaries |

## F. Work protocol / handoff to Cursor or other agent

1. Read this file, [original audit](module_onboarding_audit.md), `TODO.md`, `AGENTS.md`, security tests, and affected code on **current `main`**; re-check facts after intervening commits.
2. Begin with a precise file and contract scope. **One work package at a time**; no unrelated 'cleanup'.
3. If a new module or fix requires shared schema, cross-module contracts, auth, migration behavior, or existing consumer changes, **STOP and request owner approval before edit**.
4. For P0-A, prepare the exact bounded code diff and tests; verify accepted test behavior in an isolated environment. Do not accidentally run `start_api_with_ssm.sh` in its normal migration/startup mode during test exercises; use the existing `--check-secrets-file` preflight path or safe isolated fixtures.
5. Show file list, test command and results, residual risks, and whether test coverage was actually enforced in CI. Do not report a green check that scanned nothing.
6. **No commit, push, deploy, production configuration change, database migration, or tenant-data write without separate owner approval.** Work remains on `main` per repo charter, but do not disturb any ongoing working tree; stage only explicitly approved files.
7. Mark work done here and in `TODO.md` only after verified implementation. The AGY audit and this handoff remain durable historical references, not automatic authority to redesign business logic.
