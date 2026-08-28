# Driver decision records

This folder contains the **small driver/onboarding ADR series 0001–0005**. It is separate from the newer top-level **Trip / Dispatch Decisions 6–14** under `docs/`.

## Trust rule

Use current code and the newer driver foundation/schema locks when an older ADR conflicts with them.

Current driver architecture references:

- `../DRIVER_ONBOARDING_AND_ADMIN_CONFIGURATION_FOUNDATION.md`
- `../DRIVER_EXTENSION_PHASE3A_FOUNDATION_LOCK.md`
- `../DRIVER_EXTENSION_PHASE3A_SCHEMA_LOCK.md`
- `../DRIVER_OPERATING_MODEL_FOUNDATION.md`

## Current contents

- `0002-driver-phones.md` — **implemented driver-scoped phone table**, with scope clarified against the people-first model.
- `0003-emergency-contacts.md` — **design-only / not implemented**.
- `0004-driver-licenses.md` — **design-only / not implemented**; normalized license/endorsement/restriction tables do not exist in current code.

## Archived from this series

- `0001-driver-ownership.md` — superseded by the newer driver-extension `employment_relationship_type` model (`company_driver` / `owner_operator`).
- `0005-storage-and-ocr.md` — superseded as OCR architecture by the shared Document Parser lock; OCR provider/execution is not currently locked or implemented.

Archived copies live under `../archive/decisions/` and are historical only.
