/**
 * Route constants. Single source of truth for app routing.
 * Operations = day-to-day execution. Admin = company setup/configuration.
 */

/** Operations workspace — dispatch, loads, review, payroll, etc. */
export const OPS = {
  DASHBOARD: "/dashboard",
  INBOX: "/inbox",
  DRIVER_ONBOARDING_APPLICANT: "/driver-onboarding",
  DRIVER_ONBOARDING_REVIEW: "/operations/driver-onboarding-review",
  DRIVER_ONBOARDING_REVIEW_DETAIL: (id: number | string) => `/operations/driver-onboarding-review/${id}`,
  DISPATCH: "/dispatch",
  FLEET: "/fleet",
  LOADS: "/loads",
  /** Create a new load draft and open its detail page (manual entry from intake, etc.). */
  LOAD_NEW: "/loads/new",
  LOAD_DETAIL: (id: number | string) => `/loads/${id}`,
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
  SETTINGS_EMAIL: "/admin/settings/email",
  INTEGRATIONS_ELD: "/admin/integrations/eld",
  INTEGRATIONS_FUEL: "/admin/integrations/fuel",
  ONBOARDING: "/admin/onboarding",
  DOCUMENTS: "/admin/documents",
} as const;
