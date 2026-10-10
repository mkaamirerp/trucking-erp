# Company Contact Document Safety

**Rule:** Business documents (invoices, pay stubs, company-facing PDFs) must use only canonical company profile data from `platform_company_profiles`. Owner/user contact from `platform_users` must never be used as the source for document-facing company identity.

---

## Canonical vs Fallback

| Source | Use For |
|--------|---------|
| **Canonical** (`platform_company_profiles`) | Invoices, pay stubs, business PDFs, official business contact display |
| **Fallback** (owner `platform_users` / onboarding payload) | Admin UI display only when profile is incomplete; initial prefill; support/debug |

---

## API Response: Company Profile

`GET /api/v1/admin/company-profile` returns:

### Canonical Fields (from `platform_company_profiles` only when present)

- `legal_name`, `street`, `city`, `region`, `postal`, `country`
- `company_phone`, `company_email`

### Completeness Flags

| Field | Meaning |
|-------|---------|
| `has_business_address` | Canonical profile has full address (street, city, region, postal, country) |
| `has_company_phone` | Canonical profile has `company_phone` |
| `has_company_email` | Canonical profile has `company_email` |
| `is_document_contact_complete` | All document-required fields present in canonical profile |

### Fallback Indicators

| Field | Meaning |
|-------|---------|
| `company_phone_is_fallback` | Displayed phone comes from owner/payload, not profile |
| `company_email_is_fallback` | Displayed email comes from owner/payload, not profile |
| `address_is_fallback` | Displayed address comes from payload, not profile |

When any `*_is_fallback` is true, the UI should show:  
*"Business contact information is incomplete. Please save company phone/email/address before using invoices or pay stubs."*

---

## Document-Safe Accessor

**Required source** for all document generation:

```python
from app.services.company_contact import get_canonical_company_contact_for_documents

result = await get_canonical_company_contact_for_documents(tenant_id, db)
if result.is_document_ready:
    contact = result.contact  # CanonicalCompanyContact
    # Use contact.legal_name, contact.address_*, contact.company_phone, contact.company_email
else:
    # Block or warn: result.missing_fields lists what's missing
    ...
```

**Do not** use for documents:

- `platform_users.phone` / `platform_users.email`
- `platform_onboarding_payloads.payload_json`
- Mixed fallback logic or ad hoc reads

---

## Document Readiness

A company is "document ready" when canonical `platform_company_profiles` has:

1. `legal_name`
2. Full business address: `address_street`, `address_city`, `address_region`, `address_postal`, `address_country`
3. `company_phone`
4. `company_email`

`is_document_contact_complete = true` only when all of the above are present.

---

## Enforcement

- Invoice generation → use `get_canonical_company_contact_for_documents`; block or warn if not ready.
- Pay stub generation → same.
- Business PDFs / templates → same.
- Admin Company Profile UI → may show fallback for convenience; must display completeness warning when incomplete or fallback.
