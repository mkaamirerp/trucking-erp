# Signup & Setup Forms — Strict Input, Permissive Read (LOCKED)

**Golden rule (must not be violated):**
- **ALL** user-entered or OCR-extracted data **MUST** be strictly validated at **write time**.
- **Lists, dashboards, and summaries** MUST be permissive at **read time** and never fail or hide rows due to validation.

**Cursor must never relax input validation to "fix UI issues".**

---

## A) STRICT INPUT RULE (Signup, Setup, Forms, OCR)

**Applies to:** Signup form, workspace/company setup form, add/update driver, OCR import (before commit), any POST/PUT/PATCH endpoint.

**Cursor MUST enforce:**

| Area | Rule |
|------|------|
| **Email** | Valid RFC email (no `@demo.local`, no placeholders). |
| **Phone** | Normalize to digits; length 7–15. |
| **Passwords** | Strength rules as defined (no weakening). |
| **Names** | Required, non-empty, trimmed. |
| **Country-specific fields** | Required based on country (US/CA/etc.). |
| **Dates** | No future dates unless explicitly allowed. |
| **Business rules** | `termination_date` ⇒ `is_active = false`; no conflicting states. |
| **OCR** | Low-confidence fields → `needs_review = true`; dirty OCR values must NOT be auto-approved. |

**Cursor must NOT:**
- Auto-coerce invalid input silently.
- Replace invalid values with blanks on input.
- Skip validation "to make UI work".

If validation fails → **reject write** or save as **draft / pending review**.

---

## B) PERMISSIVE READ RULE (Lists, Dashboard, Summary)

**Applies to:** Driver list, dashboard summary, tables/reports, KPIs.

**Cursor MUST:**
- Use **permissive output schemas** (e.g. `DriverListOut`).
- **Never** use strict schemas (EmailStr, strict phone/date validators) for list endpoints.
- Render rows even if fields are dirty.
- Prefer normalized values, fall back to raw.
- Show warnings/badges — **never hide data**.

---

## C) SIGNUP FORM — CURRENT FIELD CONTRACT (DO NOT GUESS)

**Required fields (strict):**
- `workspace_slug` (string, slug-safe)
- `first_name`
- `last_name`
- `email`
- `confirm_email`
- `phone`
- `company_name`
- `country`
- `password`
- `confirm_password`
- `plan`
- `accept_terms` (must be true)
- `is_owner_or_admin` (boolean)

**Rules Cursor must respect:**
- Frontend field names **MUST** match backend schema (`workspace_slug`, not `slug`).
- Email + `confirm_email` must match.
- Password + `confirm_password` must match.
- Country selection controls downstream required fields (do not hardcode).

---

## D) ABSOLUTE DO-NOTs FOR CURSOR

- ❌ Do **NOT** change validation rules to fix list bugs.
- ❌ Do **NOT** reuse strict output schemas in list endpoints.
- ❌ Do **NOT** "fix" dirty DB data by weakening input validation.
- ❌ Do **NOT** invent new fields or rename fields without backend agreement.

---

## One-line summary (remember this)

**Strict on input (signup, setup, OCR). Permissive on read (lists, dashboards). Never hide data. Never weaken validation.**

Reference: `docs/driver-list-root-cause-and-prevention.md` for driver list/summary pattern and prevention checklist.
