# Casbin / RBAC Read-Only Inspection Report

- **Repository HEAD:** `d732ad4c654be94e4c479c368572678cb57fb89d`
- **Inspection date (UTC):** 2026-10-15T03:58:51Z
- **Scope:** Read-only static analysis + FastAPI route introspection in running `truckerp-api` container (env from `/run/secrets/truckerp.env`). No code, config, DB, or test mutations.

---

## A. Executive summary

TruckERP authorization today is **layered but not unified**: tenant resolution and **active membership** are enforced in `TenantContextMiddleware` for most `/api/v1/*` routes; authenticated identity is centralized in `get_current_user` / `get_current_platform_user` (`app/deps/auth.py`). **Subscription entitlements** (`app/deps/entitlements.py`) gate some modules (`admin_sensitive`, `payroll`, `email_inbox`, etc.) but are **not** a role model.

**Temporary membership roles** live in `app/deps/admin.py` and the frontend mirror `apps/web/src/auth/roles.ts`: four **tenant admin** roles (`OWNER`, `ADMIN`, `TENANT_ADMIN`, `TENANT_OWNER`) vs everyone else (mapped to UI **READ_ONLY**). **FULL_ACCESS** in invites maps to platform role `TENANT_ADMIN` (`access_level_to_role`), which is **broader than “operational write”** and overlaps true tenant administration.

**Fuel** is the only domain with explicit **named capabilities** (`app/deps/fuel_rbac.py`), but Segment 0A maps **all** fuel capabilities to `is_tenant_admin` — operational `FULL_ACCESS` users cannot use Fuel APIs today.

**Critical gap:** Most operational routers (Loads, Trips, Brokers, Tolls, Fleet assets, etc.) require only `get_current_user` + tenant DB scoping. A **READ_ONLY** (`TENANT_MEMBER`) user can invoke **mutations** (create/update/delete loads, trip assignment, toll imports, etc.) unless blocked elsewhere — **no consistent deny-by-default RBAC**.

**Load integrity:** `DELETE /api/v1/loads/{load_id}` calls `loads_service.delete_load` which performs a **hard SQL DELETE** (`app/services/loads.py:563-574`), while `docs/load_trip/MASTER.md` tracks **I5** (unsafe hard delete) as **NOT IMPLEMENTED** / needs soft-cancel policy — Casbin must not override this domain rule.

**Casbin recommendation:** Introduce a **version-controlled** model+policy bundle and a single `authorize(capability, subject, tenant)` service invoked **after** auth, tenant isolation, and entitlements; fail-closed on policy load errors and unknown capabilities. Keep V1 **static policy** (no new DB tables).

**Route inventory:** **371** HTTP operations on the running app graph (see §B). **300** attach `get_current_user` (directly or via dependencies). **119** authenticated API mutations lack `require_tenant_admin` / Fuel capability deps (most by design today — **over-permissive for READ_ONLY**).

---

## B. Router and endpoint inventory (complete)

Columns: **Auth** = `get_current_user` in dependency tree; **Tenant** = `require_tenant` in tree; **Ent** = entitlement dependency; **Inline guards** = AST-detected symbols in handler body (may miss router-level deps).

| Method | Path | Handler | Auth | Tenant dep | Entitlement | Inline / special guards | Op |
|--------|------|---------|------|------------|-------------|----------------------|-----|
| GET | `/openapi.json` | `fastapi.applications:openapi` @L1104 | no | no | — | — | read |
| GET | `/docs` | `fastapi.applications:swagger_ui_html` @L1119 | no | no | — | — | read |
| GET | `/docs/oauth2-redirect` | `fastapi.applications:swagger_ui_redirect` @L1137 | no | no | — | — | read |
| GET | `/redoc` | `fastapi.applications:redoc_html` @L1147 | no | no | — | — | read |
| GET | `/api/v1/health` | `health:health` @L6 | no | no | — | — | read |
| GET | `/api/v1/public/tenant/{slug}` | `public_signup:get_tenant_status` @L112 | no | no | — | HTTPException | read |
| GET | `/api/v1/public/check-slug-availability` | `public_signup:check_slug_availability` @L170 | no | no | — | HTTPException | read |
| GET | `/api/v1/public/check-signup-email` | `public_signup:check_signup_email_availability` @L203 | no | no | — | HTTPException | read |
| GET | `/api/v1/public/check-signup-phone` | `public_signup:check_signup_phone_availability` @L216 | no | no | — | HTTPException | read |
| POST | `/api/v1/public/signup` | `public_signup:public_signup` @L233 | no | no | — | HTTPException, token | mutation |
| POST | `/api/v1/public/verify-otp` | `public_signup:verify_otp` @L443 | no | no | — | HTTPException, token | mutation |
| POST | `/api/v1/public/resend-otp` | `public_signup:resend_otp` @L711 | no | no | — | token | mutation |
| POST | `/api/v1/public/cancel-signup` | `public_signup:cancel_signup` @L818 | no | no | — | HTTPException, token | mutation |
| POST | `/api/v1/public/company-setup/w9-upload` | `public_signup:upload_w9_document` @L870 | no | no | — | — | mutation |
| GET | `/api/v1/public/company-setup/document` | `public_signup:download_company_setup_document` @L904 | no | no | — | HTTPException | read |
| GET | `/api/v1/public/company-setup/prefill` | `public_signup:company_setup_prefill` @L951 | no | no | — | — | read |
| POST | `/api/v1/public/company-setup` | `public_signup:company_setup` @L988 | no | no | — | HTTPException | mutation |
| POST | `/api/v1/public/workspace-intake` | `workspace_intake:create_workspace_intake` @L74 | no | no | — | token | mutation |
| POST | `/api/v1/public/workspace-intake/consume` | `workspace_intake:consume_workspace_intake` @L120 | no | no | — | HTTPException, token | mutation |
| GET | `/api/v1/public/workspace-intake/session` | `workspace_intake:workspace_intake_session` @L161 | no | no | — | HTTPException | read |
| GET | `/api/v1/platform/tenants` | `platform_tenants:list_tenants` @L58 | no | no | — | HTTPException, require_platform_admin | read |
| POST | `/api/v1/platform/tenants` | `platform_tenants:create_tenant` @L70 | no | no | — | HTTPException, require_platform_admin | mutation |
| POST | `/api/v1/platform/tenants/{tenant_id}/provision` | `platform_tenants:provision_tenant` @L94 | no | no | — | HTTPException, require_platform_admin | mutation |
| GET | `/api/v1/platform/tenants/{tenant_id}` | `platform_tenants:get_tenant` @L192 | no | no | — | HTTPException, require_platform_admin | read |
| POST | `/api/v1/platform/tenants/{tenant_id}/retry-provision` | `platform_tenants:retry_provision` @L212 | no | no | — | HTTPException, require_platform_admin | mutation |
| GET | `/api/v1/platform/extraction-sanitized-patterns` | `platform_extraction_learning:list_sanitized_patterns` @L22 | no | no | — | require_platform_admin | read |
| PUT | `/api/v1/platform/extraction-sanitized-patterns` | `platform_extraction_learning:upsert_sanitized_pattern` @L35 | no | no | — | HTTPException, require_platform_admin | mutation |
| GET | `/api/v1/platform/global-booking-brokers` | `platform_global_booking_brokers:list_global_booking_brokers` @L76 | no | no | — | require_platform_admin | read |
| GET | `/api/v1/platform/global-booking-broker-duplicate-candidates` | `platform_global_booking_brokers:list_global_booking_broker_duplicate_candidates` @L105 | no | no | — | require_platform_admin | read |
| POST | `/api/v1/platform/global-booking-brokers/merge/preview` | `platform_global_booking_brokers:preview_global_booking_broker_merge` @L159 | no | no | — | HTTPException, require_platform_admin | mutation |
| POST | `/api/v1/platform/global-booking-brokers/merge/execute` | `platform_global_booking_brokers:execute_global_booking_broker_merge_endpoint` @L196 | no | no | — | require_platform_admin | mutation |
| POST | `/api/v1/platform/global-booking-broker-duplicate-candidates/refresh` | `platform_global_booking_brokers:refresh_global_booking_broker_duplicate_candidates_endpoint` @L224 | no | no | — | require_platform_admin | mutation |
| PATCH | `/api/v1/platform/global-booking-broker-duplicate-candidates/{candidate_id}` | `platform_global_booking_brokers:patch_global_booking_broker_duplicate_candidate` @L242 | no | no | — | HTTPException, require_platform_admin | mutation |
| POST | `/api/v1/platform/global-booking-brokers` | `platform_global_booking_brokers:create_global_booking_broker` @L308 | no | no | — | HTTPException, require_platform_admin | mutation |
| GET | `/api/v1/platform/global-booking-brokers/{broker_id}/audit-events` | `platform_global_booking_brokers:list_global_booking_broker_audit_events` @L401 | no | no | — | HTTPException, require_platform_admin | read |
| PATCH | `/api/v1/platform/global-booking-brokers/{broker_id}/profile` | `platform_global_booking_brokers:patch_global_booking_broker_profile` @L432 | no | no | — | HTTPException, require_platform_admin | mutation |
| PATCH | `/api/v1/platform/global-booking-brokers/{broker_id}` | `platform_global_booking_brokers:patch_global_booking_broker` @L469 | no | no | — | HTTPException, require_platform_admin | mutation |
| GET | `/api/v1/platform/login-failures` | `platform_diagnostics:list_login_failures` @L22 | no | no | — | HTTPException, require_platform_admin | read |
| POST | `/api/v1/platform/testing/login-lock-status` | `platform_testing:testing_login_lock_status` @L32 | no | no | — | HTTPException, require_platform_admin | mutation |
| POST | `/api/v1/platform/testing/unlock-login` | `platform_testing:testing_unlock_login` @L59 | no | no | — | HTTPException, require_platform_admin | mutation |
| POST | `/api/v1/drivers` | `drivers:create_driver` @L33 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/drivers` | `drivers:list_drivers` @L52 | yes | yes | — | HTTPException, get_current_user | read |
| GET | `/api/v1/drivers/{driver_id}/assignment-hints` | `drivers:get_driver_assignment_hints` @L114 | yes | yes | — | HTTPException, get_current_user | read |
| GET | `/api/v1/drivers/{driver_id}` | `drivers:get_driver` @L176 | yes | yes | — | HTTPException, get_current_user | read |
| PATCH | `/api/v1/drivers/{driver_id}` | `drivers:update_driver` @L189 | yes | yes | — | HTTPException, get_current_user | mutation |
| DELETE | `/api/v1/drivers/{driver_id}` | `drivers:delete_driver` @L245 | no | no | — | HTTPException | mutation |
| GET | `/api/v1/drivers/{driver_id}/summary` | `drivers:driver_summary` @L253 | yes | yes | — | HTTPException, get_current_user | read |
| GET | `/api/v1/driver-person-extensions/{person_id}` | `driver_person_extension:get_driver_person_extension` @L26 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, is_tenant_admin | read |
| PUT | `/api/v1/driver-person-extensions/{person_id}` | `driver_person_extension:upsert_driver_person_extension` @L53 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| GET | `/api/v1/people` | `people_workspace:list_people` @L61 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | get_current_user | read |
| PATCH | `/api/v1/people/{person_id}/driver-profile` | `people_workspace:patch_person_driver_profile` @L80 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | mutation |
| GET | `/api/v1/people/{person_id}/compensation-setup` | `people_workspace:get_person_compensation_setup` @L168 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | read |
| PATCH | `/api/v1/people/{person_id}/compensation-setup` | `people_workspace:patch_person_compensation_setup` @L183 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | mutation |
| GET | `/api/v1/people/{person_id}/driver-role-configuration` | `people_workspace:get_person_driver_role_configuration` @L251 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | read |
| PATCH | `/api/v1/people/{person_id}/driver-role-configuration` | `people_workspace:patch_person_driver_role_configuration` @L272 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | mutation |
| GET | `/api/v1/people/{person_id}/audit-log` | `people_workspace:list_person_maintenance_audit_log` @L348 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | read |
| GET | `/api/v1/people/{person_id}` | `people_workspace:get_person_detail` @L408 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | read |
| PATCH | `/api/v1/people/{person_id}` | `people_workspace:patch_person_core` @L424 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | mutation |
| GET | `/api/v1/fleet` | `fleet:get_fleet` @L23 | yes | yes | — | — | read |
| GET | `/api/v1/driver-phones` | `driver_phones:list_driver_phones` @L21 | yes | yes | — | — | read |
| POST | `/api/v1/driver-phones` | `driver_phones:create_driver_phone` @L41 | yes | yes | — | — | mutation |
| DELETE | `/api/v1/driver-phones/{phone_id}` | `driver_phones:deactivate_driver_phone` @L54 | yes | yes | — | HTTPException | mutation |
| POST | `/api/v1/driver-phones/{phone_id}/reactivate` | `driver_phones:reactivate_driver_phone` @L80 | yes | yes | — | HTTPException | mutation |
| POST | `/api/v1/driver-documents` | `driver_documents:create_driver_document` @L51 | yes | yes | app.deps.entitlements.require_driver_documents_entitlement | — | mutation |
| POST | `/api/v1/driver-documents/{driver_id}` | `driver_documents:create_driver_document_for_driver` @L77 | yes | yes | app.deps.entitlements.require_driver_documents_entitlement | — | mutation |
| GET | `/api/v1/driver-documents` | `driver_documents:list_driver_documents` @L114 | yes | yes | app.deps.entitlements.require_driver_documents_entitlement | HTTPException | read |
| GET | `/api/v1/driver-documents/{driver_id}` | `driver_documents:list_driver_documents_by_path` @L126 | yes | yes | app.deps.entitlements.require_driver_documents_entitlement | — | read |
| POST | `/api/v1/driver-documents/{document_id}/deactivate` | `driver_documents:deactivate_driver_document` @L136 | yes | yes | app.deps.entitlements.require_driver_documents_entitlement | HTTPException | mutation |
| POST | `/api/v1/driver-documents/{document_id}/files` | `driver_documents:upload_driver_document_file` @L162 | yes | yes | app.deps.entitlements.require_driver_documents_entitlement | HTTPException | mutation |
| GET | `/api/v1/driver-documents/{document_id}/files` | `driver_documents:list_driver_document_files` @L198 | yes | yes | app.deps.entitlements.require_driver_documents_entitlement | HTTPException | read |
| POST | `/api/v1/driver-documents/{document_id}/files/{file_id}/deactivate` | `driver_documents:deactivate_driver_document_file` @L221 | yes | yes | app.deps.entitlements.require_driver_documents_entitlement | HTTPException | mutation |
| POST | `/api/v1/admin/onboarding/invite-link` | `admin_onboarding:create_invite_link` @L70 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, applicant, get_current_user, is_tenant_admin, token | mutation |
| GET | `/api/v1/driver-onboarding/applicant/application` | `driver_onboarding:get_applicant_application` @L1047 | no | yes | app.deps.entitlements.require_tenant_subscription_active | applicant, token | read |
| GET | `/api/v1/driver-onboarding/applicant/application/events` | `driver_onboarding:stream_applicant_application_events` @L1066 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | read |
| PUT | `/api/v1/driver-onboarding/applicant/application` | `driver_onboarding:update_applicant_application` @L1109 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | mutation |
| POST | `/api/v1/driver-onboarding/applicant/application/intake` | `driver_onboarding:save_applicant_intake` @L1158 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | mutation |
| POST | `/api/v1/driver-onboarding/applicant/application/reset` | `driver_onboarding:reset_applicant_application` @L1219 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | mutation |
| POST | `/api/v1/driver-onboarding/applicant/application/dl-upload` | `driver_onboarding:upload_applicant_dl` @L1264 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | mutation |
| POST | `/api/v1/driver-onboarding/applicant/application/dl-confirm` | `driver_onboarding:confirm_applicant_dl` @L1297 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | mutation |
| GET | `/api/v1/driver-onboarding/applicant/dl-capture/{token}` | `driver_onboarding:get_dl_capture_session` @L1331 | no | yes | app.deps.entitlements.require_tenant_subscription_active | token | read |
| POST | `/api/v1/driver-onboarding/applicant/dl-capture/{token}/upload` | `driver_onboarding:upload_dl_capture_side` @L1359 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | mutation |
| POST | `/api/v1/driver-onboarding/applicant/dl-capture/{token}/confirm` | `driver_onboarding:confirm_dl_capture_side` @L1435 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | mutation |
| GET | `/api/v1/driver-onboarding/applicant/dl-capture/{token}/file` | `driver_onboarding:get_dl_capture_file` @L1500 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | read |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/dl-capture-link` | `driver_onboarding:issue_dl_capture_link` @L1571 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin, token | mutation |
| POST | `/api/v1/driver-onboarding/applicant/application/dl-capture-link` | `driver_onboarding:issue_applicant_dl_capture_link` @L1591 | no | yes | app.deps.entitlements.require_tenant_subscription_active | applicant, token | mutation |
| POST | `/api/v1/driver-onboarding/applicant/application/dl-capture-link/email` | `driver_onboarding:email_applicant_dl_capture_link` @L1633 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | mutation |
| GET | `/api/v1/driver-onboarding/applicant/application/file` | `driver_onboarding:get_applicant_application_file` @L1673 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | read |
| POST | `/api/v1/driver-onboarding/applicant/application/document-upload` | `driver_onboarding:upload_applicant_document` @L1734 | no | yes | app.deps.entitlements.require_tenant_subscription_active | HTTPException, applicant, token | mutation |
| GET | `/api/v1/driver-onboarding/applications` | `driver_onboarding:list_person_applications` @L1799 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | read |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/mark-admin-review-engaged` | `driver_onboarding:mark_admin_review_engaged` @L1848 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | mutation |
| GET | `/api/v1/driver-onboarding/applications/{application_id}` | `driver_onboarding:get_person_application_admin` @L1873 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | read |
| PATCH | `/api/v1/driver-onboarding/applications/{application_id}/review-fields` | `driver_onboarding:patch_person_application_review_fields` @L2009 | yes | yes | — | HTTPException, applicant, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/request-documents` | `driver_onboarding:request_person_application_documents` @L2064 | yes | yes | — | HTTPException, applicant, get_current_user, is_tenant_admin, token | mutation |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/documents/accept` | `driver_onboarding:set_person_application_document_acceptance` @L2150 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/document-upload` | `driver_onboarding:admin_upload_person_application_document` @L2195 | yes | yes | — | HTTPException, applicant, get_current_user, is_tenant_admin | mutation |
| GET | `/api/v1/driver-onboarding/applications/{application_id}/file` | `driver_onboarding:get_admin_application_file` @L2236 | yes | yes | — | HTTPException, applicant, get_current_user, is_tenant_admin | read |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/materialize-person-for-combined-setup` | `driver_onboarding:materialize_person_for_combined_setup` @L2269 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | mutation |
| GET | `/api/v1/driver-onboarding/applications/{application_id}/combined-driver-approve-readiness` | `driver_onboarding:get_combined_driver_approve_readiness` @L2313 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | read |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/approve` | `driver_onboarding:approve_person_application` @L2351 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/reject` | `driver_onboarding:reject_person_application` @L2402 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | mutation |
| GET | `/api/v1/driver-onboarding/applications/{application_id}/driver-compensation-setup` | `driver_onboarding:get_application_driver_compensation_setup` @L2434 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | read |
| PUT | `/api/v1/driver-onboarding/applications/{application_id}/driver-compensation-setup` | `driver_onboarding:put_application_driver_compensation_setup` @L2469 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/complete-onboarding` | `driver_onboarding:complete_person_application_onboarding` @L2520 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/onboarding/driver-license/ocr` | `onboarding:driver_license_ocr` @L31 | yes | yes | — | — | mutation |
| POST | `/api/v1/onboarding/driver-license/confirm` | `onboarding:driver_license_confirm` @L41 | yes | yes | — | HTTPException | mutation |
| GET | `/api/v1/meta/roles` | `meta:list_roles` @L16 | yes | yes | — | — | read |
| POST | `/api/v1/payroll/pay-periods` | `payroll:create_pay_period` @L69 | yes | yes | app.deps.entitlements.require_payroll_entitlement | get_current_user | mutation |
| GET | `/api/v1/payroll/pay-periods` | `payroll:list_pay_periods` @L92 | yes | yes | app.deps.entitlements.require_payroll_entitlement | HTTPException, get_current_user | read |
| GET | `/api/v1/payroll/pay-periods/{pay_period_id}` | `payroll:get_pay_period` @L119 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | read |
| PATCH | `/api/v1/payroll/pay-periods/{pay_period_id}` | `payroll:update_pay_period` @L128 | yes | yes | app.deps.entitlements.require_payroll_entitlement | HTTPException | mutation |
| POST | `/api/v1/payroll/pay-periods/{pay_period_id}/open` | `payroll:open_pay_period` @L162 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | mutation |
| POST | `/api/v1/payroll/pay-periods/{pay_period_id}/close` | `payroll:close_pay_period` @L183 | yes | yes | app.deps.entitlements.require_payroll_entitlement | HTTPException | mutation |
| POST | `/api/v1/payroll/pay-profiles` | `payroll:create_pay_profile` @L241 | yes | yes | app.deps.entitlements.require_payroll_entitlement | HTTPException | mutation |
| GET | `/api/v1/payroll/pay-profiles` | `payroll:list_pay_profiles` @L276 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | read |
| GET | `/api/v1/payroll/pay-profiles/{profile_id}` | `payroll:get_pay_profile` @L300 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | read |
| PATCH | `/api/v1/payroll/pay-profiles/{profile_id}` | `payroll:update_pay_profile` @L309 | yes | yes | app.deps.entitlements.require_payroll_entitlement | HTTPException | mutation |
| POST | `/api/v1/payroll/pay-profiles/{profile_id}/deactivate` | `payroll:deactivate_pay_profile` @L341 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | mutation |
| POST | `/api/v1/payroll/pay-entries` | `payroll:create_pay_entry` @L389 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | mutation |
| GET | `/api/v1/payroll/pay-entries` | `payroll:list_pay_entries` @L459 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | read |
| PATCH | `/api/v1/payroll/pay-entries/{entry_id}` | `payroll:update_pay_entry` @L479 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | mutation |
| POST | `/api/v1/payroll/pay-entries/{entry_id}/void` | `payroll:void_pay_entry` @L510 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | mutation |
| GET | `/api/v1/payroll/pay-periods/{pay_period_id}/summary` | `payroll:summarize_pay_period` @L532 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | read |
| GET | `/api/v1/payroll/pay-runs` | `pay_runs:list_pay_runs` @L128 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | read |
| POST | `/api/v1/payroll/pay-runs` | `pay_runs:create_pay_run` @L158 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | mutation |
| POST | `/api/v1/payroll/pay-runs/{run_id}/generate` | `pay_runs:generate_pay_run` @L204 | yes | yes | app.deps.entitlements.require_payroll_entitlement | HTTPException | mutation |
| POST | `/api/v1/payroll/pay-runs/{run_id}/finalize` | `pay_runs:finalize_pay_run` @L314 | yes | yes | app.deps.entitlements.require_payroll_entitlement | HTTPException | mutation |
| GET | `/api/v1/payroll/pay-runs/{run_id}` | `pay_runs:get_pay_run` @L358 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | read |
| GET | `/api/v1/payroll/pay-runs/{run_id}/payees` | `pay_runs:list_pay_run_payees` @L378 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | read |
| GET | `/api/v1/payroll/pay-runs/{run_id}/items` | `pay_runs:list_pay_run_items` @L426 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | read |
| GET | `/api/v1/payroll/loads/{load_id}/settlement` | `pay_runs:get_load_settlement` @L464 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | read |
| GET | `/api/v1/payroll/documents` | `pay_runs:list_pay_documents` @L537 | yes | yes | app.deps.entitlements.require_payroll_entitlement | — | read |
| GET | `/api/v1/payroll/documents/{document_id}/download` | `pay_runs:download_pay_document` @L563 | yes | yes | app.deps.entitlements.require_payroll_entitlement | HTTPException | read |
| GET | `/api/v1/me` | `me:get_me` @L83 | yes | no | — | get_current_user | read |
| PATCH | `/api/v1/me/preferences` | `me:patch_me_preferences` @L137 | yes | no | — | HTTPException, get_current_user | mutation |
| POST | `/api/v1/auth/refresh` | `auth:refresh` @L114 | no | no | — | HTTPException, token | mutation |
| POST | `/api/v1/auth/logout` | `auth:logout` @L219 | no | no | — | token | mutation |
| GET | `/api/v1/auth/me` | `auth:auth_me` @L234 | yes | no | — | get_current_user | read |
| POST | `/api/v1/auth/forgot-password` | `auth:forgot_password` @L311 | no | no | — | HTTPException, token | mutation |
| POST | `/api/v1/auth/reset-password` | `auth:reset_password` @L449 | no | no | — | HTTPException, token | mutation |
| POST | `/api/v1/auth/accept-invite` | `auth:accept_invite` @L534 | no | yes | — | HTTPException, token | mutation |
| POST | `/api/v1/auth/login` | `auth:login` @L847 | no | no | — | HTTPException, token | mutation |
| POST | `/api/v1/auth/login-step-up/issue` | `auth:login_step_up_issue` @L1118 | no | no | — | HTTPException | mutation |
| POST | `/api/v1/auth/login-step-up/verify` | `auth:login_step_up_verify` @L1150 | no | no | — | HTTPException | mutation |
| POST | `/api/v1/auth/workspaces` | `auth:create_workspace` @L1180 | yes | no | — | HTTPException, get_current_platform_user, token | mutation |
| POST | `/api/v1/brokers` | `brokers:create_broker` @L37 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/brokers` | `brokers:list_brokers` @L48 | yes | yes | — | get_current_user | read |
| GET | `/api/v1/brokers/resolve-identity` | `brokers:resolve_broker_identity` @L72 | yes | yes | — | get_current_user | read |
| POST | `/api/v1/brokers/{broker_id}/archive` | `brokers:archive_broker` @L93 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/brokers/{broker_id}/unarchive` | `brokers:unarchive_broker` @L104 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/brokers/{broker_id}/workspace` | `brokers:get_broker_workspace` @L115 | yes | yes | — | HTTPException, get_current_user | read |
| GET | `/api/v1/brokers/{broker_id}` | `brokers:get_broker` @L131 | yes | yes | — | HTTPException, get_current_user | read |
| PATCH | `/api/v1/brokers/{broker_id}` | `brokers:update_broker` @L144 | yes | yes | — | get_current_user | mutation |
| DELETE | `/api/v1/brokers/{broker_id}` | `brokers:delete_broker` @L156 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/brokers/{broker_id}/contacts` | `brokers:list_contacts` @L170 | yes | yes | — | get_current_user | read |
| POST | `/api/v1/brokers/{broker_id}/contacts` | `brokers:create_contact` @L191 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/brokers/{broker_id}/contacts/{contact_id}` | `brokers:get_contact` @L203 | yes | yes | — | HTTPException, get_current_user | read |
| PATCH | `/api/v1/brokers/{broker_id}/contacts/{contact_id}` | `brokers:update_contact` @L217 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/brokers/{broker_id}/contacts/{contact_id}/archive` | `brokers:archive_contact` @L230 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/brokers/{broker_id}/contacts/{contact_id}/unarchive` | `brokers:unarchive_contact` @L242 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/brokers/{broker_id}/domains` | `brokers:list_domains` @L257 | yes | yes | — | get_current_user | read |
| POST | `/api/v1/brokers/{broker_id}/domains` | `brokers:create_domain` @L278 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/brokers/{broker_id}/domains/{domain_id}` | `brokers:get_domain` @L290 | yes | yes | — | HTTPException, get_current_user | read |
| PATCH | `/api/v1/brokers/{broker_id}/domains/{domain_id}` | `brokers:update_domain` @L304 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/brokers/{broker_id}/domains/{domain_id}/archive` | `brokers:archive_domain` @L317 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/brokers/{broker_id}/domains/{domain_id}/unarchive` | `brokers:unarchive_domain` @L329 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/brokers/{broker_id}/aliases` | `brokers:list_aliases` @L344 | yes | yes | — | get_current_user | read |
| POST | `/api/v1/brokers/{broker_id}/aliases` | `brokers:create_alias` @L365 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/brokers/{broker_id}/aliases/{alias_id}` | `brokers:get_alias` @L377 | yes | yes | — | HTTPException, get_current_user | read |
| PATCH | `/api/v1/brokers/{broker_id}/aliases/{alias_id}` | `brokers:update_alias` @L391 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/brokers/{broker_id}/aliases/{alias_id}/archive` | `brokers:archive_alias` @L404 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/brokers/{broker_id}/aliases/{alias_id}/unarchive` | `brokers:unarchive_alias` @L416 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/brokers/{broker_id}/known-senders` | `brokers:list_known_senders` @L431 | yes | yes | — | get_current_user | read |
| POST | `/api/v1/brokers/{broker_id}/known-senders` | `brokers:create_known_sender` @L452 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/brokers/{broker_id}/known-senders/{known_sender_id}` | `brokers:get_known_sender` @L464 | yes | yes | — | HTTPException, get_current_user | read |
| PATCH | `/api/v1/brokers/{broker_id}/known-senders/{known_sender_id}` | `brokers:update_known_sender` @L478 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/brokers/{broker_id}/known-senders/{known_sender_id}/archive` | `brokers:archive_known_sender` @L491 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/brokers/{broker_id}/known-senders/{known_sender_id}/unarchive` | `brokers:unarchive_known_sender` @L503 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/customs-brokers/search` | `customs_brokers:search_customs_brokers` @L23 | yes | yes | — | get_current_user | read |
| POST | `/api/v1/customs-brokers` | `customs_brokers:create_customs_broker` @L37 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/customs-brokers` | `customs_brokers:list_customs_brokers` @L47 | yes | yes | — | get_current_user | read |
| GET | `/api/v1/customs-brokers/{broker_id}` | `customs_brokers:get_customs_broker` @L63 | yes | yes | — | HTTPException, get_current_user | read |
| PATCH | `/api/v1/customs-brokers/{broker_id}` | `customs_brokers:update_customs_broker` @L76 | yes | yes | — | get_current_user | mutation |
| DELETE | `/api/v1/customs-brokers/{broker_id}` | `customs_brokers:delete_customs_broker` @L87 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/customs-brokers/{broker_id}/contacts` | `customs_brokers:list_customs_broker_contacts` @L98 | yes | yes | — | get_current_user | read |
| POST | `/api/v1/customs-brokers/{broker_id}/contacts` | `customs_brokers:create_customs_broker_contact` @L114 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/customs-brokers/{broker_id}/contacts/{contact_id}` | `customs_brokers:get_customs_broker_contact` @L126 | yes | yes | — | HTTPException, get_current_user | read |
| PATCH | `/api/v1/customs-brokers/{broker_id}/contacts/{contact_id}` | `customs_brokers:update_customs_broker_contact` @L140 | yes | yes | — | get_current_user | mutation |
| DELETE | `/api/v1/customs-brokers/{broker_id}/contacts/{contact_id}` | `customs_brokers:delete_customs_broker_contact` @L152 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/loads` | `loads:create_load` @L30 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/loads` | `loads:list_loads` @L45 | yes | yes | — | get_current_user | read |
| POST | `/api/v1/loads/parse-document` | `loads:parse_load_workspace_document` @L78 | yes | yes | — | HTTPException, get_current_user | mutation |
| GET | `/api/v1/loads/{load_id}` | `loads:get_load_detail` @L118 | yes | yes | — | HTTPException, get_current_user | read |
| PATCH | `/api/v1/loads/{load_id}` | `loads:update_load` @L131 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/loads/{load_id}/confirm-document-snapshot` | `loads:confirm_document_snapshot` @L152 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/loads/{load_id}/mark-ready` | `loads:mark_load_ready` @L171 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/loads/{load_id}/custody` | `loads:get_load_custody` @L186 | yes | yes | — | get_current_user | read |
| GET | `/api/v1/loads/{load_id}/custody-events` | `loads:list_load_custody_events` @L197 | yes | yes | — | get_current_user | read |
| GET | `/api/v1/loads/{load_id}/notes` | `loads:list_load_notes` @L212 | yes | yes | — | get_current_user | read |
| POST | `/api/v1/loads/{load_id}/notes` | `loads:add_load_note` @L223 | yes | yes | — | get_current_user | mutation |
| DELETE | `/api/v1/loads/{load_id}` | `loads:delete_load` @L244 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/terminals` | `terminals:list_terminals` @L23 | yes | yes | — | get_current_user | read |
| POST | `/api/v1/terminals` | `terminals:create_terminal` @L33 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/terminals/{terminal_id}` | `terminals:get_terminal` @L45 | yes | yes | — | get_current_user | read |
| PUT | `/api/v1/terminals/{terminal_id}` | `terminals:update_terminal` @L55 | yes | yes | — | get_current_user | mutation |
| PATCH | `/api/v1/terminals/{terminal_id}` | `terminals:patch_terminal` @L68 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trips` | `trips:create_planned_trip` @L31 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trips/{trip_id}/cancel` | `trips:cancel_trip` @L52 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trips/{trip_id}/complete` | `trips:complete_trip` @L64 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trips/{trip_id}/loads` | `trips:add_load_to_trip` @L88 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/remove` | `trips:remove_load_from_trip` @L103 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/activate` | `trips:activate_trip_load` @L116 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/complete` | `trips:complete_trip_load` @L130 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/accept-custody` | `trips:accept_load_custody` @L147 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/yard-handoff` | `trips:yard_handoff_load_custody` @L172 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/take-custody` | `trips:take_load_custody` @L197 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/trips` | `trips:list_trips` @L219 | yes | yes | — | get_current_user | read |
| GET | `/api/v1/trips/{trip_id}` | `trips:get_trip` @L240 | yes | yes | — | HTTPException, get_current_user | read |
| PUT | `/api/v1/trips/{trip_id}/assignment` | `trips:put_trip_assignment` @L253 | yes | yes | — | get_current_user | mutation |
| PUT | `/api/v1/trips/{trip_id}/schedule` | `trips:put_trip_schedule` @L283 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trips/{trip_id}/execution-signal` | `trips:post_trip_execution_signal` @L297 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/load-lab/openai-smoke` | `load_lab:openai_smoke` @L32 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/load-lab/runs/upload` | `load_lab:upload_run` @L65 | yes | yes | — | HTTPException, get_current_user | mutation |
| GET | `/api/v1/load-lab/runs` | `load_lab:list_runs` @L92 | yes | yes | — | get_current_user | read |
| DELETE | `/api/v1/load-lab/runs` | `load_lab:clear_runs` @L103 | yes | yes | — | HTTPException, get_current_user, is_tenant_admin | mutation |
| GET | `/api/v1/load-lab/runs/{run_id}` | `load_lab:get_run` @L116 | yes | yes | — | HTTPException, get_current_user | read |
| POST | `/api/v1/load-lab/runs/{run_id}/semantic-extract` | `load_lab:semantic_extract` @L129 | yes | yes | — | HTTPException, get_current_user | mutation |
| GET | `/api/v1/load-lab/runs/{run_id}/field-learning-events` | `load_lab:list_field_learning_events` @L162 | yes | yes | — | HTTPException, get_current_user | read |
| POST | `/api/v1/load-lab/runs/{run_id}/field-learning-events` | `load_lab:create_field_learning_event` @L199 | yes | yes | — | HTTPException, get_current_user | mutation |
| POST | `/api/v1/load-lab/runs/{run_id}/lab-review` | `load_lab:recompute_lab_review` @L240 | yes | yes | — | HTTPException, get_current_user | mutation |
| GET | `/api/v1/audit-events/by-entity` | `audit_events:list_audit_events_by_entity` @L17 | yes | yes | — | get_current_user | read |
| GET | `/api/v1/dispatch/board` | `dispatch:get_dispatch_board` @L19 | yes | yes | — | get_current_user | read |
| POST | `/api/v1/trucks` | `trucks:create_truck` @L23 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/trucks` | `trucks:list_trucks` @L33 | yes | yes | — | get_current_user | read |
| GET | `/api/v1/trucks/{truck_id}/suggested-trailer` | `trucks:get_truck_suggested_trailer` @L61 | yes | yes | — | HTTPException, get_current_user | read |
| GET | `/api/v1/trucks/{truck_id}` | `trucks:get_truck` @L86 | yes | yes | — | HTTPException, get_current_user | read |
| PATCH | `/api/v1/trucks/{truck_id}` | `trucks:update_truck` @L99 | yes | yes | — | get_current_user | mutation |
| POST | `/api/v1/trailers` | `trailers:create_trailer` @L20 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/trailers` | `trailers:list_trailers` @L30 | yes | yes | — | get_current_user | read |
| GET | `/api/v1/trailers/{trailer_id}` | `trailers:get_trailer` @L58 | yes | yes | — | HTTPException, get_current_user | read |
| PATCH | `/api/v1/trailers/{trailer_id}` | `trailers:update_trailer` @L71 | yes | yes | — | get_current_user | mutation |
| GET | `/api/v1/dashboard/summary` | `dashboard:dashboard_summary` @L38 | yes | yes | — | HTTPException, get_current_user | read |
| GET | `/api/v1/admin/company-profile` | `tenant_admin:get_company_profile` @L138 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, is_tenant_admin | read |
| PATCH | `/api/v1/admin/person-setup-ui-mode` | `tenant_admin:patch_person_setup_ui_mode` @L271 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| PATCH | `/api/v1/admin/doc-request-link-expiry` | `tenant_admin:patch_doc_request_link_expiry` @L302 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, applicant, get_current_user, is_tenant_admin | mutation |
| GET | `/api/v1/admin/users` | `tenant_admin:list_tenant_users` @L470 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | get_current_user | read |
| GET | `/api/v1/admin/users/{user_id}/sign-in-security` | `tenant_admin:get_user_sign_in_security` @L512 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | read |
| POST | `/api/v1/admin/users/{user_id}/unlock-sign-in` | `tenant_admin:unlock_user_sign_in_for_tenant` @L541 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, has_full_access | mutation |
| POST | `/api/v1/admin/users/invite` | `tenant_admin:invite_user` @L623 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, has_full_access, token | mutation |
| POST | `/api/v1/admin/users/{user_id}/suspend` | `tenant_admin:suspend_user` @L815 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, has_full_access | mutation |
| POST | `/api/v1/admin/users/{user_id}/reactivate` | `tenant_admin:reactivate_user` @L864 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, has_full_access | mutation |
| POST | `/api/v1/admin/users/{user_id}/resend-invite` | `tenant_admin:resend_invite_for_user` @L911 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, has_full_access | mutation |
| DELETE | `/api/v1/admin/users/{user_id}` | `tenant_admin:remove_user_from_workspace` @L967 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, has_full_access | mutation |
| GET | `/api/v1/admin/broker-intake-settings` | `tenant_admin:get_broker_intake_settings` @L1038 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, is_tenant_admin | read |
| PATCH | `/api/v1/admin/broker-intake-settings` | `tenant_admin:patch_broker_intake_settings` @L1052 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| GET | `/api/v1/admin/dispatch-numbering` | `dispatch_numbering_admin:get_dispatch_numbering` @L34 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, is_tenant_admin | read |
| PUT | `/api/v1/admin/dispatch-numbering` | `dispatch_numbering_admin:put_dispatch_numbering` @L52 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| GET | `/api/v1/admin/email-config/gmail/authorize` | `admin_email_config:gmail_authorize` @L385 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | read |
| GET | `/api/v1/admin/email-config/gmail/ingestion-health` | `admin_email_config:gmail_ingestion_health` @L408 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin, token | read |
| GET | `/api/v1/admin/email-config/gmail/callback` | `admin_email_config:gmail_callback` @L486 | yes | no | app.deps.entitlements.require_email_mailbox_entitlement | get_current_user, is_tenant_admin, token | read |
| GET | `/api/v1/admin/email-config/microsoft/oauth-status` | `admin_email_config:microsoft_oauth_status` @L684 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | read |
| GET | `/api/v1/admin/email-config/microsoft/authorize` | `admin_email_config:microsoft_authorize` @L696 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | read |
| GET | `/api/v1/admin/email-config/microsoft/callback` | `admin_email_config:microsoft_callback` @L718 | yes | no | app.deps.entitlements.require_email_mailbox_entitlement | get_current_user, is_tenant_admin, token | read |
| POST | `/api/v1/admin/email-config/microsoft/renew-subscription` | `admin_email_config:microsoft_renew_subscription_route` @L821 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/admin/email-config/microsoft/sync-now` | `admin_email_config:microsoft_sync_now` @L852 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/admin/email-config/primary/disconnect` | `admin_email_config:disconnect_primary_email_config` @L878 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| GET | `/api/v1/admin/email-config/primary` | `admin_email_config:get_primary_email_config` @L941 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | read |
| PUT | `/api/v1/admin/email-config/primary` | `admin_email_config:upsert_primary_email_config` @L975 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin, token | mutation |
| POST | `/api/v1/admin/email-config/primary/test` | `admin_email_config:test_primary_email_config` @L1184 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin, token | mutation |
| POST | `/api/v1/admin/email-config/primary/test-inbound` | `admin_email_config:test_primary_inbound_only` @L1335 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/admin/email-config/primary/test-outbound` | `admin_email_config:test_primary_outbound_only` @L1421 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/admin/email-config/other/sync-now` | `admin_email_config:other_imap_sync_now` @L1502 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/admin/email-config/gmail/register-watch` | `admin_email_config:gmail_register_watch` @L1541 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/admin/email-config/gmail/renew-watch` | `admin_email_config:gmail_renew_watch` @L1586 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| POST | `/api/v1/admin/email-config/gmail/sync-now` | `admin_email_config:gmail_sync_now` @L1647 | yes | yes | app.deps.entitlements.require_email_mailbox_entitlement | HTTPException, get_current_user, is_tenant_admin | mutation |
| GET | `/api/v1/fuel/providers` | `fuel:list_fuel_providers` @L100 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/providers/{provider_code}` | `fuel:get_fuel_provider` @L108 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/provider-connections` | `fuel:list_fuel_provider_connections` @L120 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| POST | `/api/v1/fuel/provider-connections` | `fuel:create_fuel_provider_connection` @L135 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| GET | `/api/v1/fuel/provider-connections/{connection_id}` | `fuel:get_fuel_provider_connection` @L149 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | read |
| PUT | `/api/v1/fuel/provider-connections/{connection_id}` | `fuel:update_fuel_provider_connection` @L163 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/provider-connections/{connection_id}/test` | `fuel:test_fuel_provider_connection` @L184 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/provider-connections/{connection_id}/sync` | `fuel:sync_fuel_provider_connection` @L200 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| GET | `/api/v1/fuel/dashboard/stats` | `fuel:get_fuel_dashboard_stats` @L216 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/processed` | `fuel:list_processed_fuel_route` @L230 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/processed/{batch_id}` | `fuel:get_processed_fuel_batch_route` @L248 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/review/queue` | `fuel:list_fuel_review_queue` @L273 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/review/batches/{batch_id}` | `fuel:get_fuel_review_workspace` @L284 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/review/batches/{batch_id}/document` | `fuel:get_fuel_review_document` @L299 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | read |
| POST | `/api/v1/fuel/review/batches/{batch_id}/start` | `fuel:start_fuel_batch_review` @L335 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/review/batches/{batch_id}/rows/{entity_type}/{entity_id}/confirm` | `fuel:confirm_fuel_review_row` @L365 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/review/batches/{batch_id}/process` | `fuel:process_fuel_batch_review` @L397 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| GET | `/api/v1/fuel/reconciliation/batches/{batch_id}` | `fuel:get_fuel_batch_reconciliation` @L427 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | read |
| POST | `/api/v1/fuel/reconciliation/batches/{batch_id}/run` | `fuel:run_fuel_batch_reconciliation` @L460 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/bvd/imports` | `fuel:upload_bvd_import` @L491 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| GET | `/api/v1/fuel/bvd/imports` | `fuel:list_bvd_imports` @L523 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/bvd/history` | `fuel:list_bvd_completed_history` @L541 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/completed-basic` | `fuel:get_bvd_completed_basic` @L552 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/rows` | `fuel:list_bvd_import_rows` @L569 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/source-reconciliation` | `fuel:get_bvd_import_source_reconciliation` @L588 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/summary` | `fuel:get_bvd_import_summary` @L602 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| POST | `/api/v1/fuel/bvd/imports/{import_id}/save-review` | `fuel:save_bvd_import_review` @L615 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/bvd/imports/{import_id}/process` | `fuel:process_bvd_import_review` @L634 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/bvd/imports/{import_id}/discard` | `fuel:discard_bvd_import_stage` @L657 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| GET | `/api/v1/fuel/charge-categories` | `fuel:list_fuel_charge_categories` @L679 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/canonical-transactions` | `fuel:list_bvd_import_canonical_transactions` @L711 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | read |
| POST | `/api/v1/fuel/bvd/imports/{import_id}/classify-canonical` | `fuel:classify_bvd_import_canonical_transactions` @L731 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| PATCH | `/api/v1/fuel/transactions/{transaction_id}/classification` | `fuel:set_fuel_transaction_classification` @L757 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/classification-summary` | `fuel:get_bvd_import_classification_summary` @L791 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/classification-unresolved-groups` | `fuel:list_bvd_import_unresolved_classification_groups` @L816 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| POST | `/api/v1/fuel/bvd/imports/{import_id}/classification-reason-group` | `fuel:classify_bvd_import_reason_group` @L841 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/classification-audit` | `fuel:list_bvd_import_classification_audit` @L876 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/nationwide/history` | `fuel:list_nationwide_completed_history` @L894 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/nationwide/imports/{import_id}/completed-basic` | `fuel:get_nationwide_completed_basic` @L907 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| POST | `/api/v1/fuel/nationwide/imports` | `fuel:upload_nationwide_import` @L921 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| GET | `/api/v1/fuel/nationwide/imports/{import_id}/rows` | `fuel:list_nationwide_import_rows` @L951 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/nationwide/imports/{import_id}/source-reconciliation` | `fuel:get_nationwide_import_source_reconciliation` @L970 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/fuel/nationwide/imports/{import_id}/summary` | `fuel:get_nationwide_import_summary` @L984 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | read |
| POST | `/api/v1/fuel/nationwide/imports/{import_id}/save-review` | `fuel:save_nationwide_import_review` @L998 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/nationwide/imports/{import_id}/process` | `fuel:process_nationwide_import_review_route` @L1017 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/nationwide/imports/{import_id}/discard` | `fuel:discard_nationwide_import_stage_route` @L1040 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | mutation |
| GET | `/api/v1/fuel/nationwide/imports/{import_id}/document` | `fuel:get_nationwide_import_document` @L1062 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | read |
| POST | `/api/v1/fuel/manual-entry/stages` | `fuel:create_manual_entry_stage` @L1089 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/manual-entry/stages/receipt` | `fuel:create_manual_entry_receipt_stage` @L1108 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| GET | `/api/v1/fuel/manual-entry/stages/{stage_id}` | `fuel:get_manual_entry_stage` @L1143 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | read |
| PATCH | `/api/v1/fuel/manual-entry/stages/{stage_id}` | `fuel:patch_manual_entry_stage` @L1157 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/manual-entry/stages/{stage_id}/validate` | `fuel:validate_manual_entry_stage` @L1182 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/manual-entry/stages/{stage_id}/process` | `fuel:process_manual_entry_stage` @L1207 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| POST | `/api/v1/fuel/manual-entry/stages/{stage_id}/discard` | `fuel:discard_manual_entry_stage` @L1232 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | fuel_capability, require_fuel_capability | mutation |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/document` | `fuel:get_bvd_import_document` @L1245 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, fuel_capability, require_fuel_capability | read |
| GET | `/api/v1/tolls/providers` | `tolls:list_toll_providers` @L69 | yes | no | app.deps.entitlements.require_admin_sensitive_entitlement | — | read |
| POST | `/api/v1/tolls/files/upload` | `tolls:upload_toll_file` @L74 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | mutation |
| POST | `/api/v1/tolls/files/csv` | `tolls:upload_toll_csv_file` @L106 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | mutation |
| GET | `/api/v1/tolls/files` | `tolls:list_toll_csv_files` @L133 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | get_current_user | read |
| GET | `/api/v1/tolls/files/{batch_id}` | `tolls:get_toll_csv_file_batch` @L145 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | read |
| POST | `/api/v1/tolls/files/pdf` | `tolls:upload_toll_pdf_file` @L169 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | mutation |
| GET | `/api/v1/tolls/pdf-reviews` | `tolls:list_toll_pdf_review_batches` @L198 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | get_current_user | read |
| GET | `/api/v1/tolls/pdf-reviews/{batch_id}` | `tolls:get_toll_pdf_review_batch` @L210 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | read |
| PATCH | `/api/v1/tolls/pdf-reviews/{batch_id}/rows/{row_id}` | `tolls:patch_toll_pdf_review_row` @L234 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | mutation |
| POST | `/api/v1/tolls/pdf-reviews/{batch_id}/process` | `tolls:process_toll_pdf_review_batch` @L268 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | mutation |
| POST | `/api/v1/tolls/manual-entry/stages` | `tolls:create_toll_manual_stage` @L292 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | get_current_user | mutation |
| GET | `/api/v1/tolls/manual-entry/stages` | `tolls:list_toll_manual_stages` @L312 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | get_current_user | read |
| GET | `/api/v1/tolls/manual-entry/stages/{stage_id}` | `tolls:get_toll_manual_stage` @L323 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | get_current_user | read |
| PATCH | `/api/v1/tolls/manual-entry/stages/{stage_id}` | `tolls:patch_toll_manual_stage` @L338 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | get_current_user | mutation |
| POST | `/api/v1/tolls/manual-entry/stages/{stage_id}/validate` | `tolls:validate_toll_manual_stage` @L359 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | get_current_user | mutation |
| POST | `/api/v1/tolls/manual-entry/stages/{stage_id}/discard` | `tolls:discard_toll_manual_stage` @L378 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | get_current_user | mutation |
| POST | `/api/v1/tolls/manual-entry/stages/{stage_id}/process` | `tolls:process_toll_manual_stage_endpoint` @L393 | yes | yes | app.deps.entitlements.require_admin_sensitive_entitlement | HTTPException, get_current_user | mutation |
| POST | `/api/v1/email-threads/gmail/pull-delta` | `email_threads:gmail_pull_delta_from_inbox` @L79 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | HTTPException, get_current_user | mutation |
| GET | `/api/v1/email-threads` | `email_threads:list_email_threads` @L132 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | read |
| POST | `/api/v1/email-threads/{thread_id}/create-draft-load` | `email_threads:create_draft_load_from_email_thread` @L155 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | mutation |
| POST | `/api/v1/email-threads/{thread_id}/link-load` | `email_threads:link_load_to_email_thread` @L171 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | mutation |
| GET | `/api/v1/email-threads/{thread_id}` | `email_threads:get_email_thread_detail` @L188 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | read |
| GET | `/api/v1/email-threads/{thread_id}/intake-qr-extractions` | `email_threads:list_email_thread_intake_qr_extractions` @L198 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | read |
| GET | `/api/v1/email-threads/{thread_id}/messages` | `email_threads:list_email_thread_messages` @L211 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | read |
| POST | `/api/v1/email-threads/{thread_id}/recompute-intake` | `email_threads:recompute_email_thread_intake` @L229 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | mutation |
| POST | `/api/v1/email-threads/{thread_id}/upload-pdf` | `email_threads:upload_pdf_to_email_thread` @L240 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | mutation |
| POST | `/api/v1/email-threads/{thread_id}/disregard` | `email_threads:disregard_email_thread` @L259 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | mutation |
| GET | `/api/v1/email-threads/{thread_id}/intake-review` | `email_threads:get_email_thread_intake_review` @L269 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | read |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/claim` | `email_threads:claim_email_thread_intake_review` @L286 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | HTTPException, get_current_user | mutation |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/resolve` | `email_threads:resolve_email_thread_intake_review` @L314 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | mutation |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/dismiss` | `email_threads:dismiss_email_thread_intake_review` @L339 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | mutation |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/duplicate/link-prior` | `email_threads:duplicate_intake_review_link_prior` @L364 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | mutation |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/duplicate/confirm` | `email_threads:duplicate_intake_review_confirm` @L394 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | mutation |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/duplicate/dismiss-false-positive` | `email_threads:duplicate_intake_review_dismiss_false_positive` @L418 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | mutation |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/reopen` | `email_threads:reopen_email_thread_intake_review` @L442 | yes | yes | app.deps.entitlements.require_email_inbox_entitlement | get_current_user | mutation |
| POST | `/api/v1/webhooks/gmail/pubsub` | `gmail_pubsub:gmail_pubsub_push` @L63 | no | no | — | HTTPException | mutation |
| GET | `/api/v1/webhooks/microsoft-graph` | `microsoft_graph_webhook:microsoft_graph_notification` @L23 | no | no | — | HTTPException | read |
| POST | `/api/v1/webhooks/microsoft-graph` | `microsoft_graph_webhook:microsoft_graph_notification` @L23 | no | no | — | HTTPException | mutation |
| GET | `/dashboard` | `app.main:serve_dashboard` @L183 | no | no | — | — | read |
| GET | `/` | `app.main:root` @L198 | no | no | — | — | read |
| GET | `/healthz` | `app.main:healthz` @L203 | no | no | — | — | read |
| GET | `/api/v1/healthz` | `app.main:healthz_v1` @L208 | no | no | — | — | read |

### Router registration (`app/main.py`)

All routers are **statically** imported in `app/main.py:128-173`. `dev_tools` / `dev_tools_db` mount only when `settings.allows_tenant_resolution_shortcuts()` (`app/main.py:162-165`).

---

## C. Existing authorization model and identity flow

### C.1 Tenant edge (`TenantContextMiddleware`)

- Allowlisted paths skip tenant resolution (`app/middleware/tenant_context.py:23-38`, `108-109`).
- `/api/v1/platform/*` skips tenant (`158-163`).
- Resolves tenant from **Host subdomain**, Gmail OAuth `state`, JWT fallback paths (`/api/v1/auth/me`, `/api/v1/auth/refresh`), or dev shortcuts (`312-361`).
- **Membership gate** for authenticated API: platform mode checks `TenantMembership.status == active` (`433-444`); tenant-DB auth mode defers workspace checks to `get_current_user` (`419-431`).
- **Public auth** paths skip membership (`391-400`): login, forgot/reset password, accept-invite, step-up OTP.
- **Applicant** prefix skips membership (`402-410`): `/api/v1/driver-onboarding/applicant/*`.

### C.2 JWT → `CurrentUser` (`app/deps/auth.py`)

| Mode | `sub` claim | Role source | Extra checks |
|------|-------------|-------------|--------------|
| Platform (`tenant_auth_mode=platform`) | `platform_users.id` | JWT `roles[0]` overridden by `PlatformTenantMember.role` (`197-198`) | User `ACTIVE`, `session_version`, membership (`188-195`) |
| Tenant DB (`tenant_auth_mode=tenant`) | `tenant_users.id` | `TenantWorkspaceMember.role` (`145-146`) | Tenant user `ACTIVE`, workspace member `active`, `PlatformTenantUserMap` required (`155-159`) |

**Cross-tenant:** JWT `tenant_id` must match `request.state.tenant_id` (`99-103`).

### C.3 Temporary admin / access-level mapping (`app/deps/admin.py`)

- `TENANT_ADMIN_ROLES` / `FULL_ACCESS_ROLES`: `OWNER`, `ADMIN`, `TENANT_ADMIN`, `TENANT_OWNER` (`8-12`).
- `role_to_access_level`: non-admin roles → `READ_ONLY` (`15-19`).
- `access_level_to_role`: `FULL_ACCESS` → **`TENANT_ADMIN`** (not a distinct operational role) (`22-26`).
- `require_tenant_admin` dependency (`app/dependencies/authz.py:7-13`) returns `RBAC_FORBIDDEN`.

### C.4 Entitlements (subscription, not RBAC)

Features: `payroll`, `email_inbox`, `email_mailbox`, `admin_sensitive`, `driver_documents`, `onboarding` (`app/deps/entitlements.py:17-71`). Requires `PlatformSubscription` in `TRIAL_ACTIVE` or `ACTIVE` (`40-44`).

### C.5 Frontend gating (not authorization)

- `apps/web/src/auth/roles.ts` mirrors backend admin sets.
- `AdminRouteGuard` (`apps/web/src/components/AdminRouteGuard.tsx:9-43`): `TENANT_MEMBER` may reach **`/admin/users` only**; other `/admin/*` requires tenant admin roles.
- Payroll UI uses `hasRole(..., TENANT_ADMIN)` only (`PayRunsPage.tsx`, `PayRunNewPage.tsx`) — **stricter than backend** on some payroll routes.
- `AdminUsersPage` invite button uses `hasFullAccess` (`apps/web/src/pages/AdminUsersPage.tsx:17`) — aligns with backend `has_full_access` on invite.
- **No frontend guard** on Loads/Trips/Tolls mutations for READ_ONLY users.

### C.5.1 Frontend role check inventory (complete)

| Location | Check | Effect |
|----------|-------|--------|
| `apps/web/src/auth/roles.ts:9-17` | `isTenantAdmin`, `hasFullAccess` | Mirrors `TENANT_ADMIN_ROLES` / `FULL_ACCESS_ROLES` |
| `apps/web/src/components/AdminRouteGuard.tsx:27-43` | `isTenantAdmin`, member-only exception | Blocks non-admin from `/admin/*` except `/admin/users` |
| `apps/web/src/pages/AdminUsersPage.tsx:17` | `hasFullAccess` | Hides invite UI for READ_ONLY |
| `apps/web/src/components/TopNav.tsx:261` | `isTenantAdmin` | Admin nav visibility |
| `apps/web/src/pages/LoadLabPage.tsx:246` | `isTenantAdmin` | OpenAI smoke button |
| `apps/web/src/pages/PayRunsPage.tsx:16-25` | `hasRole(TENANT_ADMIN)` | Pay run create CTA |
| `apps/web/src/pages/PayRunNewPage.tsx:35-148` | `hasRole(TENANT_ADMIN)` | Submit pay run |
| `apps/web/src/pages/PayRunDetailPage.tsx:42-162` | `hasRole(TENANT_ADMIN)` | Admin actions on run |
| `apps/web/src/pages/PayPeriodsPage.tsx:17-114` | `hasRole(TENANT_ADMIN)` | Create/close periods |

All other authenticated app routes rely on **API enforcement only** (no `useMe` role checks).

### C.6 Ambiguous / missing status checks (report only)

- `PlatformTenant.status` / `db_status` enforced in middleware (`385-389`); tenant-level `READ_ONLY` status in `tenant_readiness` (`ALLOWED_TENANT_STATUSES`) — **NOT_VERIFIED** whether middleware blocks non-`ACTIVE` tenant business status beyond `row.status`.
- `PlatformTenantMember` / invite pending states on mutating routes — **NOT_VERIFIED** globally.
- Suspended membership: middleware uses `TenantMembership.status == active` only — suspended users blocked; **READ_ONLY active members are not blocked from mutations**.

---

## D. Endpoint-by-endpoint permission matrix

**Proposed capabilities** are naming targets for Casbin V1. **Current effective access** reflects code today, not desired policy. `NEEDS_APPROVAL` = owner decision required.

| Method | Path | Proposed capability | READ_ONLY (proposed) | FULL_ACCESS ops (proposed) | Tenant admin (proposed) | Current auth / gate |
|--------|------|---------------------|----------------------|----------------------------|-------------------------|---------------------|
| GET | `/openapi.json` | `NEEDS_APPROVAL.unmapped` | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED | none |
| GET | `/docs` | `NEEDS_APPROVAL.unmapped` | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED | none |
| GET | `/docs/oauth2-redirect` | `NEEDS_APPROVAL.unmapped` | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED | none |
| GET | `/redoc` | `NEEDS_APPROVAL.unmapped` | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED | none |
| GET | `/api/v1/health` | `NEEDS_APPROVAL.unmapped` | allow (current) | allow (current) | allow (current) | middleware membership or public auth path |
| GET | `/api/v1/public/tenant/{slug}` | `auth.public.tenant.{slug}` | public/session | public/session | public/session | middleware membership or public auth path |
| GET | `/api/v1/public/check-slug-availability` | `auth.public.check-slug-availability` | public/session | public/session | public/session | middleware membership or public auth path |
| GET | `/api/v1/public/check-signup-email` | `auth.public.check-signup-email` | public/session | public/session | public/session | middleware membership or public auth path |
| GET | `/api/v1/public/check-signup-phone` | `auth.public.check-signup-phone` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/public/signup` | `auth.public.signup` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/public/verify-otp` | `auth.public.verify-otp` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/public/resend-otp` | `auth.public.resend-otp` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/public/cancel-signup` | `auth.public.cancel-signup` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/public/company-setup/w9-upload` | `auth.public.company-setup.w9-upload` | public/session | public/session | public/session | middleware membership or public auth path |
| GET | `/api/v1/public/company-setup/document` | `auth.public.company-setup.document` | public/session | public/session | public/session | middleware membership or public auth path |
| GET | `/api/v1/public/company-setup/prefill` | `auth.public.company-setup.prefill` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/public/company-setup` | `auth.public.company-setup` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/public/workspace-intake` | `auth.public.workspace-intake` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/public/workspace-intake/consume` | `auth.public.workspace-intake.consume` | public/session | public/session | public/session | middleware membership or public auth path |
| GET | `/api/v1/public/workspace-intake/session` | `auth.public.workspace-intake.session` | public/session | public/session | public/session | middleware membership or public auth path |
| GET | `/api/v1/platform/tenants` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| POST | `/api/v1/platform/tenants` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| POST | `/api/v1/platform/tenants/{tenant_id}/provision` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| GET | `/api/v1/platform/tenants/{tenant_id}` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| POST | `/api/v1/platform/tenants/{tenant_id}/retry-provision` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| GET | `/api/v1/platform/extraction-sanitized-patterns` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| PUT | `/api/v1/platform/extraction-sanitized-patterns` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| GET | `/api/v1/platform/global-booking-brokers` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| GET | `/api/v1/platform/global-booking-broker-duplicate-candidates` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| POST | `/api/v1/platform/global-booking-brokers/merge/preview` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| POST | `/api/v1/platform/global-booking-brokers/merge/execute` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| POST | `/api/v1/platform/global-booking-broker-duplicate-candidates/refresh` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| PATCH | `/api/v1/platform/global-booking-broker-duplicate-candidates/{candidate_id}` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| POST | `/api/v1/platform/global-booking-brokers` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| GET | `/api/v1/platform/global-booking-brokers/{broker_id}/audit-events` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| PATCH | `/api/v1/platform/global-booking-brokers/{broker_id}/profile` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| PATCH | `/api/v1/platform/global-booking-brokers/{broker_id}` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| GET | `/api/v1/platform/login-failures` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| POST | `/api/v1/platform/testing/login-lock-status` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| POST | `/api/v1/platform/testing/unlock-login` | `platform.control` | deny | deny | deny (platform key) | X-Platform-Admin-Key |
| POST | `/api/v1/drivers` | `drivers.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/drivers` | `drivers.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/drivers/{driver_id}/assignment-hints` | `drivers.driver_id/assignment-hints.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/drivers/{driver_id}` | `drivers.driver_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/drivers/{driver_id}` | `drivers.driver_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| DELETE | `/api/v1/drivers/{driver_id}` | `drivers.driver_id.delete` | allow (current) | allow (current) | allow (current) | middleware membership or public auth path |
| GET | `/api/v1/drivers/{driver_id}/summary` | `drivers.driver_id/summary.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/driver-person-extensions/{person_id}` | `driver_person_extensions.person_id.view` | deny | deny | allow | JWT/cookie → get_current_user |
| PUT | `/api/v1/driver-person-extensions/{person_id}` | `driver_person_extensions.person_id.update` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/people` | `people.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/people/{person_id}/driver-profile` | `people.person_id/driver-profile.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/people/{person_id}/compensation-setup` | `people.person_id/compensation-setup.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/people/{person_id}/compensation-setup` | `people.person_id/compensation-setup.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/people/{person_id}/driver-role-configuration` | `people.person_id/driver-role-configuration.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/people/{person_id}/driver-role-configuration` | `people.person_id/driver-role-configuration.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/people/{person_id}/audit-log` | `people.person_id/audit-log.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/people/{person_id}` | `people.person_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/people/{person_id}` | `people.person_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/fleet` | `fleet.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/driver-phones` | `driver_phones.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-phones` | `driver_phones.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| DELETE | `/api/v1/driver-phones/{phone_id}` | `driver_phones.phone_id.delete` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-phones/{phone_id}/reactivate` | `driver_phones.phone_id/reactivate.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-documents` | `driver_documents.create` | deny | allow | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-documents/{driver_id}` | `driver_documents.driver_id.create` | deny | allow | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/driver-documents` | `driver_documents.view` | deny | allow | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/driver-documents/{driver_id}` | `driver_documents.driver_id.view` | deny | allow | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-documents/{document_id}/deactivate` | `driver_documents.document_id/deactivate.create` | deny | allow | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-documents/{document_id}/files` | `driver_documents.document_id/files.create` | deny | allow | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/driver-documents/{document_id}/files` | `driver_documents.document_id/files.view` | deny | allow | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-documents/{document_id}/files/{file_id}/deactivate` | `driver_documents.document_id/files/file_id/deactivate.create` | deny | allow | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/onboarding/invite-link` | `tenant.admin.onboarding.invite-link.create` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/driver-onboarding/applicant/application` | `driver_onboarding.applicant/application.view` | n/a | n/a | n/a (invite token) | invite token (handler) |
| GET | `/api/v1/driver-onboarding/applicant/application/events` | `driver_onboarding.applicant/application/events.view` | n/a | n/a | n/a (invite token) | invite token (handler) |
| PUT | `/api/v1/driver-onboarding/applicant/application` | `driver_onboarding.applicant/application.update` | n/a | n/a | n/a (invite token) | invite token (handler) |
| POST | `/api/v1/driver-onboarding/applicant/application/intake` | `driver_onboarding.applicant/application/intake.create` | n/a | n/a | n/a (invite token) | invite token (handler) |
| POST | `/api/v1/driver-onboarding/applicant/application/reset` | `driver_onboarding.applicant/application/reset.create` | n/a | n/a | n/a (invite token) | invite token (handler) |
| POST | `/api/v1/driver-onboarding/applicant/application/dl-upload` | `driver_onboarding.applicant/application/dl-upload.create` | n/a | n/a | n/a (invite token) | invite token (handler) |
| POST | `/api/v1/driver-onboarding/applicant/application/dl-confirm` | `driver_onboarding.applicant/application/dl-confirm.create` | n/a | n/a | n/a (invite token) | invite token (handler) |
| GET | `/api/v1/driver-onboarding/applicant/dl-capture/{token}` | `driver_onboarding.applicant/dl-capture/token.view` | n/a | n/a | n/a (invite token) | invite token (handler) |
| POST | `/api/v1/driver-onboarding/applicant/dl-capture/{token}/upload` | `driver_onboarding.applicant/dl-capture/token/upload.create` | n/a | n/a | n/a (invite token) | invite token (handler) |
| POST | `/api/v1/driver-onboarding/applicant/dl-capture/{token}/confirm` | `driver_onboarding.applicant/dl-capture/token/confirm.create` | n/a | n/a | n/a (invite token) | invite token (handler) |
| GET | `/api/v1/driver-onboarding/applicant/dl-capture/{token}/file` | `driver_onboarding.applicant/dl-capture/token/file.view` | n/a | n/a | n/a (invite token) | invite token (handler) |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/dl-capture-link` | `driver_onboarding.applications/application_id/dl-capture-link.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-onboarding/applicant/application/dl-capture-link` | `driver_onboarding.applicant/application/dl-capture-link.create` | n/a | n/a | n/a (invite token) | invite token (handler) |
| POST | `/api/v1/driver-onboarding/applicant/application/dl-capture-link/email` | `driver_onboarding.applicant/application/dl-capture-link/email.create` | n/a | n/a | n/a (invite token) | invite token (handler) |
| GET | `/api/v1/driver-onboarding/applicant/application/file` | `driver_onboarding.applicant/application/file.view` | n/a | n/a | n/a (invite token) | invite token (handler) |
| POST | `/api/v1/driver-onboarding/applicant/application/document-upload` | `driver_onboarding.applicant/application/document-upload.create` | n/a | n/a | n/a (invite token) | invite token (handler) |
| GET | `/api/v1/driver-onboarding/applications` | `driver_onboarding.applications.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/mark-admin-review-engaged` | `driver_onboarding.applications/application_id/mark-admin-review-engaged.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/driver-onboarding/applications/{application_id}` | `driver_onboarding.applications/application_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/driver-onboarding/applications/{application_id}/review-fields` | `driver_onboarding.applications/application_id/review-fields.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/request-documents` | `driver_onboarding.applications/application_id/request-documents.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/documents/accept` | `driver_onboarding.applications/application_id/documents/accept.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/document-upload` | `driver_onboarding.applications/application_id/document-upload.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/driver-onboarding/applications/{application_id}/file` | `driver_onboarding.applications/application_id/file.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/materialize-person-for-combined-setup` | `driver_onboarding.applications/application_id/materialize-person-for-combined-setup.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/driver-onboarding/applications/{application_id}/combined-driver-approve-readiness` | `driver_onboarding.applications/application_id/combined-driver-approve-readiness.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/approve` | `driver_onboarding.applications/application_id/approve.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/reject` | `driver_onboarding.applications/application_id/reject.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/driver-onboarding/applications/{application_id}/driver-compensation-setup` | `driver_onboarding.applications/application_id/driver-compensation-setup.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PUT | `/api/v1/driver-onboarding/applications/{application_id}/driver-compensation-setup` | `driver_onboarding.applications/application_id/driver-compensation-setup.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/driver-onboarding/applications/{application_id}/complete-onboarding` | `driver_onboarding.applications/application_id/complete-onboarding.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/onboarding/driver-license/ocr` | `onboarding.driver-license/ocr.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/onboarding/driver-license/confirm` | `onboarding.driver-license/confirm.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/meta/roles` | `meta.roles.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/payroll/pay-periods` | `payroll.pay-periods.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/pay-periods` | `payroll.pay-periods.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/pay-periods/{pay_period_id}` | `payroll.pay-periods/pay_period_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/payroll/pay-periods/{pay_period_id}` | `payroll.pay-periods/pay_period_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/payroll/pay-periods/{pay_period_id}/open` | `payroll.pay-periods/pay_period_id/open.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/payroll/pay-periods/{pay_period_id}/close` | `payroll.pay-periods/pay_period_id/close.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/payroll/pay-profiles` | `payroll.pay-profiles.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/pay-profiles` | `payroll.pay-profiles.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/pay-profiles/{profile_id}` | `payroll.pay-profiles/profile_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/payroll/pay-profiles/{profile_id}` | `payroll.pay-profiles/profile_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/payroll/pay-profiles/{profile_id}/deactivate` | `payroll.pay-profiles/profile_id/deactivate.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/payroll/pay-entries` | `payroll.pay-entries.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/pay-entries` | `payroll.pay-entries.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/payroll/pay-entries/{entry_id}` | `payroll.pay-entries/entry_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/payroll/pay-entries/{entry_id}/void` | `payroll.pay-entries/entry_id/void.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/pay-periods/{pay_period_id}/summary` | `payroll.pay-periods/pay_period_id/summary.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/pay-runs` | `payroll.pay-runs.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/payroll/pay-runs` | `payroll.pay-runs.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/payroll/pay-runs/{run_id}/generate` | `payroll.pay-runs/run_id/generate.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/payroll/pay-runs/{run_id}/finalize` | `payroll.pay-runs/run_id/finalize.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/pay-runs/{run_id}` | `payroll.pay-runs/run_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/pay-runs/{run_id}/payees` | `payroll.pay-runs/run_id/payees.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/pay-runs/{run_id}/items` | `payroll.pay-runs/run_id/items.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/loads/{load_id}/settlement` | `payroll.loads/load_id/settlement.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/documents` | `payroll.documents.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/payroll/documents/{document_id}/download` | `payroll.documents/document_id/download.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/me` | `NEEDS_APPROVAL.unmapped` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/me/preferences` | `NEEDS_APPROVAL.unmapped` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/auth/refresh` | `auth.auth.refresh` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/auth/logout` | `auth.auth.logout` | public/session | public/session | public/session | middleware membership or public auth path |
| GET | `/api/v1/auth/me` | `auth.auth.me` | public/session | public/session | public/session | JWT/cookie → get_current_user |
| POST | `/api/v1/auth/forgot-password` | `auth.auth.forgot-password` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/auth/reset-password` | `auth.auth.reset-password` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/auth/accept-invite` | `auth.auth.accept-invite` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/auth/login` | `auth.auth.login` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/auth/login-step-up/issue` | `auth.auth.login-step-up.issue` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/auth/login-step-up/verify` | `auth.auth.login-step-up.verify` | public/session | public/session | public/session | middleware membership or public auth path |
| POST | `/api/v1/auth/workspaces` | `auth.auth.workspaces` | public/session | public/session | public/session | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers` | `brokers.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers` | `brokers.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers/resolve-identity` | `brokers.resolve-identity.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/archive` | `brokers.broker_id/archive.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/unarchive` | `brokers.broker_id/unarchive.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers/{broker_id}/workspace` | `brokers.broker_id/workspace.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers/{broker_id}` | `brokers.broker_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/brokers/{broker_id}` | `brokers.broker_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| DELETE | `/api/v1/brokers/{broker_id}` | `brokers.broker_id.delete` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers/{broker_id}/contacts` | `brokers.broker_id/contacts.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/contacts` | `brokers.broker_id/contacts.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers/{broker_id}/contacts/{contact_id}` | `brokers.broker_id/contacts/contact_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/brokers/{broker_id}/contacts/{contact_id}` | `brokers.broker_id/contacts/contact_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/contacts/{contact_id}/archive` | `brokers.broker_id/contacts/contact_id/archive.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/contacts/{contact_id}/unarchive` | `brokers.broker_id/contacts/contact_id/unarchive.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers/{broker_id}/domains` | `brokers.broker_id/domains.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/domains` | `brokers.broker_id/domains.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers/{broker_id}/domains/{domain_id}` | `brokers.broker_id/domains/domain_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/brokers/{broker_id}/domains/{domain_id}` | `brokers.broker_id/domains/domain_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/domains/{domain_id}/archive` | `brokers.broker_id/domains/domain_id/archive.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/domains/{domain_id}/unarchive` | `brokers.broker_id/domains/domain_id/unarchive.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers/{broker_id}/aliases` | `brokers.broker_id/aliases.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/aliases` | `brokers.broker_id/aliases.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers/{broker_id}/aliases/{alias_id}` | `brokers.broker_id/aliases/alias_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/brokers/{broker_id}/aliases/{alias_id}` | `brokers.broker_id/aliases/alias_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/aliases/{alias_id}/archive` | `brokers.broker_id/aliases/alias_id/archive.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/aliases/{alias_id}/unarchive` | `brokers.broker_id/aliases/alias_id/unarchive.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers/{broker_id}/known-senders` | `brokers.broker_id/known-senders.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/known-senders` | `brokers.broker_id/known-senders.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/brokers/{broker_id}/known-senders/{known_sender_id}` | `brokers.broker_id/known-senders/known_sender_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/brokers/{broker_id}/known-senders/{known_sender_id}` | `brokers.broker_id/known-senders/known_sender_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/known-senders/{known_sender_id}/archive` | `brokers.broker_id/known-senders/known_sender_id/archive.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/brokers/{broker_id}/known-senders/{known_sender_id}/unarchive` | `brokers.broker_id/known-senders/known_sender_id/unarchive.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/customs-brokers/search` | `customs_brokers.search.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/customs-brokers` | `customs_brokers.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/customs-brokers` | `customs_brokers.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/customs-brokers/{broker_id}` | `customs_brokers.broker_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/customs-brokers/{broker_id}` | `customs_brokers.broker_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| DELETE | `/api/v1/customs-brokers/{broker_id}` | `customs_brokers.broker_id.delete` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/customs-brokers/{broker_id}/contacts` | `customs_brokers.broker_id/contacts.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/customs-brokers/{broker_id}/contacts` | `customs_brokers.broker_id/contacts.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/customs-brokers/{broker_id}/contacts/{contact_id}` | `customs_brokers.broker_id/contacts/contact_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/customs-brokers/{broker_id}/contacts/{contact_id}` | `customs_brokers.broker_id/contacts/contact_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| DELETE | `/api/v1/customs-brokers/{broker_id}/contacts/{contact_id}` | `customs_brokers.broker_id/contacts/contact_id.delete` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/loads` | `loads.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/loads` | `loads.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/loads/parse-document` | `loads.documents.parse` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/loads/{load_id}` | `loads.load_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/loads/{load_id}` | `loads.load_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/loads/{load_id}/confirm-document-snapshot` | `loads.documents.confirm` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/loads/{load_id}/mark-ready` | `loads.mark_ready` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/loads/{load_id}/custody` | `loads.custody.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/loads/{load_id}/custody-events` | `loads.custody.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/loads/{load_id}/notes` | `loads.load_id/notes.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/loads/{load_id}/notes` | `loads.notes.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| DELETE | `/api/v1/loads/{load_id}` | `loads.load_id.delete` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/terminals` | `terminals.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/terminals` | `terminals.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/terminals/{terminal_id}` | `terminals.terminal_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PUT | `/api/v1/terminals/{terminal_id}` | `terminals.terminal_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/terminals/{terminal_id}` | `terminals.terminal_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trips` | `trips.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trips/{trip_id}/cancel` | `trips.trip_id/cancel.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trips/{trip_id}/complete` | `trips.trip_id/complete.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trips/{trip_id}/loads` | `trips.trip_id/loads.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/remove` | `trips.trip_id/loads/load_id/remove.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/activate` | `trips.trip_id/loads/load_id/activate.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/complete` | `trips.trip_id/loads/load_id/complete.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/accept-custody` | `trips.trip_id/loads/load_id/accept-custody.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/yard-handoff` | `trips.trip_id/loads/load_id/yard-handoff.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trips/{trip_id}/loads/{load_id}/take-custody` | `trips.trip_id/loads/load_id/take-custody.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/trips` | `trips.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/trips/{trip_id}` | `trips.trip_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PUT | `/api/v1/trips/{trip_id}/assignment` | `trips.trip_id/assignment.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PUT | `/api/v1/trips/{trip_id}/schedule` | `trips.trip_id/schedule.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trips/{trip_id}/execution-signal` | `trips.trip_id/execution-signal.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/load-lab/openai-smoke` | `load_lab.openai-smoke.create` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/load-lab/runs/upload` | `load_lab.runs/upload.create` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/load-lab/runs` | `load_lab.runs.view` | deny | deny | allow | JWT/cookie → get_current_user |
| DELETE | `/api/v1/load-lab/runs` | `load_lab.runs.delete` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/load-lab/runs/{run_id}` | `load_lab.runs/run_id.view` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/load-lab/runs/{run_id}/semantic-extract` | `load_lab.runs/run_id/semantic-extract.create` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/load-lab/runs/{run_id}/field-learning-events` | `load_lab.runs/run_id/field-learning-events.view` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/load-lab/runs/{run_id}/field-learning-events` | `load_lab.runs/run_id/field-learning-events.create` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/load-lab/runs/{run_id}/lab-review` | `load_lab.runs/run_id/lab-review.create` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/audit-events/by-entity` | `audit.events.by-entity.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/dispatch/board` | `dispatch.board.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trucks` | `trucks.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/trucks` | `trucks.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/trucks/{truck_id}/suggested-trailer` | `trucks.truck_id/suggested-trailer.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/trucks/{truck_id}` | `trucks.truck_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/trucks/{truck_id}` | `trucks.truck_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/trailers` | `trailers.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/trailers` | `trailers.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/trailers/{trailer_id}` | `trailers.trailer_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/trailers/{trailer_id}` | `trailers.trailer_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/dashboard/summary` | `dashboard.summary.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/company-profile` | `tenant.admin.company-profile.view` | deny | deny | allow | JWT/cookie → get_current_user |
| PATCH | `/api/v1/admin/person-setup-ui-mode` | `tenant.admin.person-setup-ui-mode.update` | deny | deny | allow | JWT/cookie → get_current_user |
| PATCH | `/api/v1/admin/doc-request-link-expiry` | `tenant.admin.doc-request-link-expiry.update` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/users` | `tenant.admin.users.view` | allow* | allow* | allow* (*no admin gate on handler) | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/users/{user_id}/sign-in-security` | `tenant.admin.users.sign-in-security.view` | allow* | allow* | allow* (*no admin gate on handler) | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/users/{user_id}/unlock-sign-in` | `tenant.admin.users.unlock-sign-in.create` | deny | allow | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/users/invite` | `tenant.admin.users.invite.create` | deny | allow | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/users/{user_id}/suspend` | `tenant.admin.users.suspend.create` | deny | allow | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/users/{user_id}/reactivate` | `tenant.admin.users.reactivate.create` | deny | allow | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/users/{user_id}/resend-invite` | `tenant.admin.users.resend-invite.create` | deny | allow | allow | JWT/cookie → get_current_user |
| DELETE | `/api/v1/admin/users/{user_id}` | `tenant.admin.users.delete` | deny | allow | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/broker-intake-settings` | `tenant.admin.broker-intake-settings.view` | deny | deny | allow | JWT/cookie → get_current_user |
| PATCH | `/api/v1/admin/broker-intake-settings` | `tenant.admin.broker-intake-settings.update` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/dispatch-numbering` | `tenant.admin.dispatch-numbering.view` | deny | deny | allow | JWT/cookie → get_current_user |
| PUT | `/api/v1/admin/dispatch-numbering` | `tenant.admin.dispatch-numbering.update` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/email-config/gmail/authorize` | `tenant.admin.email-config.authorize.view` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/email-config/gmail/ingestion-health` | `tenant.admin.email-config.ingestion-health.view` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/email-config/gmail/callback` | `tenant.admin.email-config.callback.view` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/email-config/microsoft/oauth-status` | `tenant.admin.email-config.oauth-status.view` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/email-config/microsoft/authorize` | `tenant.admin.email-config.authorize.view` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/email-config/microsoft/callback` | `tenant.admin.email-config.callback.view` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/email-config/microsoft/renew-subscription` | `tenant.admin.email-config.renew-subscription.create` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/email-config/microsoft/sync-now` | `tenant.admin.email-config.sync-now.create` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/email-config/primary/disconnect` | `tenant.admin.email-config.disconnect.create` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/admin/email-config/primary` | `tenant.admin.email-config.primary.view` | deny | deny | allow | JWT/cookie → get_current_user |
| PUT | `/api/v1/admin/email-config/primary` | `tenant.admin.email-config.primary.update` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/email-config/primary/test` | `tenant.admin.email-config.test.create` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/email-config/primary/test-inbound` | `tenant.admin.email-config.test-inbound.create` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/email-config/primary/test-outbound` | `tenant.admin.email-config.test-outbound.create` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/email-config/other/sync-now` | `tenant.admin.email-config.sync-now.create` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/email-config/gmail/register-watch` | `tenant.admin.email-config.register-watch.create` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/email-config/gmail/renew-watch` | `tenant.admin.email-config.renew-watch.create` | deny | deny | allow | JWT/cookie → get_current_user |
| POST | `/api/v1/admin/email-config/gmail/sync-now` | `tenant.admin.email-config.sync-now.create` | deny | deny | allow | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/providers` | `fuel.providers.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/providers/{provider_code}` | `fuel.providers/provider_code.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/provider-connections` | `fuel.provider-connections.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/provider-connections` | `fuel.provider-connections.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/provider-connections/{connection_id}` | `fuel.provider-connections/connection_id.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| PUT | `/api/v1/fuel/provider-connections/{connection_id}` | `fuel.provider-connections/connection_id.update` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/provider-connections/{connection_id}/test` | `fuel.provider-connections/connection_id/test.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/provider-connections/{connection_id}/sync` | `fuel.provider-connections/connection_id/sync.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/dashboard/stats` | `fuel.dashboard/stats.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/processed` | `fuel.processed.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/processed/{batch_id}` | `fuel.processed/batch_id.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/review/queue` | `fuel.review/queue.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/review/batches/{batch_id}` | `fuel.review/batches/batch_id.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/review/batches/{batch_id}/document` | `fuel.review/batches/batch_id/document.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/review/batches/{batch_id}/start` | `fuel.review/batches/batch_id/start.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/review/batches/{batch_id}/rows/{entity_type}/{entity_id}/confirm` | `fuel.review/batches/batch_id/rows/entity_type/entity_id/confirm.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/review/batches/{batch_id}/process` | `fuel.review/batches/batch_id/process.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/reconciliation/batches/{batch_id}` | `fuel.reconciliation/batches/batch_id.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/reconciliation/batches/{batch_id}/run` | `fuel.reconciliation/batches/batch_id/run.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/bvd/imports` | `fuel.bvd/imports.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/bvd/imports` | `fuel.bvd/imports.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/bvd/history` | `fuel.bvd/history.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/completed-basic` | `fuel.bvd/imports/import_id/completed-basic.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/rows` | `fuel.bvd/imports/import_id/rows.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/source-reconciliation` | `fuel.bvd/imports/import_id/source-reconciliation.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/summary` | `fuel.bvd/imports/import_id/summary.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/bvd/imports/{import_id}/save-review` | `fuel.bvd/imports/import_id/save-review.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/bvd/imports/{import_id}/process` | `fuel.bvd/imports/import_id/process.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/bvd/imports/{import_id}/discard` | `fuel.bvd/imports/import_id/discard.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/charge-categories` | `fuel.charge-categories.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/canonical-transactions` | `fuel.bvd/imports/import_id/canonical-transactions.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/bvd/imports/{import_id}/classify-canonical` | `fuel.bvd/imports/import_id/classify-canonical.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/fuel/transactions/{transaction_id}/classification` | `fuel.transactions/transaction_id/classification.update` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/classification-summary` | `fuel.bvd/imports/import_id/classification-summary.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/classification-unresolved-groups` | `fuel.bvd/imports/import_id/classification-unresolved-groups.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/bvd/imports/{import_id}/classification-reason-group` | `fuel.bvd/imports/import_id/classification-reason-group.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/classification-audit` | `fuel.bvd/imports/import_id/classification-audit.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/nationwide/history` | `fuel.nationwide/history.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/nationwide/imports/{import_id}/completed-basic` | `fuel.nationwide/imports/import_id/completed-basic.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/nationwide/imports` | `fuel.nationwide/imports.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/nationwide/imports/{import_id}/rows` | `fuel.nationwide/imports/import_id/rows.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/nationwide/imports/{import_id}/source-reconciliation` | `fuel.nationwide/imports/import_id/source-reconciliation.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/nationwide/imports/{import_id}/summary` | `fuel.nationwide/imports/import_id/summary.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/nationwide/imports/{import_id}/save-review` | `fuel.nationwide/imports/import_id/save-review.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/nationwide/imports/{import_id}/process` | `fuel.nationwide/imports/import_id/process.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/nationwide/imports/{import_id}/discard` | `fuel.nationwide/imports/import_id/discard.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/nationwide/imports/{import_id}/document` | `fuel.nationwide/imports/import_id/document.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/manual-entry/stages` | `fuel.manual-entry/stages.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/manual-entry/stages/receipt` | `fuel.manual-entry/stages/receipt.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/manual-entry/stages/{stage_id}` | `fuel.manual-entry/stages/stage_id.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/fuel/manual-entry/stages/{stage_id}` | `fuel.manual-entry/stages/stage_id.update` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/manual-entry/stages/{stage_id}/validate` | `fuel.manual-entry/stages/stage_id/validate.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/manual-entry/stages/{stage_id}/process` | `fuel.manual-entry/stages/stage_id/process.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| POST | `/api/v1/fuel/manual-entry/stages/{stage_id}/discard` | `fuel.manual-entry/stages/stage_id/discard.create` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/fuel/bvd/imports/{import_id}/document` | `fuel.bvd/imports/import_id/document.view` | deny | deny | allow (current fuel map) | JWT/cookie → get_current_user |
| GET | `/api/v1/tolls/providers` | `tolls.providers.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/tolls/files/upload` | `tolls.files/upload.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/tolls/files/csv` | `tolls.files/csv.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/tolls/files` | `tolls.files.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/tolls/files/{batch_id}` | `tolls.files/batch_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/tolls/files/pdf` | `tolls.files/pdf.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/tolls/pdf-reviews` | `tolls.pdf-reviews.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/tolls/pdf-reviews/{batch_id}` | `tolls.pdf-reviews/batch_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/tolls/pdf-reviews/{batch_id}/rows/{row_id}` | `tolls.pdf-reviews/batch_id/rows/row_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/tolls/pdf-reviews/{batch_id}/process` | `tolls.pdf-reviews/batch_id/process.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/tolls/manual-entry/stages` | `tolls.manual-entry/stages.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/tolls/manual-entry/stages` | `tolls.manual-entry/stages.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/tolls/manual-entry/stages/{stage_id}` | `tolls.manual-entry/stages/stage_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| PATCH | `/api/v1/tolls/manual-entry/stages/{stage_id}` | `tolls.manual-entry/stages/stage_id.update` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/tolls/manual-entry/stages/{stage_id}/validate` | `tolls.manual-entry/stages/stage_id/validate.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/tolls/manual-entry/stages/{stage_id}/discard` | `tolls.manual-entry/stages/stage_id/discard.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/tolls/manual-entry/stages/{stage_id}/process` | `tolls.manual-entry/stages/stage_id/process.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/gmail/pull-delta` | `email.threads.gmail/pull-delta.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/email-threads` | `email.threads.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/create-draft-load` | `email.threads.thread_id/create-draft-load.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/link-load` | `email.threads.thread_id/link-load.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/email-threads/{thread_id}` | `email.threads.thread_id.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/email-threads/{thread_id}/intake-qr-extractions` | `email.threads.thread_id/intake-qr-extractions.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/email-threads/{thread_id}/messages` | `email.threads.thread_id/messages.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/recompute-intake` | `email.threads.thread_id/recompute-intake.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/upload-pdf` | `email.threads.thread_id/upload-pdf.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/disregard` | `email.threads.thread_id/disregard.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| GET | `/api/v1/email-threads/{thread_id}/intake-review` | `email.threads.thread_id/intake-review.view` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/claim` | `email.threads.thread_id/intake-review/claim.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/resolve` | `email.threads.thread_id/intake-review/resolve.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/dismiss` | `email.threads.thread_id/intake-review/dismiss.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/duplicate/link-prior` | `email.threads.thread_id/intake-review/duplicate/link-prior.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/duplicate/confirm` | `email.threads.thread_id/intake-review/duplicate/confirm.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/duplicate/dismiss-false-positive` | `email.threads.thread_id/intake-review/duplicate/dismiss-false-positive.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/email-threads/{thread_id}/intake-review/reopen` | `email.threads.thread_id/intake-review/reopen.create` | allow (current) | allow (current) | allow (current) | JWT/cookie → get_current_user |
| POST | `/api/v1/webhooks/gmail/pubsub` | `webhooks.ingest` | n/a | n/a | n/a (service) | OIDC bearer and/or push token |
| GET | `/api/v1/webhooks/microsoft-graph` | `webhooks.ingest` | n/a | n/a | n/a (service) | clientState HMAC (no user JWT) |
| POST | `/api/v1/webhooks/microsoft-graph` | `webhooks.ingest` | n/a | n/a | n/a (service) | clientState HMAC (no user JWT) |
| GET | `/dashboard` | `NEEDS_APPROVAL.unmapped` | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED | none |
| GET | `/` | `NEEDS_APPROVAL.unmapped` | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED | none |
| GET | `/healthz` | `NEEDS_APPROVAL.unmapped` | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED | none |
| GET | `/api/v1/healthz` | `NEEDS_APPROVAL.unmapped` | allow (current) | allow (current) | allow (current) | middleware membership or public auth path |

---

## E. Exceptions and non-user actors

| Flow | Mechanism | RBAC class |
|------|-----------|------------|
| Login / refresh / logout / password reset / accept-invite | Public auth paths + cookies (`app/routers/auth.py`, middleware `PUBLIC_AUTH_PATHS`) | Pre-membership / session |
| Create workspace | `get_current_platform_user` + no tenant (`middleware` `282-295`) | Platform user |
| Public signup / OTP | `/api/v1/public/*` (`public_signup.py`) | Unauthenticated + rate limits |
| Workspace intake | `/api/v1/public/workspace-intake` | Unauthenticated |
| Driver applicant links | `/api/v1/driver-onboarding/applicant/*` token in query/body | Invite token actor |
| Gmail Pub/Sub | `POST /api/v1/webhooks/gmail/pubsub` OIDC/token (`gmail_pubsub.py:28-59`) | Service |
| Microsoft Graph | `clientState` verification (`microsoft_graph_webhook.py:46-47`) | Service |
| Platform admin API | `X-Platform-Admin-Key` (`platform_tenants.py:29-46`) | Separate control plane |
| Dev tools | Password gate; only mounted in shortcut envs (`main.py:162-165`, `dev_tools.py`) | Dev-only; **no tenant RBAC** |
| Domain event dispatcher | In-process background (`main.py:109-113`) | Internal |

---

## F. Load integrity preservation requirements

Source: `docs/load_trip/MASTER.md` (I5 row ~64: hard DELETE unsafe — **NOT IMPLEMENTED**).

| Mutation entry (API) | Handler | Service / notes |
|------------------------|---------|-----------------|
| `POST /api/v1/loads` | `loads.py` create | Creates load |
| `PATCH /api/v1/loads/{id}` | `loads.py` | `loads_service.update_load` — concurrency + audit (`test_load_money_audit_atomicity_issue26.py`) |
| `POST .../confirm-document-snapshot` | `loads.py` | Document confirmation path |
| `POST .../mark-ready` | `loads.py` | Gated in service (`test_load_mark_ready_gate_issue3.py`) |
| `POST .../notes` | `loads.py` | Notes + audit |
| `DELETE .../loads/{id}` | `loads.py:243-253` | **`delete_load` hard DELETE** `app/services/loads.py:563-574` — conflicts with I5 policy intent |
| Trips / custody | `trips.py`, custody services | State machine tests (`test_custody_*`, `test_trip_*`) |
| Dispatch board read | `dispatch.py` | Legacy read model |

**Casbin rule:** Capabilities may **deny** mutations; they must **not** permit actions forbidden by load/trip state machines or frozen writers (`test_load_writer_freeze_issue0a.py`).

---

## G. Proposed Casbin model and code interfaces

### G.1 Files (V1, no DB policy)

| Artifact | Path | Purpose |
|----------|------|---------|
| Model | `app/authz/casbin/model.conf` | RBAC with domains: `r = sub, dom, obj, act` |
| Policy | `app/authz/casbin/policy.csv` | Static role→capability grants per tenant template |
| Capability registry | `app/authz/capabilities.py` | `Capability` enum + route map |
| Enforcer wrapper | `app/authz/enforcer.py` | `load_policy()`, `check(user, tenant_id, capability) -> bool` |
| FastAPI dep | `app/authz/deps.py` | `require_capability("loads.update")` |

### G.2 Suggested signatures

```python
# app/authz/service.py
async def authorize(current: CurrentUser, capability: str, *, db: AsyncSession) -> None: ...

# app/authz/deps.py
def require_capability(capability: str):
    async def _dep(user: CurrentUser = Depends(get_current_user), ...) -> CurrentUser: ...
```

### G.3 Dependency ordering

1. `TenantContextMiddleware` (tenant + membership)
2. `get_current_user` (identity + role)
3. `require_entitlement(feature)` (subscription)
4. `require_capability(...)` (Casbin)
5. Domain invariants (load state, custody, financial immutability)

### G.4 Role resolution

- **Subject:** `platform_user_id` + resolved `membership_role` + synthetic `access_level` (`READ_ONLY` vs `FULL_ACCESS`) **decoupled** from `TENANT_ADMIN`.
- **Domain:** `tenant_id` string.
- **Object:** capability string (e.g. `loads.delete`).
- **Action:** `allow` / deny default **deny**.

### G.5 Fuel mapping

Keep existing capability strings in `fuel_rbac.py`; policy grants:
- `tenant_admin` → all `fuel.*`
- `full_access` → operational subset (**NEEDS_APPROVAL** list)
- `read_only` → `fuel.review.view` only (**NEEDS_APPROVAL**)

### G.6 Fail-closed

- Policy load failure → HTTP 503 + `AUTHZ_POLICY_UNAVAILABLE`.
- Unknown capability in code → startup error (registry validation).
- Unknown role → deny.

---

## H. Existing and proposed test matrix

### H.1 Existing (discovered; not executed in this audit)

| Area | Tests |
|------|-------|
| Tenant admin gate | `tests/test_require_tenant_admin_roles.py` |
| Fuel RBAC map | `tests/test_fuel_segment_0a.py` (`fuel_capability_allowed`) |
| Cross-tenant JWT/host | `tests/test_cross_tenant_host_enforcement.py` |
| Tenant middleware | `tests/test_tenant_middleware_isolation_hardening.py`, `tests/test_tenant_auth_matrix.py` |
| Platform admin key | `tests/test_platform_admin_key_gate.py` |
| Login / step-up | `tests/test_login_hardening_smoke.py`, `tests/test_login_step_up_otp.py` |
| Load mark ready / freeze / delete behavior | `tests/test_load_mark_ready_gate_issue3.py`, `tests/test_load_writer_freeze_issue0a.py`, `tests/test_loads_v1.py` |
| Custody / trips | `tests/test_custody_*`, `tests/test_trip_*` |

### H.2 Missing (proposed)

| Scenario | Expect |
|----------|--------|
| `TENANT_MEMBER` PATCH `/api/v1/loads/{id}` | 403 once `loads.update` denied for READ_ONLY |
| Operational FULL_ACCESS (new role) vs `TENANT_ADMIN` | Admin routes denied for ops role |
| READ_ONLY GET admin company profile | 403 |
| READ_ONLY GET `/api/v1/admin/users` | **NEEDS_APPROVAL** (today 200) |
| Policy file missing at startup | 503 on guarded routes |
| Unknown capability in `require_capability` | App fails startup |
| Frontend-only admin guard bypass | Direct API call blocked |
| Wrong tenant host + valid JWT | 403 (existing — keep) |
| Inactive subscription + payroll route | 403 entitlement |
| Applicant token expired | 401/403 |
| `DELETE /api/v1/loads/{id}` for READ_ONLY | 403; domain may also block per I5 |

---

## I. Risk register and unresolved decisions

### Confirmed findings

| ID | Sev | Evidence | Endpoints / impact | Recommendation |
|----|-----|----------|-------------------|----------------|
| R1 | **CRITICAL** | No role check on operational routers; only `get_current_user` e.g. `app/routers/loads.py:130-176`, `trips.py`, `tolls.py` | READ_ONLY users can mutate loads, trips, tolls, brokers, fleet | Introduce `require_capability` on all mutations; deny READ_ONLY by policy |
| R2 | **CRITICAL** | `delete_load` SQL DELETE `app/services/loads.py:566-573`; route `loads.py:243-253` | Hard delete load rows; conflicts with MASTER I5 | Domain policy first: block/replace with soft-cancel; then `loads.delete` capability |
| R3 | **HIGH** | `list_tenant_users` no `is_tenant_admin` `tenant_admin.py:469-508` | Any member lists all workspace users (emails, access levels) | Require `tenant.admin.users.view` or admin gate; align with UI exception |
| R4 | **HIGH** | `access_level_to_role` maps FULL_ACCESS→`TENANT_ADMIN` `admin.py:22-26` | Invited “Full access” receives **admin role**, not operational-only | **NEEDS_APPROVAL:** split `TENANT_OPERATOR` vs admin roles |
| R5 | **HIGH** | Fuel capabilities require tenant admin `fuel_rbac.py:31-50` | Operational users cannot use Fuel even if entitled | Map capabilities per approved ops matrix |
| R6 | **MEDIUM** | `GET /api/v1/admin/users/{id}/sign-in-security` no `has_full_access` `tenant_admin.py:511-537` | READ_ONLY can view sign-in lock state for members | Restrict to `tenant.admin.security.view` |
| R7 | **MEDIUM** | Microsoft webhook: `clientState` only `microsoft_graph_webhook.py:46-47` | Forged notifications if secret weak | Rotate secrets; optional Graph validation **NEEDS_APPROVAL** |
| R8 | **LOW** | `DELETE /api/v1/drivers/{id}` no auth `drivers.py:244-249` | Returns 405 without tenant/auth | Add standard deps for consistency |
| R9 | **MEDIUM** | Payroll UI checks `TENANT_ADMIN` only; backend uses `require_tenant_admin` on subset | OWNER/ADMIN may differ between UI and API | Align UI with `isTenantAdmin` helper |

### Hypotheses (not confirmed)

- Applicant token replay window scope — **NOT_VERIFIED** without token implementation review.
- All `GET` email sync endpoints side-effect free — **NOT_VERIFIED** (some POST sync paths exist).

---

## J. Minimal phased implementation plan

| Phase | Work | Regression gates |
|-------|------|------------------|
| 0 | Capability registry + policy file + fail-closed loader | Unit tests for enforcer; startup validation |
| 1 | Admin + People + payroll mutations | `test_require_tenant_admin_roles.py`; new READ_ONLY deny tests |
| 2 | Loads/Trips/Dispatch mutations (preserve state machine) | `test_load_mark_ready_gate_issue3.py`, custody/trip suite |
| 3 | Fuel granular policy (replace admin-only map) | `test_fuel_segment_0a.py` extended |
| 4 | Frontend route guards aligned to capabilities | E2E smoke for READ_ONLY |
| 5 | Resolve I5 deletion policy before enabling `loads.delete` | MASTER owner sign-off |

---

## K. Coverage statistics


| Metric | Count | Rule |
|--------|------:|------|
| Total HTTP operations | 371 | FastAPI routes, methods except HEAD |
| Mapped to proposed capability | 360 | Heuristic prefix map |
| Unresolved capability name | 11 | `NEEDS_APPROVAL.unmapped` |
| API mutations | 215 | POST/PUT/PATCH/DELETE under `/api` |
| API mutations with JWT auth dep | 173 | `get_current_user` in tree |
| API mutations with explicit admin/fuel inline/router gate | 61 | AST + fuel deps (under-counts router-level `require_tenant_admin`) |
| API mutations without JWT (excl. public/auth/applicant/webhook) | 1 | `DELETE /api/v1/drivers/{driver_id}` (405) |

**Protected mutation (audit definition):** mutation that requires authentication **or** documented alternate auth (applicant/webhook/platform). **Unprotected** = none of the above.

---

## Decisions requiring owner approval

1. **NEEDS_APPROVAL:** Define operational **FULL_ACCESS** as distinct from `TENANT_ADMIN` / invite role mapping (`access_level_to_role`).
2. **NEEDS_APPROVAL:** Should READ_ONLY users access **`GET /api/v1/admin/users`** and sign-in security panel data?
3. **NEEDS_APPROVAL:** Target capability matrix for Fuel operational vs admin-only actions.
4. **NEEDS_APPROVAL:** I5 load deletion — soft-cancel vs hard delete; Casbin must follow domain decision (`docs/load_trip/MASTER.md`).
5. **NEEDS_APPROVAL:** Microsoft Graph webhook authentication hardening scope.
6. **NEEDS_APPROVAL:** Default deny for all tenant mutations except explicit READ_ONLY allow list (recommended).
