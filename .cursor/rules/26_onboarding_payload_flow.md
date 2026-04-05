# Onboarding Payload Flow (LOCKED)

**Step-1 signup data is stored as a server-side onboarding payload (platform DB), not as final company profile.**

## Flow

1. **Step 1 — Signup:** Collect workspace slug, owner info, company name, address, country, plan, etc. Store as **one JSON payload** in `platform_onboarding_payloads` (tenant_id, payload_json, expires_at, consumed_at). Do **not** write to `platform_company_profiles` yet. Only create: user, tenant, membership (and subscription).

2. **Step 2 — OTP / Verify:** Provision tenant DB; mark tenant db_status=READY. Do **not** copy company data anywhere yet.

3. **Step 3 — Company Setup Page:** Backend returns **prefill** from onboarding payload (read-only: company name, country, owner email, address). **required_remaining_fields** (country-driven) → editable inputs (address, USDOT/MC/CVOR/etc.). User fills only what’s missing.

4. **Step 4 — Complete Setup:** One submit does the real writes: write final company profile + compliance + address to platform (and optionally tenant DB as source of truth). Set `platform_company_profiles.setup_completed_at = now()`. Mark onboarding payload **consumed_at = now()** (or delete it).

## Rules Cursor must respect

- **Onboarding payload:** Stored in `platform_onboarding_payloads`; expires (e.g. 7 days); consumed or deleted after setup completion.
- **Company Setup page:** Must prefill Step-1 values **read-only** from that payload and only collect the remaining fields (address editable, USDOT/MC/CVOR).
- **Complete Setup:** Write final data **once** to platform company profile; consume/delete the payload. No mid-flow copying of partial company profile.

## Endpoints

- `GET /api/v1/public/company-setup/prefill` — returns prefill (read-only) + required_remaining_fields.
- `POST /api/v1/public/company-setup` — final commit: merge prefill + form, write profile, consume payload.

Reference: `docs/signup-dashboard-flow.md`, `app/models/platform.py` (PlatformOnboardingPayload).
