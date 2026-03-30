# Platform admin web shell — posture and browser threat model

This document is the **browser-facing security report** for the internal `/platform` control-plane UI and its shared HTTP helper (`apps/web/src/lib/platformAdminFetch.ts`). It is meant for reviewers and operators, not end users.

## What shipped

- **Routes:** `/platform`, `/platform/tenants`, `/platform/tenants/:id`, `/platform/login-failures` (React app).
- **API:** `GET /api/v1/platform/login-failures` (and existing `/api/v1/platform/tenants*`), all gated by **`X-Platform-Admin-Key`** on the backend.
- **Apex-only UI:** The shell is wrapped so it does not present as normal product UI on workspace subdomains (`PlatformApexGate` — see `apps/web/src/components/PlatformApexGate.tsx`).

## Shared fetch layer

All platform calls intended for operators should go through **`platformAdminFetch`** / **`platformAdminJson`** so that:

- The header name and wiring stay in one place.
- **401** is turned into a typed **`PlatformAdminUnauthorizedError`** (UI can prompt for a new key).
- Non-OK responses get a consistent **`PlatformAdminHttpError`** with status and message.

Automated checks: `cd apps/web && npm run test` runs `src/lib/platformAdminFetch.test.ts`.

## sessionStorage API key — intentional but temporary

The shell stores the operator’s **`X-Platform-Admin-Key`** in **`sessionStorage`** (see `getPlatformAdminApiKey` / `setPlatformAdminApiKey`).

**Why this is acceptable only as an internal tool step**

- The value is **readable by any script on the page**. A successful **XSS** (or a malicious browser extension) could **exfiltrate** the key.
- It is **not** an httpOnly cookie, so it does not benefit from that cookie hardening model.
- Operators must treat the key like a **high-privilege secret**: short-lived, rotated if exposed, used only on trusted machines and networks.

**Why we still did it (for now)**

- Centralizing the key in one place is **cleaner and safer operationally** than re-implementing header logic per page.
- It **does not** change the server contract: the backend still validates the key; this is purely how the **browser** remembers it between requests in-session.

**Recommended long-term direction** (when you replace the shared-secret-in-browser pattern)

- **httpOnly, Secure, SameSite** session cookie after real **platform admin** auth, **or**
- A **server-side BFF** that holds credentials and proxies `/platform` API calls (browser never sees the raw admin key).

The platform DB already has foundations for `platform_admins`-style login; this shell deliberately **does not** implement that flow yet.

## Summary

| Topic                         | Status |
|------------------------------|--------|
| Backend enforcement          | Required `X-Platform-Admin-Key` (unchanged) |
| Browser key storage          | sessionStorage — **short-term**, XSS-sensitive |
| UI host separation           | Apex-only gate for `/platform` |
| Centralized client HTTP      | `platformAdminFetch` + Vitest |
| Final security model         | httpOnly session or BFF — **not done in this step** |
