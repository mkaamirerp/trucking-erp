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
  DRIVER_ONBOARDING_REVIEW: "/operations/driver-onboarding-review",
  DRIVER_ONBOARDING_REVIEW_DETAIL: (id: number | string) => `/operations/driver-onboarding-review/${id}`,
  /** People — maintained person master (directory + core edit). */
  PEOPLE: "/operations/people",
  PEOPLE_DETAIL: (id: number | string) => `/operations/people/${id}`,
  DISPATCH: "/dispatch",
  /** Trip (operational container) — read-only shell; member loads link to /loads/:id. */
  TRIPS: "/trips",
  /** Trip Container = Dispatch Control Center — accordion operational home (first slice). */
  TRIP_CONTAINER: "/trips/container",
  TRIP_DETAIL: (id: number | string) => `/trips/${id}`,
  FUTURE_MOVEMENT_PLANS: "/dispatch/future-plans",
  FUTURE_MOVEMENT_PLAN_DETAIL: (id: number | string) => `/dispatch/future-plans/${id}`,
  FLEET: "/fleet",
  /** Freight brokers (MC / intake identity), not customs brokers. */
  BROKERS: "/brokers",
  BROKER_DETAIL: (id: number | string) => `/brokers/${id}`,
  LOADS: "/loads",
  /** Load Lab — isolated PDF extraction testing and audit (does not replace main load workspace). */
  LOAD_LAB: "/loads/lab",
  /** Manual load creation — canonical workspace in create mode; then continue at LOAD_DETAIL. */
  LOAD_NEW: "/loads/new",
  /** Pre-promotion commercial workspace (DW-1 draft). */
  LOAD_DRAFT: (draftId: string) => `/loads/draft/${draftId}`,
  LOAD_DETAIL: (id: number | string) => `/loads/${id}`,
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
  FUEL: "/fuel",
  FUEL_PROVIDERS: "/fuel/providers",
  FUEL_REVIEW: "/fuel/review",
  FUEL_HISTORY: "/fuel/history",
  FUEL_REVIEW_BATCH: (id: number | string) => `/fuel/review/${id}`,
  FUEL_BVD_UPLOAD: "/fuel/bvd/upload",
  FUEL_BVD_REVIEW: (importId: string) => `/fuel/bvd/${importId}/review`,
  FUEL_BVD_DETAIL: (importId: string) => `/fuel/bvd/${importId}/detail`,
  /** Toll FILE intake history/search (unmapped CSV rows). */
  TOLLS: "/tolls",
  /** Toll PDF review staging (not canonical transactions). */
  TOLLS_PDF_REVIEWS: "/tolls/pdf-reviews",
  /** Toll MANUAL review-stage drafts (not canonical transactions). */
  TOLLS_MANUAL_ENTRY: "/tolls/manual-entry",
} as const;

/**
 * React remount key for load workspace routes. Keeps one instance across /loads/new →
 * /loads/draft/:id (parse navigates mid-request) but remounts when opening /loads/:id.
 */
export function loadWorkspaceRemountKey(pathname: string): string {
  const pathOnly = pathname.split("?")[0] ?? pathname;
  if (pathOnly === OPS.LOAD_NEW || pathOnly.startsWith("/loads/draft/")) {
    return "load-workspace-pre-promote";
  }
  const detail = pathOnly.match(/^\/loads\/(\d+)(?:\/|$)/);
  if (detail) return `load-workspace-detail-${detail[1]}`;
  return pathname;
}

/** Apex-only platform control plane (X-Platform-Admin-Key). */
export const PLATFORM = {
  HOME: "/platform",
  TENANTS: "/platform/tenants",
  TENANT_DETAIL: (id: number | string) => `/platform/tenants/${id}`,
  GLOBAL_BOOKING_BROKERS: "/platform/global-booking-brokers",
  LOGIN_FAILURES: "/platform/login-failures",
  TESTING_UNLOCK_LOGIN: "/platform/testing/unlock-login",
} as const;

/** Current user — profile and preferences. */
export const USER = {
  PROFILE: "/profile",
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
