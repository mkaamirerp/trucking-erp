# Driver Foundation Boundary Report

*Read the current backend state before designing any new admin driver config. All file references are verified against the live codebase.*

---

## 1. What Currently Owns Driver Identity

**Primary model:** `app/models/driver.py` — table `drivers`.

The `Driver` row is the **operational dispatch roster record**. It is materialized at approval time, not at intake time. It has `first_name`, `last_name`, `email`, `phone`, `hire_date`, `termination_date`, `is_active`, and a full block of license columns: `license_number`, `license_class` (free-text), `license_region`, `license_issue_date`, `license_expiry_date`, `issuing_country`, `issuing_region`.

`Driver.person_id` is a nullable FK to `people.id` (composite on `tenant_id`) with `ON DELETE SET NULL`. A Driver can exist without a linked Person, but normally they are connected.

`Driver.payee_id` is a unique nullable FK to `payees.id` with `ON DELETE RESTRICT`. One payee per driver, cannot delete a payee that a driver still references.

`Person` in `app/models/person.py` holds the canonical human record: address fields (`street`, `city`, `region`, `postal_code`, `zip_code`, `country`), notes, and `Person.driver_profile` back-reference to Driver. Person also carries `first_name`, `last_name`, `email`, `phone` — duplicated on Driver.

**Duplication is intentional by design:** `Driver` is a denormalized operational projection. Name/contact fields are synced from Person during approval (`app/routers/driver_onboarding.py`, `_upsert_operational_driver_for_person`). Edits directly to Driver do not flow back to Person.

Router: `app/routers/drivers.py`. Service: `app/services/drivers.py`. Schemas: `app/schemas/driver.py` — `DriverCreate`, `DriverOut`, `DriverUpdate`, `DriverListOut`.

**Key boundary issue:** `Driver.license_class` is free text. A normalized license class (`A`, `B`, `AZ`, `DZ`, etc.) does not exist anywhere in the schema today.

---

## 2. What Currently Owns the Approval Flow

**Intake model:** `app/models/person_application.py` — table `person_applications`.

Key columns: `application_type` (default `"DRIVER"`), `requested_role_code` (default `"DRIVER"`), `status` (default `"DRAFT"`), `intake_payload` (JSONB, driver-submitted form), `person_id` (nullable — linked only after approval creates the Person), `submitted_at`, `reviewed_at`, `reviewed_by_user_id`, `approved_at`, `approved_by_user_id`, `rejection_reason`.

Status machine (defined in `app/schemas/driver_onboarding.py`): `DRAFT → SUBMITTED → APPROVED or REJECTED`.

**Legacy model:** `app/models/driver_onboarding_submission.py` — table `driver_onboarding_submissions`. File header explicitly marks it as compatibility-only. `PersonApplication` is the canonical path.

**Approval router:** `app/routers/driver_onboarding.py`. The promotion function is `_ensure_person_entities_for_application` (same file). On approval it executes in order:

1. Creates or updates `Person` with canonical data from the application.
2. Creates `PersonRole` with `requested_role_code`.
3. If role is `DRIVER`: creates `DriverProfile` (license_number, license_region, license_expiry from intake) and materializes a `Driver` row in the dispatch roster.
4. All steps are idempotent — safe to re-run on re-approval.

`DriverProfile` is a Person-side capability record (in `app/models/person_application.py` or nearby — holds license facts as processed from intake). It is distinct from the Driver model.

**Nothing in the approval flow sets an operating type, employment model, or equipment binding mode.** Those fields do not exist. Admin approval today only decides role code (`DRIVER`) and creates the roster entry. No second-pass config step exists.

---

## 3. What Currently Owns Payee and Pay Logic

**Payee model:** `app/models/payee.py` — table `payees`.

Key columns: `payee_type` (`DRIVER` or `CARRIER`), `worker_type` (`EMPLOYEE_DRIVER`, `CONTRACTOR_COMPANY_DRIVER`, `OWNER_OPERATOR_LEASED_ON`, `THIRD_PARTY_CARRIER`), `display_name`, `is_active`. Carrier-specific columns: `carrier_mc_number`, `carrier_dot_number`, `tax_id_last4`.

`Driver.payee_id` → `payees.id` is the binding. The Driver owns the FK. One driver maps to at most one payee.

**CompensationProfile model:** `app/models/payee.py` — table `compensation_profiles`. FK: `payee_id`. This is the canonical pay structure source: `worker_type_snapshot`, `gross_calc_type` (`CPM`, `PERCENT_REVENUE`, `FLAT_PER_LOAD`, `HOURLY`, `SALARY`, `HYBRID`), rate columns (`percent_rate`, `cpm_loaded`, `cpm_empty`, `hourly_rate`, `salary_amount`, `flat_amount`), `dispatch_fee_enabled`, `dispatch_fee_rate`, `settlement_frequency`.

**PayProfile model (legacy):** `app/models/payroll.py` — table `pay_profiles`. FK: `driver_id`. Holds `pay_type` (per_mile/hourly/percentage/salary), `rate_amount`, `rate_unit`. This predates CompensationProfile and is the legacy driver-linked config path. CompensationProfile via Payee is the intended modern path.

**PayEntry model:** `app/models/payroll.py` — table `pay_entries`. FK: `driver_id`, `pay_period_id`. Holds individual work record lines.

**PayRun / PayRunItem:** `app/models/payroll.py` — tables `pay_runs`, `pay_run_items`. `PayRunItem.payee_id` → `payees.id`. Metadata tracing via `metadata_json` JSONB (includes `load_id`, `trip_number` where resolvable).

**`worker_type` on Payee is a pay classification**, not a dispatch operating model. It affects settlement calculations. It does not drive equipment assignment behavior or dispatch workflow. These are different concepts that currently share similar vocabulary (`owner_operator`) but live in separate models with separate purposes.

---

## 4. What Currently Owns Dispatch Driver and Equipment Behavior

**Load assignment:** `app/models/load.py` — `Load.driver_id` (FK to `drivers.id`), `Load.truck_id` (FK to `trucks.id`), `Load.trailer_id` (FK to `trailers.id`). Assignment is direct column. No intermediate assignment table exists. Assignment is written via `PATCH /loads/{id}` (`app/routers/loads.py`).

**Dispatch board:** `app/routers/dispatch.py` — exposes `GET /dispatch/board` which returns loads grouped by status for the board UI. No driver-specific routing logic here.

**DispatchTrip model:** `app/models/dispatch_trip.py` — table `dispatch_trips`. Key columns: `trip_number`, `job_type` (`freight_load` or `trailer_move`), `status` (default `active`), `load_id` (nullable), `trailer_move_id` (nullable). Exactly one of `load_id` or `trailer_move_id` must be set (check constraint). Trip is the operational event wrapping a load; it carries the `trip_number` visible on settlement.

**Assignment hints endpoint:** `app/routers/drivers.py:108–167` — `GET /drivers/{driver_id}/assignment-hints`. Heuristics in order:

1. Find the driver's most recent in-progress load (statuses: `assigned`, `dispatched`, `arrived_pickup`, `in_transit`, `arrived_delivery`). If found, return its `truck_id` and `trailer_id`.
2. If no truck resolved and driver has a `person_id`: query `trucks` where `owner_person_id == driver.person_id` and `status == "active"`. Return first match.
3. If no trailer resolved and driver has a `person_id`: query `trailers` where `owner_person_id == driver.person_id` and `status == "active"`. Return first match.

These are pure suggestions. There is no enforcement, no equipment binding mode, and no operating-type awareness in the hint logic today.

**No operating type or equipment mode field exists on Driver.** The concept is completely absent from the current schema. Assignment behavior is purely driven by load history and Person-linked fleet ownership.

---

## 5. What Currently Owns Truck and Trailer Ownership Assumptions

**Truck model:** `app/models/truck.py` — table `trucks`. Relevant columns: `ownership_type` (String 30, default `"company"`), `owner_person_id` (BigInteger, nullable, composite FK to `people.id` with `ON DELETE SET NULL`). No `assigned_driver_id`. No `binding_mode`. Ownership is to Person, not to Driver directly.

**Trailer model:** `app/models/trailer.py` — table `trailers`. Same pattern: `ownership_type` (default `"company"`), `owner_person_id` (nullable, FK to `people.id`, `ON DELETE SET NULL`).

**Suggested-trailer endpoint:** `app/routers/trucks.py:60–82` — `GET /trucks/{truck_id}/suggested-trailer`. Logic: find the most recent load that used this truck and had a non-null `trailer_id`. Return that trailer. No ownership binding, no mode logic — purely historical pairing.

**No dedicated equipment assignment or driver-equipment binding table exists.** Ownership is captured as a column on the equipment record pointing to Person. Dispatch assignment is captured as a column on Load. The gap between "this owner-operator's truck" and "the truck on this specific load" is bridged only by the assignment-hints heuristic at dispatch time.

---

## 6. Where New Admin Driver Config Can Safely Live

**Fields that do not exist anywhere in the current schema:**

| Field | Status |
|---|---|
| `operating_type` (long_haul_company, owner_operator, city_local, shunt_yard) | Missing |
| `employment_model` (company_driver, owner_operator, contractor) | Missing — Payee.worker_type is pay classification only |
| `equipment_binding_mode` (dedicated, pooled, owner_unit, yard_pool) | Missing |
| `license_class_normalized` (A, B, AZ, DZ, etc.) | Missing — Driver.license_class is free text |
| `capability_flags` (hazmat, doubles, tanker, etc.) | Missing |

**What must not be stepped on:**

- `Driver.license_class` is free text from intake — do not repurpose. A normalized field is additive.
- `Payee.worker_type` is pay classification — do not try to make it drive dispatch behavior. They are parallel concepts.
- `Driver.person_id` is nullable with `SET NULL`. Any new profile table that FKs to Driver must handle the driver existing without Person (normal operational state).
- `Driver.payee_id` is `RESTRICT` on delete — the payee cannot be removed while a driver references it. A dispatch profile should have `ON DELETE CASCADE` to Driver, not to Payee.

**Recommended location: a new `driver_dispatch_profiles` table**, one-to-one with Driver.

**Why not new columns on Driver:** The Driver table is an operational roster projection — minimal, synced from Person on approval, used by dispatch queries. Adding admin configuration to it blurs the line between what is materialized operational data and what is tenant-admin policy. The existing pattern in this codebase already separates these: Person (canonical human), DriverProfile (intake capability, Person-side), Driver (operational roster, minimal projection). A `DriverDispatchProfile` continues that pattern on the admin-config side.

**FK relationships the new table must respect:**

- `driver_dispatch_profiles.driver_id` → `drivers.id` (`ON DELETE CASCADE` — profile dies with driver)
- Composite FK on `(tenant_id, driver_id)` to prevent cross-tenant pollution
- No FK to Payee needed — employment_model on DriverDispatchProfile and worker_type on Payee are parallel fields for different purposes; keep them independent, reconcile in the approval flow

**Onboarding/approval flow integration point:** The admin approval step in `app/routers/driver_onboarding.py` is the natural place to set or initialize the dispatch profile. Currently that function creates Person, PersonRole, DriverProfile, and Driver. A fifth step — create or seed `DriverDispatchProfile` from admin-submitted config — belongs in the same sequence, after the Driver row exists.

---

## Boundary Summary

| Domain | Owner | Key Model / Table | Primary Entry Point |
|---|---|---|---|
| Driver identity (operational) | `drivers` table | `app/models/driver.py` | `app/routers/drivers.py` |
| Applicant intake and state | `person_applications` table | `app/models/person_application.py` | `app/routers/driver_onboarding.py` |
| Approval and promotion | `driver_onboarding` router | `_ensure_person_entities_for_application` in `app/routers/driver_onboarding.py` | `POST /api/v1/driver-onboarding/{app_id}/approve` |
| Payee and pay structure | `payees` + `compensation_profiles` | `app/models/payee.py` | Payroll routers |
| Dispatch assignment | `Load.driver_id` column | `app/models/load.py` | `PATCH /loads/{id}` |
| Equipment ownership | `Truck.owner_person_id`, `Trailer.owner_person_id` | `app/models/truck.py`, `app/models/trailer.py` | Trucks / trailers routers |
| Assignment hints | History + ownership query | `app/routers/drivers.py:108–167` | `GET /drivers/{id}/assignment-hints` |
| **Admin dispatch config (missing)** | **Proposed: `driver_dispatch_profiles`** | **Does not exist** | **Belongs after Driver materialization in approval flow** |

---

## Key Overlaps and Blurry Boundaries

**Driver name fields are duplicated.** `Driver.first_name/last_name/email/phone` mirror `Person`. They are synced on approval and again on re-approval. Direct edits to Driver do not propagate to Person. Edits to Person do not auto-propagate to Driver. This is deliberate but means the two can drift.

**License info is split across two models.** `Driver` holds free-text `license_class`, `license_number`, `license_region`, `license_expiry_date`. `DriverProfile` (Person-side) also holds license fields from intake. Sync happens in the approval function. A normalized `license_class_normalized` column should live on `DriverDispatchProfile`, not on Driver, to avoid adding to this split.

**`worker_type` appears in two places with different meanings.** `Payee.worker_type` is a pay classification (`EMPLOYEE_DRIVER`, `OWNER_OPERATOR_LEASED_ON`, etc.). The proposed `employment_model` on `DriverDispatchProfile` would be an operational/dispatch classification. They use similar vocabulary but serve different systems. They must remain separate columns. The approval flow is where the admin sets both, but they should not be the same field.

**Equipment ownership points to Person, not Driver.** `Truck.owner_person_id` and `Trailer.owner_person_id` reference `people.id`. The assignment-hints endpoint resolves from `driver.person_id` to find owner-linked equipment. This chain works but is one indirection. A future `equipment_binding_mode` on `DriverDispatchProfile` would add policy on top of this ownership query without changing the ownership model itself.
