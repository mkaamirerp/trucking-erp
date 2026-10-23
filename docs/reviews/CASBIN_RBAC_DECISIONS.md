# Casbin RBAC — Decision Corrections

- **HEAD:** `d732ad4c654be94e4c479c368572678cb57fb89d`
- **Date (UTC):** 2026-10-15
- **Source report (unchanged):** `docs/reviews/CASBIN_RBAC_INSPECTION.md`
- **Method:** Read-only recount of the same 371-route graph used for that report, plus source checks for helper and decorator gates the first counters missed. No tests were executed. No runtime calls were made against tenant data.

This file corrects counting, the Casbin model, risk ratings, and the Phase 0 boundary. It does not authorize implementation.

## What to review

Corrections versus `docs/reviews/CASBIN_RBAC_INSPECTION.md`:

| Topic | Inspection report | This correction |
|-------|-------------------|-----------------|
| 119 vs 61 vs 173 | Treated as separate coverage stats | Not a partition. Overlap is 13. Disjoint result is **76 gated + 97 ungated = 173** |
| Ungated mutations | 119 authenticated mutations lack a role gate | **97** have no role gate. 22 of the 119 are already gated by `is_tenant_admin`, driver-document full access, or People `_require_admin` |
| Casbin shape | Sketch only | One RBAC-with-domains model. Subject is the membership role, not the user id. `dom=*` does not cross tenants |
| FULL_ACCESS | Listed as an open Phase 0 decision | Keep mapping `FULL_ACCESS` → `TENANT_ADMIN`. A separate operational role waits for a later phase |
| 11 unmapped routes | `NEEDS_APPROVAL` | Infrastructure, or authenticated self-service (`GET /api/v1/me`, `PATCH /api/v1/me/preferences`) |
| Fuel | Proposed granular grants | V1 stays admin-only |
| Load delete | Mixed into the auth risk list | I5 stays open. Phase 0 does not allow or block `delete_load` |
| Risk R1, R3–R7 | Several intended behaviors rated as bypasses | Only missing gates and the hard-delete path stay as findings. Documented READ_ONLY admin reads are not findings |
| Phase 0 | Registry plus later enforcement phases | Non-enforcing policy package only. **No owner decision is required** before that package |

---

## 1. Mutation-count reconciliation

The inspection report uses three figures that are **not** a partition of each other.

| Reported figure | What it actually counted |
|-----------------|--------------------------|
| **173** | API `POST`/`PUT`/`PATCH`/`DELETE` whose FastAPI dependency tree includes `get_current_user` **or** `get_current_platform_user`. Includes `POST /api/v1/auth/workspaces`. |
| **61** | Subset of those 173 whose **handler body** contains `is_tenant_admin` or `has_full_access`, **or** whose dependency tree is a Fuel capability. Misses decorator dependencies and helpers. |
| **119** | Authenticated API mutations with no Fuel dependency, no `require_tenant_admin` in the dependency tree, and no `/admin` in the path. This **includes** 13 routes that are inside the 61, plus helper/dependency gates the body scan missed. |

### Identity

```text
119 + 61 = 180
overlap(119, 61) = 13
180 - 13 = 167
167 + 6 payroll routes gated only by Depends(require_tenant_admin) = 173
```

The 13-route overlap is real `is_tenant_admin` enforcement whose path does not contain `/admin`:

- `PUT /api/v1/driver-person-extensions/{person_id}`
- `POST /api/v1/load-lab/openai-smoke`
- `DELETE /api/v1/load-lab/runs`
- eleven `/api/v1/driver-onboarding/applications/{application_id}/…` mutations (`dl-capture-link`, `review-fields`, `request-documents`, `documents/accept`, `document-upload`, `materialize-person-for-combined-setup`, `approve`, `reject`, `driver-compensation-setup`, `complete-onboarding`)

### Disjoint categories of the 173

Checked once, first match wins. Sum is 173.

| # | Category | Count | Evidence |
|---|----------|------:|----------|
| A | Fuel `require_fuel_capability` | 25 | `app/deps/fuel_rbac.py:53-64`; Fuel router dependencies |
| B | `is_tenant_admin(...)` in the handler body | 30 | e.g. `app/routers/admin_email_config.py`, `driver_onboarding.py`, `load_lab.py:37` and `:109` |
| C | `has_full_access(...)` in the handler body | 6 | `app/routers/tenant_admin.py:551`, `:631`, `:822`, `:871`, `:919`, `:978` |
| D | `require_full_access_driver_documents` dependency | 5 | `app/routers/driver_documents.py:36-47` |
| E | Route `dependencies=[Depends(require_tenant_admin)]` | 6 | `app/routers/payroll.py:67`, `:160`, `:181`; `app/routers/pay_runs.py:156`, `:202`, `:312` |
| F | People `_require_admin` helper | 4 | `app/routers/people_workspace.py:55-57`, called at `:89`, `:192`, `:286`, `:433` |
| G | Authenticated, no role symbol | 97 | See below |
| | **Total** | **173** | A+B+C+D+E+F+G |

Explicit role/capability gate = A+B+C+D+E+F = **76**.  
The old **61** = A+B+C only (25+30+6). It omitted D (5), E (6), and F (4): 61+5+6+4 = **76**.

The old **119** = G (97) + overlap with B (13) + D (5) + F (4) = **119**. Those 13+5+4 routes are gated. They are not ungated.

### What the 97 actually are

Prefix counts (sum 97):

| Prefix | Mutations with no role gate |
|--------|----------------------------:|
| `/api/v1/brokers` | 21 |
| `/api/v1/trips` | 13 |
| `/api/v1/email-threads` | 13 |
| `/api/v1/tolls` | 10 |
| `/api/v1/payroll` | 7 |
| `/api/v1/loads` | 7 |
| `/api/v1/customs-brokers` | 6 |
| `/api/v1/load-lab` | 4 |
| `/api/v1/driver-phones` | 3 |
| `/api/v1/terminals` | 3 |
| `/api/v1/drivers` | 2 |
| `/api/v1/onboarding` | 2 |
| `/api/v1/trucks` | 2 |
| `/api/v1/trailers` | 2 |
| `/api/v1/me` | 1 (`PATCH /preferences`) |
| `/api/v1/auth` | 1 (`POST /workspaces`) |

`DELETE /api/v1/drivers/{driver_id}` is **not** in the 173. It has no auth dependency and always returns 405 (`app/routers/drivers.py:244-249`).

---

## 2. Casbin model (one model)

V1 does not store per-user rows. Python resolves the membership role for the already-bound tenant, then asks Casbin whether that role may perform the action in that domain.

```ini
[request_definition]
r = sub, dom, obj, act

[policy_definition]
p = sub, dom, obj, act, eft

[policy_effect]
e = some(where (p.eft == allow)) && !some(where (p.eft == deny))

[matchers]
m = r.sub == p.sub && (p.dom == "*" || r.dom == p.dom) && r.obj == p.obj && r.act == p.act
```

No `g` grouping in V1. A user id is never a policy subject.

| Field | Request value | Policy value |
|-------|----------------|--------------|
| `sub` | Membership role for **this** tenant: `OWNER`, `ADMIN`, `TENANT_ADMIN`, `TENANT_OWNER`, or `TENANT_MEMBER` | Same role string |
| `dom` | Decimal `tenant_id` from `request.state.tenant_id` after middleware and `get_current_user` | `*` for a grant that applies to every already-authenticated tenant, or one tenant id for an exception |
| `obj` | Capability resource (`loads`, `tenant.users`, `fuel.providers`) | Same |
| `act` | Verb (`view`, `update`, `invite`, …) | Same |
| `eft` | — | `allow` in V1. No `deny` rows until a later approval |

`p.dom == "*"` means “any tenant this request has already been authenticated into.” It does not grant a role from tenant 17 into tenant 42. Cross-tenant use is rejected before Casbin: JWT `tenant_id` must match the host tenant (`app/deps/auth.py:99-103`), and the role is loaded only for that tenant.

### Membership → subject

| Auth mode | Role loaded into `CurrentUser.role` | Casbin `sub` |
|-----------|--------------------------------------|--------------|
| Platform (`tenant_auth_mode=platform`) | `PlatformTenantMember.role` overrides the JWT role (`app/deps/auth.py:197-198`) | That role, uppercased |
| Tenant-local (`tenant_uses_tenant_db_auth`) | `TenantWorkspaceMember.role` where `status == "active"` (`app/deps/auth.py:133-146`) | That role, uppercased |

Empty role, unrecognized role, or inactive membership: do not call a default allow. Unknown `sub` matches no `p` row, so the effect is deny.

`FULL_ACCESS` and `READ_ONLY` are **not** Casbin subjects in V1. They stay labels in `role_to_access_level` (`app/deps/admin.py:15-19`).

### Examples (static policy, two tenants)

Policy fragment (shape only; Phase 0 does not attach it to routes):

```csv
p, TENANT_ADMIN, *, tenant.users, invite, allow
p, TENANT_OWNER, *, tenant.users, invite, allow
p, OWNER, *, tenant.users, invite, allow
p, ADMIN, *, tenant.users, invite, allow
```

There is no `TENANT_MEMBER` allow for `tenant.users` / `invite`.

| Request | Decision |
|---------|----------|
| `sub=TENANT_ADMIN`, `dom=17`, `obj=tenant.users`, `act=invite` | **Allow** (`p.dom=*` matches 17) |
| `sub=TENANT_MEMBER`, `dom=17`, `obj=tenant.users`, `act=invite` | **Deny** (no allow; no deny row required) |
| `sub=TENANT_OWNER`, `dom=42`, `obj=tenant.users`, `act=invite` | **Allow** (same static rows; domain 42 is the request tenant, not tenant 17’s membership) |
| `sub=TENANT_MEMBER`, `dom=42`, `obj=tenant.users`, `act=invite` | **Deny** |
| Caller is `TENANT_ADMIN` in tenant 17 but the host is tenant 42 | **Not a Casbin decision.** `get_current_user` returns 403 before a role for 42 is supplied (`app/deps/auth.py:99-103`, `:195`) |

---

## 3. Admin roles vs future operational FULL_ACCESS

Current code treats these four strings as both tenant admin and “full access”:

```7:12:app/deps/admin.py
TENANT_ADMIN_ROLES = frozenset({"OWNER", "ADMIN", "TENANT_ADMIN", "TENANT_OWNER"})
FULL_ACCESS_ROLES = frozenset({"OWNER", "ADMIN", "TENANT_ADMIN", "TENANT_OWNER"})
```

Invites write `FULL_ACCESS` as the role `TENANT_ADMIN` (`app/deps/admin.py:22-26`). That is current intended behavior, not a bypass.

**V1 policy:** duplicate the same allow rows for `OWNER`, `ADMIN`, `TENANT_ADMIN`, and `TENANT_OWNER` wherever `is_tenant_admin` or `has_full_access` is true today. Do not add a fifth subject. Do not change `access_level_to_role`.

**Later approved phase (not Phase 0):** introduce a new subject, for example `OPERATIONAL_FULL_ACCESS`, with operational allows and **no** `tenant.users.*` / People / email-config admin allows. Only new invites would persist that role, and only after the policy file grants it. Existing `TENANT_ADMIN` members stay on the four-role admin grant. No automatic downgrade.

---

## 4. The 11 unmapped operations

The report’s `NEEDS_APPROVAL.unmapped` set is these 11 routes. Classification:

| Method | Path | Class | Phase 0 treatment |
|--------|------|-------|-------------------|
| GET | `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc` | Infrastructure (FastAPI schema/UI) | Outside tenant RBAC |
| GET | `/`, `/healthz`, `/api/v1/health`, `/api/v1/healthz`, `/dashboard` | Infrastructure / static health or HTML (`app/main.py:182-208`) | Outside tenant RBAC |
| GET | `/api/v1/me` | Authenticated self-service | Any active member of the bound tenant. Not a tenant-admin capability |
| PATCH | `/api/v1/me/preferences` | Authenticated self-service | Same. Theme write for the caller only (`app/routers/me.py`) |

Public signup, login, password reset, invites, applicant links, webhooks, and platform-key routes were already classified in the inspection inventory. They are not part of these 11. Pre-auth flows stay on their current mechanisms (middleware allowlist / `PUBLIC_AUTH_PATHS` / applicant token / platform admin key). They are not Casbin membership checks.

`POST /api/v1/onboarding/driver-license/ocr` and `…/confirm` are **not** in the 11. They are authenticated tenant routes with no role symbol (inside the 97). They are tenant capabilities, not public pre-auth.

---

## 5. Fail-closed loader

Phase 0 loads the model and policy at process start and refuses to start if that load is not valid. Routes are not wrapped yet, so a **valid** load does not change HTTP authorization. An **invalid** load prevents the process from serving traffic.

| Condition | Behavior |
|-----------|----------|
| Model or policy file missing, unreadable, or rejected by Casbin | Startup failure. Do not serve with an empty enforcer |
| `# policy_version:` header ≠ `EXPECTED_POLICY_VERSION` in code | Startup failure |
| Registry contains a capability with no policy rows and no explicit “intentionally unenforced” flag | Startup failure |
| Request role not in `{OWNER, ADMIN, TENANT_ADMIN, TENANT_OWNER, TENANT_MEMBER}` | **403** `AUTHZ_FORBIDDEN` once a route is enforced. Unknown role is not allow |
| Enforced route’s capability is absent from the loaded registry | **503** `AUTHZ_POLICY_UNAVAILABLE` (configuration fault, not a user deny) |
| Enforcer failed or was cleared after startup | **503** `AUTHZ_POLICY_UNAVAILABLE` |
| Role is known, capability is known, no matching allow (and no deny row) | **403** `AUTHZ_FORBIDDEN` |

Versioning: one integer in the policy file header and one constant beside the loader. Rollback is `git revert` of `model.conf` / `policy.csv` and an API restart. There is no policy table and no online reload in V1. A bad file must fail startup rather than fall back to the previous in-memory snapshot, because V1 does not have a second source of truth.

Dependency order, when enforcement is later attached:

1. Tenant middleware (host tenant, active membership)
2. `get_current_user` (identity, session version, role for that tenant)
3. Entitlement dependency, where the route already has one
4. Casbin capability check
5. Domain service rules (load state, custody, payroll status, Fuel admin mapping)

Casbin does not replace step 5.

---

## 6. Ungated mutations vs service blocks

### Confirmed by source: no role gate

Category G (97) reaches the handler for any active member. Two of them are intentional self-service and stay that way: `PATCH /api/v1/me/preferences`, `POST /api/v1/auth/workspaces` (platform user, `app/deps/auth.py:21-47`).

The other **95** have no `is_tenant_admin`, `has_full_access`, Fuel capability, or People admin helper. `app/services/loads.py` has no role check. Trip, toll, and broker services were not found to consult `is_tenant_admin` / `has_full_access`. This audit did **not** execute those routes.

`READ_ONLY` is documented as the non-admin label for `/admin/users` (`app/deps/admin.py:10-11`), not as a global write ban. These 95 routes are a **missing role layer**, not a bypass of an existing deny. The operator-facing invite label “Read only” (`apps/web/src/pages/AdminUsersPage.tsx`) is broader than that comment. That mismatch is source-confirmed and runtime-untested.

Inside payroll, six mutations **do** use `require_tenant_admin` (category E) and these seven **do not**:

- `PATCH /api/v1/payroll/pay-periods/{pay_period_id}` (`app/routers/payroll.py:127`)
- `POST /api/v1/payroll/pay-profiles` (`:240`)
- `PATCH /api/v1/payroll/pay-profiles/{profile_id}` (`:308`)
- `POST /api/v1/payroll/pay-profiles/{profile_id}/deactivate` (`:340`)
- `POST /api/v1/payroll/pay-entries` (`:388`)
- `PATCH /api/v1/payroll/pay-entries/{entry_id}` (`:478`)
- `POST /api/v1/payroll/pay-entries/{entry_id}/void` (`:509`)

That split is an inconsistent gate inside one module. It is still not a bypass of a check that those seven handlers contain.

### Already blocked in services or handlers (not RBAC)

These rejects are domain or hard-wired behavior. A future Casbin allow must not remove them.

| Path | Block | Role-independent? |
|------|-------|-------------------|
| `DELETE /api/v1/drivers/{driver_id}` | Always 405 (`app/routers/drivers.py:244-249`) | Yes. Also missing auth deps; the method never deletes |
| `PATCH /api/v1/loads/{load_id}` with `status=ready` | `_guard_update_payload` / `LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT` (`app/services/loads.py:194`) | Yes. Other PATCH fields still apply for any member |
| `POST /api/v1/loads/{load_id}/mark-ready` | `mark_load_ready` (`app/services/loads.py:634`) accepts only a valid draft→ready transition | Yes when the transition is illegal. A legal transition is not role-blocked |
| `DELETE /api/v1/loads/{load_id}` version mismatch | `delete_load` returns 404/409 (`app/services/loads.py:563-585`) | Yes. A matching `concurrency_version` **does** `DELETE` the row |

### Tests required before any later enforcement

Do not run these against production. Use the existing isolated tenant test DB only after an implementation phase is approved.

| Case | Platform mode | Tenant-local mode |
|------|----------------|-------------------|
| Role source | `PlatformTenantMember.role` | `TenantWorkspaceMember.role` |
| `OWNER`, `ADMIN`, `TENANT_ADMIN`, `TENANT_OWNER` | Same allow for a current admin capability | Same allow |
| `TENANT_MEMBER` on a current admin capability | 403 once enforced | 403 once enforced |
| Inactive user / inactive membership / session version mismatch | Existing 401/403 from `get_current_user` (`app/deps/auth.py:127-146` and `:182-195`) | Same |
| JWT tenant ≠ host tenant | 403 before Casbin | 403 before Casbin |
| Unknown role string | 403 | 403 |
| Policy file removed | Process does not start | Same (policy is not per auth mode) |

Existing unit coverage to keep: `tests/test_require_tenant_admin_roles.py`, `tests/test_fuel_segment_0a.py` (admin-only map), `tests/test_cross_tenant_host_enforcement.py`, `tests/test_tenant_auth_matrix.py`. None of these were re-run for this note.

---

## 7. Fuel (V1)

Leave `fuel_capability_allowed` as “capability name must be in the admin set, and `is_tenant_admin(role)`” (`app/deps/fuel_rbac.py:31-50`).

V1 static policy, if it mentions Fuel at all, grants each existing `fuel.*` capability only to `OWNER`, `ADMIN`, `TENANT_ADMIN`, and `TENANT_OWNER`. No `TENANT_MEMBER` Fuel allow. No operational FULL_ACCESS Fuel split. Granular Fuel grants are a later approval, not Phase 0.

---

## 8. Load integrity (frozen)

`DELETE /api/v1/loads/{load_id}` (`app/routers/loads.py:243-253`) calls `delete_load`, which executes `delete(Load)` when `tenant_id` and `concurrency_version` match (`app/services/loads.py:563-574`).

`docs/load_trip/MASTER.md` item I5 is still **NOT IMPLEMENTED**: hard delete is unsafe; the open decision is soft-cancel versus block. That decision stays open. Phase 0 does not add `loads.delete`, does not change `delete_load`, and does not treat a Casbin allow or deny as the I5 ruling.

Mark Ready, writer freeze, custody transitions, and audit atomicity stay in the service layer.

---

## 9. Corrected risk ratings

Ratings below replace the inspection register for decision-making. “Bypass” means a caller skips a check the code already attempts. “Missing layer” means no such check exists.

| ID | Corrected rating | Class | Why the earlier rating was wrong or incomplete |
|----|------------------|-------|------------------------------------------------|
| R1 operational writes by `TENANT_MEMBER` | **HIGH missing layer**, not CRITICAL bypass | Source-confirmed, runtime-untested | `READ_ONLY` is specified for `/admin/users` (`app/deps/admin.py:10-11`). There is no server deny to skip. The invite label is still broader than the code comment |
| R2 load hard delete | **HIGH integrity gap**, not an auth bypass | Source-confirmed | I5 is an open domain policy. Any active member can call the route because of R1’s missing layer; the service then deletes |
| R3 `GET /api/v1/admin/users` | **Not a finding** for Phase 0 | Intended | Docstring: READ_ONLY and FULL_ACCESS may list (`app/routers/tenant_admin.py:475`) |
| R4 `FULL_ACCESS` → `TENANT_ADMIN` | **Not a finding** for Phase 0 | Intended | `access_level_to_role` (`app/deps/admin.py:22-26`). Future split is section 3 |
| R5 Fuel admin-only | **Not a bypass** | Intended restriction | `app/deps/fuel_rbac.py:31-50`. Keep in V1 |
| R6 sign-in security GET | **Not a finding** for Phase 0 | Intended | Docstring includes READ_ONLY (`app/routers/tenant_admin.py:518`) |
| R7 Microsoft webhook | **Hypothesis only** | Not confirmed | `clientState` is checked (`app/routers/microsoft_graph_webhook.py:46-48`). No forged-call evidence in this audit |
| R8 driver DELETE without deps | **LOW defense-in-depth** | Source-confirmed non-bypass | Handler always returns 405 |
| R9 payroll UI uses `hasRole(me, "TENANT_ADMIN")` | **LOW UI under-grant** | Source-confirmed | Backend admin gate also allows `OWNER` / `ADMIN` / `TENANT_OWNER` (`app/deps/admin.py:8`). Hiding a button is not a server bypass. The seven payroll routes in section 6 remain a missing server gate |

---

## 10. Phase 0 boundary

Phase 0 may add only:

- `app/authz/casbin/model.conf` — the model in section 2
- `app/authz/casbin/policy.csv` — allow rows that **restate** categories A–F for the four admin roles, plus Fuel admin-only
- A loader that validates version, files, and registry at startup and fail-closes
- Unit tests of that loader and of role→decision for both role-resolution inputs (platform member role vs tenant workspace role), with no production database

Phase 0 must **not**:

- Wrap existing routes with `require_capability`
- Change `access_level_to_role`, Fuel’s admin map, or any Load/Trip service
- Add policy tables or migrations
- Deny or allow live traffic differently when the policy file is valid

`TENANT_MEMBER` operational routes stay reachable exactly as today, because Phase 0 does not sit on the request path.

### Owner decision required before Phase 0

**None**, if this boundary is accepted: Phase 0 is a non-enforcing, fail-closed policy package.

These are explicitly **not** Phase 0 decisions (do not block the package above):

- Whether `TENANT_MEMBER` may keep operational writes (enforcement phase)
- A separate operational FULL_ACCESS role (later invite phase)
- Granular Fuel grants
- I5 soft-cancel vs block
- Whether READ_ONLY should lose `GET /api/v1/admin/users` or the sign-in security panel
- Microsoft Graph webhook hardening
