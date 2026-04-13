# People-First API Design (mandatory)

## Core rule

**Person is the only "who."**

- **DB:** Rows keyed by `(tenant_id, person_id, ...)`. Composite FKs: `(tenant_id, person_id) -> people(tenant_id, id)`.
- **API:** Anything owned by a person is nested under `/people/{person_id}/...`.
- **Driver** is a role or profile attached to a person, not a separate identity. Do not create top-level "driver-*" resources.

## When to nest vs when NOT to nest

**Nest under `/people/{person_id}` when:** It's a person-owned sub-resource.

- phones, emails, addresses
- documents / files
- emergency contacts
- licenses / certifications
- role assignments
- person notes, tags, preferences

**Do NOT nest when:** It's a global resource queried across many people.

- "list all documents expiring in 30 days"
- "all people with role DRIVER"
- "search people"

Use **collection endpoints** with query params instead:

- `GET /people?role=DRIVER`
- `GET /documents?type=CERTIFICATION&expires_before=...`

You usually want **both**: nested for "this person's X" and global for compliance/dashboards.

## Recommended API shape

### Identity

- `GET /people` — `POST /people`
- `GET /people/{person_id}` — `PATCH /people/{person_id}` — `DELETE /people/{person_id}` (soft delete)

### Person sub-resources (owned-by-person)

- `GET|POST /people/{person_id}/phones` — `PATCH|DELETE /people/{person_id}/phones/{phone_id}`
- `GET|POST /people/{person_id}/emails` (or single email on Person)
- `GET|POST /people/{person_id}/addresses`
- `GET|POST /people/{person_id}/documents` — `GET|PATCH|DELETE /people/{person_id}/documents/{document_id}`
- `GET|POST /people/{person_id}/roles`
- Filter documents: `?type=DRIVER_LICENSE`, `?category=COMPLIANCE`, `?expires_before=...`

### Role-specific profiles (1-to-1 with person)

- `GET|PUT|PATCH /people/{person_id}/driver-profile`
- `GET|PUT|PATCH /people/{person_id}/mechanic-profile` (if needed)
- These are profiles extending the person, not separate identity tables.

### Global collection endpoints

- `GET /people?role=DRIVER` (and other filters)
- `GET /documents?person_id=...&type=...&expires_before=...`

### Driver as alias only

- **Allowed:** `GET /drivers` as alias for `GET /people?role=DRIVER` (returns people who are drivers).
- **Do not add new** top-level identity routes such as `POST /drivers` or parallel `/driver-phones`-style shims. **`/driver-documents` remains live** in the main app (grandfathered); see **Live repository note** below — do not “clean this up” casually.

## Naming

- Prefer neutral names for person-owned resources: `DocumentOut`, `PersonDocumentOut`, with `document_type` (e.g. DRIVER_LICENSE, CERTIFICATION, W9). Do not use "DriverDocument" as the primary API name when documents apply to any person.
- Keep "driver" only where it's role-specific (e.g. `driver-profile`).

## Implementation rules

1. **person_id** is the universal human FK. Phones, documents, roles, profiles key off `person_id`.
2. Enforce **tenant**: always scope by `tenant_id`; use composite FKs where applicable.
3. For role-specific endpoints (e.g. driver-profile, driver documents), **verify person has that role** when required; do not assume `person_id` implies driver.
4. **Target API shape:** Prefer `/people/{person_id}/documents` and `/people/{person_id}/phones` instead of growing new top-level driver-keyed identity routes.
5. **Naming:** Use PersonDocument (not DriverDocument), PersonDocumentFile, person_documents schemas, save_document_upload_local. Avoid `type` as a parameter name (use doc_type with alias "document_type").
6. **REST:** Use PATCH for deactivate/update (e.g. PATCH `/people/{person_id}/documents/{id}` with `{ "is_active": false }`), not POST .../deactivate.
7. **Helpers:** Prefer _get_person(db, person_id, tenant_id) returning Person to avoid double queries.

## Live repository note (policy vs code)

The main app still exposes **supported** tenant routes under **`/api/v1/driver-documents`** (including body and path variants keyed by **`driver_id`**, not `person_id`). That surface is **grandfathered** until an intentional migration moves document CRUD under `/people/...` and retires the old paths.

**Rule for contributors:** do **not** treat the “ban” language above as permission to delete or bypass `app/routers/driver_documents.py` without an explicit migration + API contract change. New *features* should default to people-first nesting; extending the legacy router requires a deliberate security/tenant review (same bar as any other tenant mutation).
