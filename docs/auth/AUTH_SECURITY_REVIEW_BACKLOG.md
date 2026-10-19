# Auth security review backlog (remediation deferred)

**Status:** **SECURITY REVIEW RECORDED — REMEDIATION DEFERRED**

**Owner decision:** Auth remediation is **PARKED**. Findings and recommendations are preserved for later issue-by-issue approval.

**Not Auth Gold.** Prior security work is real and valuable; it does **not** close the outstanding items below.

**Architecture authority (unchanged):** [`LOGIN_IDENTITY_ARCHITECTURE_LOCK.md`](LOGIN_IDENTITY_ARCHITECTURE_LOCK.md) — sole identity/credential lock. This backlog is **not** a competing architecture master.

---

## Independent Security Review — Audit Baseline

| Field | Value |
|-------|--------|
| **Independent reviewer** | ChatGPT Work |
| **Repository** | `mkaamirerp/trucking-erp` |
| **Branch** | `main` |
| **Audited baseline commit** | `ede7ba80d0154f39db5a4f23813b7eaceae99030` |
| **Earlier security commits reviewed** | `3225303c43da0e787d86486d49407e4754aaca69`, `9f0bc83bbf9a5410b99b919338eae0950079ac64` |
| **Review scope** | Public GitHub source code, including previous authentication security changes |
| **Review method** | Read-only investigation |

ChatGPT Work performed **no** code changes, commits, pushes, or deployments.

### Review limitations

- **69** backend tests passed in the review environment.
- **3** failed due to hardcoded environment paths (not treated as product defects in this record).
- Additional suites blocked by missing **zxingcpp**.
- **No** live production EC2 verification.
- **No** production database or browser security testing.

### Relationship to earlier security commits

Commits `3225303c…` and `9f0bc83b…` implement real protections (see below). The findings **A1–A8** were identified **after** considering those commits. **Do not** describe those commits as fixing or closing A1–A8.

---

## Classification legend

| Tag | Meaning |
|-----|---------|
| **CONFIRMED CODE FINDING** | Matches known code/architecture behavior; fix deferred |
| **REPORTED / REPRODUCTION PENDING** | Recorded from review; not re-verified on EC2 in this doc pass |
| **LIVE CONFIGURATION UNVERIFIED** | Effective runtime/SSM vs compose defaults not confirmed |
| **OWNER DECISION REQUIRED** | Policy or architecture approval before implementation |

---

## Existing protections (completed — not “fully hardened”)

| Protection | Notes |
|------------|--------|
| Server-controlled reset-link origins | In place |
| Hashed random reset tokens and expiry | In place |
| JWT secret validation (no hardcoded fallback) | In place |
| Restricted JWT signing algorithm | In place |
| HttpOnly authentication cookies | In place |
| Login rate limiting | In place |
| OTP step-up authentication | In place |
| Existing credential synchronization safeguards | Partial — see **A3** |

---

## Outstanding findings and recommendations

### A1 — HIGH — Secure cookies and reset-token logging

| | |
|--|--|
| **Classification** | **LIVE CONFIGURATION UNVERIFIED**; **REPORTED / REPRODUCTION PENDING** (logging) |

**Evidence (review):**

- Docker Compose includes `SECURE_COOKIES=false`.
- Auth router conditionally logs full reset URLs (credential exposure risk in logs).

**Recommendations (deferred):**

- Enforce `Secure` cookies in production and staging.
- Eliminate raw reset-token URL logging.
- Verify effective EC2/SSM configuration.
- Inspect logging exposure without displaying secrets in operator output.

---

### A2 — HIGH — Password-reset consumption is not atomic

| | |
|--|--|
| **Classification** | **CONFIRMED CODE FINDING**; **REPORTED / REPRODUCTION PENDING** (concurrent dual-success repro) |

**Recommendations (deferred):**

- Introduce transaction-safe token consumption (single-use CAS).
- Preserve `session_version` correctness in the same transaction boundary.
- Add PostgreSQL concurrency regression tests for parallel reset requests.

---

### A3 — HIGH — Credential synchronization / identity authority

| | |
|--|--|
| **Classification** | **CONFIRMED CODE FINDING**; **OWNER DECISION REQUIRED** |

**Recommendations (deferred):**

- Follow frozen **authority-per-identity** architecture ([`LOGIN_IDENTITY_ARCHITECTURE_LOCK.md`](LOGIN_IDENTITY_ARCHITECTURE_LOCK.md)).
- Eliminate **normal password dual-write** as the target design (not ad-hoc mirror sync).
- Record partial-failure behavior and safe recovery requirements.
- Do **not** redesign authentication without owner approval.

---

### A4 — MEDIUM — Workspace password-reset routing

| | |
|--|--|
| **Classification** | **REPORTED / REPRODUCTION PENDING** |

**Evidence (review):** Public allowlist may bypass tenant resolution; workspace-host reset reportedly reached handler with `tenant_id=null`.

**Recommendations (deferred):**

- Verify public allowlist behavior end-to-end.
- Resolve workspace context correctly on workspace hosts.
- Preserve intentional apex reset functionality where product requires it.
- Add host-routing regression tests (middleware → handler).

---

### A5 — MEDIUM — Logout and refresh-token revocation

| | |
|--|--|
| **Classification** | **CONFIRMED CODE FINDING**; **OWNER DECISION REQUIRED** |

**Recommendations (deferred):**

- Define **single-device** versus **all-device** logout policy.
- Evaluate per-session / token-family revocation (blocklist, rotation, short TTL).
- Record refresh cookie path and transport constraints.
- Consider refresh rotation and reuse detection.

**IMPORTANT — do not implement without approval:** A proposed **`session_version` bump on every logout** would revoke **all devices**; that is **not** an approved default from this review.

---

### A6 — MEDIUM — bcrypt 72-byte password limitation

| | |
|--|--|
| **Classification** | **CONFIRMED CODE FINDING**; **OWNER DECISION REQUIRED** |

**Recommendations (deferred):**

- Investigate password byte-length policy (UX + validation).
- Design backward-compatible hash migration if pre-hashing or similar is chosen.
- Preserve existing account access for current hashes.

---

### A7 — HARDENING — JWT required claims

| | |
|--|--|
| **Classification** | **CONFIRMED CODE FINDING** |

**Recommendations (deferred):**

- Require essential claims during JWT verification.
- Cover at minimum: `exp`, `sub`, token `type`, `sv` (session version), and tenant binding where applicable.
- Add malformed-token regression tests.

---

### A8 — SECURITY FINDING — Invite acceptance may reactivate suspended users

| | |
|--|--|
| **Classification** | **CONFIRMED CODE FINDING**; **OWNER DECISION REQUIRED** (policy) |

**Evidence (review):** Existing invite acceptance updates membership status to **active**, which may reactivate suspended users without an explicit reactivation policy.

**Recommendations (deferred):**

- Verify actual account and membership status enums in code and DB.
- Define invitation eligibility and reactivation policy (suspended/blocked users).
- Reject unauthorized reactivation on accept.
- Preserve invite for retry when validation fails (do not consume invite on policy rejection).
- Add regression tests for suspended/blocked invite acceptance paths.

---

## Scheduling and boundaries

- **Not currently scheduled** for implementation.
- **Issue-by-issue owner approval** required before Auth code changes.
- **Do not mix** with Load/Trip Antigravity remediation, Issue 26 deploy track, or parser work.
- **Production verification pending** for cookies, reset, revocation, and workspace routing.

---

## Related documentation (`docs/auth/`)

| Document | Role |
|----------|------|
| [`LOGIN_IDENTITY_ARCHITECTURE_LOCK.md`](LOGIN_IDENTITY_ARCHITECTURE_LOCK.md) | Frozen identity architecture (do not override) |
| [`AUTH_SECURITY_REVIEW_BACKLOG.md`](AUTH_SECURITY_REVIEW_BACKLOG.md) | **This file** — consolidated security backlog |
| [`SECURITY_AUDIT_RECORD.md`](SECURITY_AUDIT_RECORD.md) | Pointer to this backlog (legacy alias) |
| [`TENANT_LOGIN_MANUAL.md`](TENANT_LOGIN_MANUAL.md) | Implemented behavior manual |
| [`IDENTITY_AUTH_MODEL_REPORT.md`](IDENTITY_AUTH_MODEL_REPORT.md) | Historical report |
| [`README.md`](README.md) | Module index |

Repository checklist: `TODO.md` → **AUTH SECURITY HARDENING — PARKED**.
