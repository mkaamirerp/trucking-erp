# Login / Auth

Purpose:
Login, authentication, JWT/session, password reset, users, and tenant auth/security specific to authentication.

**Identity architecture authority:** [`LOGIN_IDENTITY_ARCHITECTURE_LOCK.md`](LOGIN_IDENTITY_ARCHITECTURE_LOCK.md) (sole lock — no duplicate master).

**Security posture:** **SECURITY REVIEW RECORDED — REMEDIATION DEFERRED** — consolidated backlog [`AUTH_SECURITY_REVIEW_BACKLOG.md`](AUTH_SECURITY_REVIEW_BACKLOG.md) (findings A1–A8, parked). Alias: [`SECURITY_AUDIT_RECORD.md`](SECURITY_AUDIT_RECORD.md).

Repository tracking: `TODO.md` → **AUTH SECURITY HARDENING — PARKED**.

Current files:

| File | Role |
|------|------|
| `LOGIN_IDENTITY_ARCHITECTURE_LOCK.md` | Frozen target architecture |
| `AUTH_SECURITY_REVIEW_BACKLOG.md` | Consolidated security findings + recommendations (not Gold) |
| `SECURITY_AUDIT_RECORD.md` | Pointer to backlog |
| `TENANT_LOGIN_MANUAL.md` | Implemented behavior manual |
| `IDENTITY_AUTH_MODEL_REPORT.md` | Historical implementation report |
| `operations/` | Runbooks |

Future structure:
Module TODO consolidation and verification evidence as needed (no second architecture master).
