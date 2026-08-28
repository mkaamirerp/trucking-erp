# Driver decision records

This folder contains only **current / implemented driver ADRs**. It is separate from the newer top-level **Trip / Dispatch Decisions 6–14** under `docs/`.

## Trust order

When sources disagree, use this order:

1. current application code and migrations;
2. current driver foundation / schema locks;
3. active ADRs in this folder;
4. historical ADRs under `../archive/decisions/`.

Current driver architecture references:

- `../DRIVER_ONBOARDING_AND_ADMIN_CONFIGURATION_FOUNDATION.md`
- `../DRIVER_EXTENSION_PHASE3A_FOUNDATION_LOCK.md`
- `../DRIVER_EXTENSION_PHASE3A_SCHEMA_LOCK.md`
- `../DRIVER_OPERATING_MODEL_FOUNDATION.md`

## Active decision

- `0002-driver-phones.md` — **implemented** driver-scoped operational phone model. It is tied to the dispatch-facing `drivers` row and is not universal `Person` contact authority.

## Historical decision records

The following early ADRs are preserved under `../archive/decisions/` and must not be treated as implementation instructions:

- `0001-driver-ownership.md` — superseded by the newer driver-extension `employment_relationship_type` model.
- `0003-emergency-contacts.md` — unimplemented historical proposal; future ownership must be decided against the people-first model.
- `0004-driver-licenses.md` — unimplemented normalized-table proposal; the CA/US license requirement remains useful, but the old schema is not approved current design.
- `0005-storage-and-ocr.md` — superseded as OCR architecture by the shared Document Parser lock.

Do not create tables or product behavior from an archived ADR without a new current implementation decision.
