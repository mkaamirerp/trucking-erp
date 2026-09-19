# Documentation test fixtures

This folder contains **committed regression/test evidence**, not product architecture documents.

## `fuel/`

Evidence-backed Fuel/Card fixtures for the **generic Fuel parser + provider profiles** architecture.

Current active files:

- `BVD_invoice_972201.pdf` — real BVD statement PDF (invoice 972201); first provider-profile proof
- `BVD_invoice_972201.extracted_text.json` — page text extracted for layout-anchor tests (not the digital-PDF AI input)
- `nationwide_fuel.pdf` — real Nationwide fuel invoice PDF; second provider-profile proof
- `nationwide_fuel.extracted_text.json` — page text for Nationwide layout-anchor tests

Provider profiles (data, not engines) — **one master JSON**, one current section per provider:

- `app/contracts/fuel_provider_profiles.json` — top-level keys exactly `BVD` and `NATIONWIDE`
  (identity: `provider_code` + `profile_version` stamp; no `profile_code` / `statement_v1`)

## `load_lab/`

The `load_lab` directory name is historical provenance. The files that remain there are still used by current parser tests and **do not mean Load Lab owns the production parser**.

Current active files:

- `load_lab_fixture_1pickup_3deliveries.pdf`
- `load_lab_fixture_1pickup_3deliveries.lab_parse_response.json`
- `load_lab_fixture_3pickups_1delivery.pdf`
- `load_lab_fixture_3pickups_1delivery.lab_parse_response.json`

The PDFs provide stable extractable-text examples. The `.lab_parse_response.json` files are compatibility/golden inputs used to prove that older Lab-shaped payloads can still map safely into `LoadDocumentParseResponse` without leaking Lab-only diagnostics.

They are **not** the semantic expected-output contract for the current Rate Confirmation v2 profile. Current parser architecture is defined by `../TruckERP_Shared_Document_Parsing_Architecture.md` and `../TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`.

Two unused illustrative `synthetic_expected_truckerjson` files were moved to `../archive/fixtures/load_lab/` because no current test or code consumes them.

## Fixture rule

Do not archive or rename a fixture that a current test references unless the test is deliberately updated in the same change. Do not treat a historical fixture filename or payload shape as architecture authority.
