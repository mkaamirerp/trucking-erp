# Signup → Company Profile Field Report

**Date:** 2026-03-07  
**Status:** Implemented

## Summary

The signup form collects full business identity data. This report documents where each field ends up, canonical storage, persistence guarantees, repair/fallback behavior, and the final Company Profile API response shape.

---

## Field Mapping

| Signup Field        | Stored at Signup                          | After Company-Setup Canonical Location           | Notes |
|---------------------|-------------------------------------------|--------------------------------------------------|-------|
| company_legal_name  | `payload_json.company_legal_name`         | `platform_company_profiles.legal_name`           | Also `platform_tenants.name` initially |
| address (street)    | `payload_json.address.street`             | `platform_company_profiles.address_street`       | Required at signup |
| address (city)      | `payload_json.address.city`              | `platform_company_profiles.address_city`         | |
| address (region)    | `payload_json.address.region`             | `platform_company_profiles.address_region`       | |
| address (postal)    | `payload_json.address.postal`             | `platform_company_profiles.address_postal`       | |
| address (country)    | `payload_json.address.country`            | `platform_company_profiles.address_country`      | |
| phone               | `payload_json.phone`                      | `platform_company_profiles.company_phone`       | Also `platform_users.phone` (owner) |
| email               | `payload_json.email`                      | `platform_company_profiles.company_email`       | Also `platform_users.email` (owner) |
| first_name          | `payload_json.first_name`                 | `platform_users.first_name`                      | User, not company |
| last_name           | `payload_json.last_name`                  | `platform_users.last_name`                      | User, not company |
| workspace_slug      | `payload_json.workspace_slug`             | `platform_tenants.slug`                          | |

---

## Canonical Source After Setup

**After company-setup completes**, the canonical source for business identity is:

- **`platform_company_profiles`** for: legal_name, address_*, company_phone, company_email, usdot_number, mc_number, cvor_number, operator_license, hst_number, w9_*.

**`platform_onboarding_payloads`** is consumed at setup (consumed_at set) and should not be used for downstream reads. It serves as:
- Prefill source during company-setup
- Repair source when profile is missing

---

## Persistence Guarantees

### Address
- **Guaranteed:** Signup requires address (street, city, region, postal, country). Company-setup requires address. Both flows validate and persist to `platform_company_profiles`.
- **Repair:** If profile row is missing but onboarding payload has full address, GET `/api/v1/admin/company-profile` creates the profile from payload (lazy repair).
- **Display fallback:** If repair fails (incomplete payload), address from payload is returned for display only; profile is not created.

### Company Name (Legal Name)
- **Guaranteed:** Signup requires `company_legal_name`; company-setup requires `legal_name` (prefilled from payload). Persisted to `platform_company_profiles.legal_name`.

### Company Phone
- **Collected at signup:** `payload_json.phone`.
- **Canonical:** `platform_company_profiles.company_phone` (new column, nullable).
- **Flow:** Company-setup accepts `company_phone`; if omitted, backfilled from onboarding payload. Prefill exposes `owner_phone`; frontend passes it to setup.
- **Fallback:** If `company_phone` is null on profile, API returns owner's `platform_users.phone` for display.

### Company Email
- **Collected at signup:** `payload_json.email`.
- **Canonical:** `platform_company_profiles.company_email` (new column, nullable).
- **Flow:** Company-setup accepts `company_email`; if omitted, backfilled from onboarding payload. Prefill exposes `owner_email`; frontend passes it to setup.
- **Fallback:** If `company_email` is null on profile, API returns owner's `platform_users.email` for display.

---

## Repair Strategy

1. **Lazy repair on GET company-profile:**  
   When `GET /api/v1/admin/company-profile` is called and `platform_company_profiles` has no row for the tenant, but `platform_onboarding_payloads` has a payload with full address:
   - Create `PlatformCompanyProfile` from payload (legal_name, address, company_phone, company_email).
   - Commit and return the new profile.
   - Payload is not consumed (consumed_at remains null) so the user can complete setup later if needed.

2. **Display fallback:**  
   When profile is missing and payload cannot be fully repaired (e.g. incomplete address), the API returns address/legal/phone/email from payload for display only. No profile row is created.

---

## Final Company Profile Response Shape

`GET /api/v1/admin/company-profile` returns:

```json
{
  "tenant_name": "string",
  "slug": "string",
  "timezone": "string",
  "base_currency": "string",
  "country_code": "string | null",
  "legal_name": "string | null",
  "street": "string | null",
  "city": "string | null",
  "region": "string | null",
  "postal": "string | null",
  "country": "string | null",
  "company_phone": "string | null",
  "company_email": "string | null",
  "usdot_number": "string | null",
  "mc_number": "string | null",
  "cvor_number": "string | null",
  "operator_license": "string | null",
  "hst_number": "string | null",
  "has_w9_file": "boolean",
  "setup_completed_at": "string | null"
}
```

---

## UI Sections (Admin Company Profile Page)

1. **Workspace** – Subdomain/Slug, Name, Timezone, Base Currency, Country
2. **Company Identity** – Company Name, Legal Name, Company Phone, Company Email
3. **Business Address** – Street, City, Region, Postal, Country (first-class section)
4. **Business Registration** – USDOT, MC, CVOR, Operator License, HST, W9 on File

---

## Future: Company Profile Edit

The page includes an "Edit (coming soon)" button. When edit support is implemented:
- PATCH or PUT endpoint for company profile
- Allow tenant admin to update address, company_phone, company_email, legal_name, and registration numbers
- Continue to use `platform_company_profiles` as the canonical source

---

## Migration

- **0023_company_profile_phone_email:** Adds `company_phone` and `company_email` columns to `platform_company_profiles` (nullable).
