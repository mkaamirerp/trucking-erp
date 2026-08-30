# TruckERP Login & Identity Architecture Lock

**Status:** FROZEN TARGET / SOURCE OF TRUTH FOR AUTH IMPLEMENTATION  
**Date:** 2026-08-30  
**Scope:** Login identity, user origin, workspace membership, password/reset authority, session authority, multi-tenant identity linking, and migration safety.

This document freezes the intended TruckERP identity model before the auth code is changed. It exists because the current `TENANT_LOGIN_MANUAL.md` intentionally describes current implementation, while this document defines the target architecture that implementation must converge to.

---

## 1. Core rule: identity origin determines credential authority

Email is an attribute. **Email is never an identity-link key by itself.**

TruckERP has two valid identity origins:

1. **Platform identity** — a global TruckERP account created by the main signup/subscription/account flow. A `PlatformUser` may belong to one or many tenant workspaces.
2. **Tenant-local identity** — a user created inside one tenant workspace by that tenant. A tenant-local user belongs only to that tenant and must not automatically become a `PlatformUser`.

A person may have both a platform identity and a tenant-local representation only when there is an **explicit trusted link** between the two records.

---

## 2. Identity types

### A. Platform identity

- Stored in `platform_users` / `PlatformUser`.
- Global across TruckERP.
- May have access to multiple tenants.
- Owns one global platform credential and one platform `session_version`.
- Example origin: main TruckERP signup/subscription flow.

### B. Tenant-local identity

- Stored in tenant DB `tenant_users` / `TenantUser`.
- Scoped to exactly one tenant.
- Created by tenant administration inside that workspace.
- Owns its tenant-local credential and tenant-local `session_version`.
- Must not require or create a `PlatformUser` merely to log into that tenant.

### C. Platform-linked tenant identity

A platform user may also need a local `TenantUser` row inside each tenant they operate in.

The relationship is explicit:

`PlatformUser -> PlatformTenantUserMap -> TenantUser`

One `PlatformUser` may therefore map to one `TenantUser` in Tenant A, another `TenantUser` in Tenant B, and so on.

The tenant row is the local workspace representation. The **credential authority remains the global `PlatformUser`** for a trusted platform-linked identity.

---

## 3. User creation matrix

| Origin | PlatformUser | TenantUser | Explicit map | Credential authority |
|---|---:|---:|---:|---|
| Main TruckERP signup/subscription owner | Yes | Yes, in created tenant | Yes | PlatformUser |
| Existing platform user deliberately added to another tenant | Existing | Yes, in that tenant | Yes | PlatformUser |
| User created from Tenant Admin -> Users | No | Yes | No | TenantUser |
| TruckERP platform-only operator | Yes | Only if deliberately added to a tenant | Only when added | PlatformUser |

### Non-negotiable creation rule

**Tenant Admin -> Add/Invite User must not create a `PlatformUser`, platform membership, or platform-to-tenant map for a normal tenant-local account.**

Likewise, main signup/subscription must create the platform identity and the explicit tenant representation/link required for the new workspace owner.

---

## 4. Explicit identity link; never infer from email

`PlatformTenantUserMap` is the bridge between a global platform identity and one tenant-local representation.

The map must carry explicit provenance, recommended as `identity_link_type` (name may vary only if an equivalent explicit field is clearer).

Recommended values:

- `SUBSCRIPTION_OWNER` — created by main TruckERP signup/subscription ownership flow.
- `PLATFORM_MEMBER` — existing global platform user deliberately granted access to another tenant.
- `EXPLICIT_LINK` — separately verified/admin-approved identity link.
- `LEGACY_COMPAT` — historical/migration mapping whose provenance is not yet trusted for the new authority model.

### Hard rule

The following is forbidden:

`same normalized email in platform_users and tenant_users => same identity`

Matching email alone must never create a map, change credential authority, synchronize a password, or merge accounts.

---

## 5. Single credential authority; no normal password dual-write

The final architecture does **not** maintain two independently authoritative password copies for one linked identity.

### Trusted platform-linked identity

For `SUBSCRIPTION_OWNER`, `PLATFORM_MEMBER`, or `EXPLICIT_LINK`:

- `PlatformUser.password_hash` is authoritative.
- `PlatformUser.session_version` is authoritative.
- Workspace login verifies the mapped `PlatformUser` credential.
- Password change/reset changes the global platform credential once.
- The new password applies to every tenant workspace explicitly linked to that same `PlatformUser`.
- Tenant credential fields for that linked `TenantUser` are not login authority and should ultimately be unused/null after safe migration.

### Tenant-local identity

When there is no trusted platform link:

- `TenantUser.password_hash` is authoritative.
- `TenantUser.session_version` is authoritative.
- Password change/reset affects only that tenant-local identity.
- Platform credentials must not be read, created, modified, or synchronized for this account.

### Consequence

Normal password flows must not hash once for platform and again for tenant, and must not attempt to keep two password stores synchronized as the long-term design. Credential routing is determined by explicit identity authority.

---

## 6. Workspace login must resolve authority per identity, not per tenant

The long-term login decision cannot be a single `tenant_auth_mode` choice for the whole workspace because one tenant may contain both:

- platform-linked owner/platform members, and
- tenant-local dispatcher/manager/accountant/other users.

Target workspace login (`{tenant}.truckerp.me/login`):

1. Resolve tenant from host.
2. Normalize submitted email.
3. Load `TenantUser` by `(tenant_id, email_norm)` and require active `TenantWorkspaceMember`.
4. Inspect `PlatformTenantUserMap` for that exact tenant user.
5. If there is a **trusted** platform link, load the exact mapped `PlatformUser` by ID and verify the platform credential/session authority.
6. If there is **no** platform link, verify the tenant-local credential/session authority.
7. If mapping is `LEGACY_COMPAT`, use only an explicitly defined compatibility path; do not silently promote it based on email.
8. Apply Turnstile/OTP/rate-limit protections around the resolved identity without changing credential authority.

### `tenant_auth_mode`

`tenant_auth_mode` may remain temporarily for migration/compatibility, but it is **not the final per-user credential authority selector**. Authority is per identity.

---

## 7. Apex/main-site login

A tenant-local user cannot be safely resolved from the apex host because the same email could legitimately exist independently in multiple tenants.

Therefore:

- Apex/main-site identity is platform-oriented.
- Tenant-local users sign in through their workspace URL.
- Platform users may belong to multiple tenant spaces.
- If a platform user has multiple tenant memberships, the product may ask the user to select a workspace or redirect to a workspace chooser.
- Apex must never search tenant databases by matching email and guess an identity.

---

## 8. Password change and Forgot Password routing

### Workspace host

Resolve the tenant-local user first, then its explicit identity link.

- Trusted platform link -> password/reset operation belongs to `PlatformUser` and is global for that platform identity.
- No trusted platform link -> password/reset operation belongs only to `TenantUser` in the current tenant.
- `LEGACY_COMPAT` -> do not guess; use the compatibility policy until explicitly classified.

### Apex host

- Password/reset operations are for `PlatformUser` identities only.
- Do not fan out by matching email into tenant databases.

### Security rule

A reset may never choose platform vs tenant solely because the same email exists in both stores.

---

## 9. Session/JWT authority

A token/session must identify which authority issued it.

Recommended explicit claim/metadata: `identity_type = platform | tenant`.

### Platform-linked identity

- subject: PlatformUser ID
- session invalidation source: `PlatformUser.session_version`
- access remains limited to tenants for which explicit membership/link rules pass

### Tenant-local identity

- subject: TenantUser ID
- token must be tenant-scoped
- session invalidation source: `TenantUser.session_version`
- token from Tenant A must never authorize Tenant B

There must be no ambiguous interpretation of the same `sub` value as sometimes platform and sometimes tenant without an explicit identity type.

---

## 10. Membership and access

Every user who operates inside a tenant must have an active tenant workspace access record (`TenantWorkspaceMember` or its eventual canonical equivalent).

Platform-linked users may additionally have platform membership/control-plane rows for global workspace discovery, subscription ownership, or platform access.

Tenant-local users must not require a `PlatformUser`/platform membership merely because they need workspace access.

---

## 11. Multi-tenant platform identity

One `PlatformUser` may belong to many tenant spaces.

Example:

- PlatformUser P1 -> Tenant A / TenantUser 10
- PlatformUser P1 -> Tenant B / TenantUser 27
- PlatformUser P1 -> Tenant C / TenantUser 4

All trusted mappings refer to the same global platform credential. A global password change therefore does not require independent password hashes per tenant.

Tenant-local users remain isolated and are unaffected.

---

## 12. Legacy mapping migration safety

Existing `PlatformTenantUserMap` rows were created under earlier dual-write/cutover/rollback behavior. Existing map presence alone must not automatically be treated as proof of a trusted platform-origin identity until provenance is established.

Migration rules:

1. Add explicit link provenance/type.
2. Existing uncertain rows default/classify as `LEGACY_COMPAT`.
3. Do not bulk promote mappings based on equal email.
4. Do not bulk copy password hashes in either direction.
5. Do not automatically reconcile during Alembic migrations.
6. Trusted rows may be classified from provable creation/membership provenance, with tests and an audit report before production mutation.
7. Any destructive cleanup of redundant credential fields is a later migration after login/reset behavior is proven.

---

## 13. August 2026 incident lesson

The incident demonstrated the danger of two credential stores being treated as competing authorities: a password change reached one store while fresh login verified the other, and an existing session masked the mismatch.

The permanent prevention is **not** indefinite password mirroring. It is unambiguous identity authority:

- platform-linked identity -> one global platform credential;
- tenant-local identity -> one tenant credential;
- explicit map/provenance decides the relationship;
- email never decides it.

Reconciliation scripts must not be used during forensics unless an explicit recovery action is approved, because they can destroy evidence and overwrite the newer credential.

---

## 14. Required regression invariants

Implementation is not complete until tests prove all of the following:

1. Tenant Admin-created user produces a `TenantUser` and workspace membership only; no `PlatformUser` is created.
2. Main signup/subscription owner produces a `PlatformUser`, tenant representation, and trusted `SUBSCRIPTION_OWNER` mapping.
3. Same email in platform and tenant with **no map** remains two independent identities.
4. Same email in different tenant DBs remains independent unless each tenant has an explicit map to the platform identity.
5. Trusted platform-linked workspace login verifies `PlatformUser.password_hash`, not a stale tenant hash.
6. Tenant-local workspace login verifies `TenantUser.password_hash` and never touches platform credentials.
7. One PlatformUser linked to two or more tenants uses the same global platform credential in every linked workspace.
8. Platform password reset/change invalidates the platform session version and works across all trusted linked workspaces without password mirroring.
9. Tenant-local password reset/change changes only that tenant-local identity.
10. A legacy mapping is never silently promoted to trusted because email matches.
11. Tenant-local JWT/session cannot be used in another tenant.
12. Platform-linked and tenant-local users can coexist and log in correctly inside the **same tenant**, proving login authority is per identity rather than tenant-wide.
13. No normal application password path performs automatic platform<->tenant password hash synchronization.

---

## 15. Operational guardrails

- No production password reset, reconcile, auth-mode flip, or credential migration as part of implementing this lock unless separately approved.
- Credential repair/reconcile tools are read-only by default and must not run automatically from Alembic.
- Before any production identity migration, run a read-only inventory of platform users, tenant users, maps, link provenance, and affected memberships.
- Never log plaintext passwords, password hashes, reset tokens, cookies, or JWTs.
- Auth changes must be isolated from DL/OpenCV, realtime DL, and unfinished Turnstile work.

---

## 16. Documentation follow-through

`TENANT_LOGIN_MANUAL.md` currently describes implemented behavior. After the implementation governed by this architecture lock lands, update that manual so it describes the new per-identity login/reset behavior.

`IDENTITY_AUTH_MODEL_REPORT.md` is a historical implementation report and must not override this architecture lock. After implementation, either regenerate it or mark it superseded/current as appropriate.

---

## Frozen summary

**Identity origin determines credential authority.**  
**Email never links identities.**  
**Tenant-created users stay tenant-local.**  
**Platform users may belong to multiple tenants.**  
**Trusted platform-to-tenant relationships are explicit and provenance-tagged.**  
**Platform-linked identities use one global PlatformUser credential.**  
**Tenant-local identities use one tenant credential.**  
**Login and password reset choose authority per identity, not per tenant.**  
**Normal password dual-write is not the final architecture.**
