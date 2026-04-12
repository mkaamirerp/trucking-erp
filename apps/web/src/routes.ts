/**
 * Route constants. Single source of truth for app routing.
 * Operations = day-to-day execution. Admin = company setup/configuration.
 */

/** Operations workspace — dispatch, loads, review, payroll, etc. */
export const OPS = {
  DASHBOARD: "/dashboard",
  /** Email load — Gmail / thread queues, sync, ingestion (not the Load Intake verification module). */
  EMAIL_LOAD: "/inbox",
  /** Load Intake — verify broker docs, KPIs, draft loads from email queues. */
  INTAKE: "/intake",
  DRIVER_ONBOARDING_APPLICANT: "/driver-onboarding",
  DRIVER_ONBOARDING_REVIEW: "/operations/driver-onboarding-review",
  DRIVER_ONBOARDING_REVIEW_DETAIL: (id: number | string) => `/operations/driver-onboarding-review/${id}`,
  DISPATCH: "/dispatch",
  FLEET: "/fleet",
  /** Freight brokers (MC / intake identity), not customs brokers. */
  BROKERS: "/brokers",
  BROKER_DETAIL: (id: number | string) => `/brokers/${id}`,
  LOADS: "/loads",
  /** Manual load creation — canonical workspace in create mode; then continue at LOAD_DETAIL. */
  LOAD_NEW: "/loads/new",
  LOAD_DETAIL: (id: number | string) => `/loads/${id}`,
  /** Query param on `/loads/:id` — dispatch board opens workspace with assignment strip (unassigned only). */
  LOAD_DISPATCH_ASSIGN_QUERY: "dispatchAssign",
  /** Query param on `/loads/:id` for intake email side panel (thread id). */
  LOAD_INTAKE_THREAD_QUERY: "intakeThread",
  /** Load workspace with intake context (same page as LOAD_DETAIL, plus query). */
  LOAD_WORKSPACE_INTAKE: (loadId: number | string, emailThreadId: number | string) =>
    `/loads/${loadId}?intakeThread=${encodeURIComponent(String(emailThreadId))}`,
  PAY_RUNS: "/payroll/pay-runs",
  PAY_RUN_NEW: "/payroll/pay-runs/new",
  PAY_RUN_DETAIL: (id: number | string) => `/payroll/pay-runs/${id}`,
  PAY_PERIODS: "/payroll/pay-periods",
  DOCUMENTS: "/payroll/documents",
} as const;

/** Apex-only platform control plane (X-Platform-Admin-Key). */
export const PLATFORM = {
  HOME: "/platform",
  TENANTS: "/platform/tenants",
  TENANT_DETAIL: (id: number | string) => `/platform/tenants/${id}`,
  GLOBAL_BOOKING_BROKERS: "/platform/global-booking-brokers",
  LOGIN_FAILURES: "/platform/login-failures",
  TESTING_UNLOCK_LOGIN: "/platform/testing/unlock-login",
} as const;

/** Tenant Admin workspace — company profile, users, settings, etc. */
export const ADMIN = {
  ROOT: "/admin",
  COMPANY_PROFILE: "/admin/company-profile",
  USERS: "/admin/users",
  ROLES: "/admin/roles",
  PAYROLL: "/admin/payroll",
  DISPATCH_NUMBERING: "/admin/dispatch-numbering",
  BROKER_INTAKE: "/admin/broker-intake",
  SETTINGS_EMAIL: "/admin/settings/email",
  INTEGRATIONS_ELD: "/admin/integrations/eld",
  INTEGRATIONS_FUEL: "/admin/integrations/fuel",
  ONBOARDING: "/admin/onboarding",
  DOCUMENTS: "/admin/documents",
} as const;
