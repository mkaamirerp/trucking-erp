import { getTenantSlugFromHost } from "./tenant";
const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";
const DEFAULT_TENANT_ID = import.meta.env.VITE_TENANT_ID || "1";
const PUBLIC_API_BASE = import.meta.env.VITE_PUBLIC_API_BASE || "/api/v1/public";

function currentSlugFromPath(): string | null {
  if (typeof window === "undefined") return null;
  const slug = getTenantSlugFromHost();
  if (slug) return slug;
  // fallback to path-based for dev/local if needed
  const segments = window.location.pathname.split("/").filter(Boolean);
  if (!segments.length) return null;
  const candidate = segments[0];
  const reserved = new Set([
    "signup",
    "login",
    "forgot-password",
    "reset-password",
    "payroll",
    "drivers",
    "api",
    "dashboard",
    "company-setup",
    "account-setup",
    "driver-onboarding",
    "admin",
  ]);
  if (reserved.has(candidate)) return null;
  if (!/^[a-z0-9][a-z0-9-]{1,62}$/i.test(candidate)) return null;
  return candidate;
}

function withTenantHeaders(init?: RequestInit): RequestInit {
  const headers = new Headers(init?.headers as HeadersInit | undefined);
  if (!headers.has("X-Tenant-ID") && !headers.has("X-Tenant-Slug")) {
    const slug = currentSlugFromPath();
    if (slug) {
      headers.set("X-Tenant-Slug", slug);
    } else {
      headers.set("X-Tenant-ID", DEFAULT_TENANT_ID);
    }
  }
  return { ...init, headers, credentials: "include" };
}

export function fetchWithTenant(input: RequestInfo | URL, init?: RequestInit) {
  return fetch(input, withTenantHeaders(init));
}

export function fetchPublic(input: RequestInfo | URL, init?: RequestInit) {
  return fetch(input, { ...init, credentials: "include" });
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export async function getPayPeriods() {
  const res = await fetchWithTenant(`${API_BASE}/payroll/pay-periods`);
  return handle<PayPeriod[]>(res);
}

export async function getMe() {
  const res = await fetchWithTenant(`/api/v1/me`);
  return handle<Me>(res);
}

export async function createPayPeriod(payload: PayPeriodCreate) {
  const res = await fetchWithTenant(`${API_BASE}/payroll/pay-periods`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<PayPeriod>(res);
}

export async function closePayPeriod(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/payroll/pay-periods/${id}/close`, { method: "POST" });
  return handle<PayPeriod>(res);
}

export async function listPayRuns() {
  // NOTE: backend currently lacks a list endpoint; this will fail until implemented.
  const res = await fetchWithTenant(`${API_BASE}/payroll/pay-runs`);
  return handle<PayRunSummary[]>(res);
}

export async function createPayRun(payload: PayRunCreatePayload) {
  const res = await fetchWithTenant(`${API_BASE}/payroll/pay-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<PayRun>(res);
}

export async function generatePayRun(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/payroll/pay-runs/${id}/generate`, { method: "POST" });
  return handle<{ pay_run_id: number; item_count: number }>(res);
}

export async function finalizePayRun(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/payroll/pay-runs/${id}/finalize`, { method: "POST" });
  return handle<{ pay_run_id: number; status: string; totals_snapshot?: unknown }>(res);
}

export async function getPayRun(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/payroll/pay-runs/${id}`);
  return handle<PayRunDetail>(res);
}

export async function getPayRunPayees(runId: number) {
  const res = await fetchWithTenant(`${API_BASE}/payroll/pay-runs/${runId}/payees`);
  return handle<PayRunPayeeRow[]>(res);
}

export async function getPayRunItems(runId: number, payeeId?: number) {
  const url = new URL(`${API_BASE}/payroll/pay-runs/${runId}/items`, window.location.origin);
  if (payeeId) url.searchParams.set("payee_id", String(payeeId));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PayRunItem[]>(res);
}

export async function listDocuments() {
  const res = await fetchWithTenant(`${API_BASE}/payroll/documents`);
  return handle<PayDocument[]>(res);
}

// ---- Public signup ----
export async function checkSlugAvailability(slug: string) {
  const url = new URL(`${PUBLIC_API_BASE}/check-slug-availability`, window.location.origin);
  url.searchParams.set("slug", slug);
  const res = await fetchPublic(url.toString().replace(window.location.origin, ""));
  if (res.status === 400) {
    const text = await res.text();
    throw new Error(text || "Invalid slug");
  }
  return handle<SlugAvailabilityResponse>(res);
}

export async function signup(payload: SignupPayload) {
  // Send form payload with only key renames for backend: slug → workspace_slug, company_name → company_legal_name. Pass address through as the form sends it.
  const body = {
    workspace_slug: payload.slug,
    email: payload.email.trim(),
    password: payload.password,
    first_name: payload.first_name.trim(),
    last_name: payload.last_name.trim(),
    phone: payload.phone.trim(),
    company_legal_name: payload.company_name?.trim() ?? payload.slug,
    address: payload.address,
  };
  const res = await fetchPublic(`${PUBLIC_API_BASE}/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = "Signup failed";
    try {
      const json = text ? (JSON.parse(text) as { detail?: string | Array<{ msg?: string }> }) : null;
      if (json?.detail) {
        message = Array.isArray(json.detail)
          ? (json.detail as Array<{ msg?: string }>).map((d) => d?.msg ?? "").filter(Boolean).join(". ") || "Validation failed"
          : String(json.detail);
      }
    } catch {
      /* use default */
    }
    throw new Error(message);
  }
  return handle<SignupResponse>(res);
}

export async function verifyOtp(payload: VerifyOtpRequest) {
  const res = await fetchPublic(`${PUBLIC_API_BASE}/verify-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const raw = await handle<
    | VerifyOtpResponse
    | {
        verified?: boolean;
        message: string;
        requires_company_setup: boolean;
        workspace_url: string;
        tenant_id?: number;
        slug?: string;
      }
  >(res);
  const success = (raw as any).success ?? (raw as any).verified ?? false;
  return {
    success: Boolean(success),
    message: raw.message,
    requires_company_setup: raw.requires_company_setup,
    workspace_url: raw.workspace_url,
    company_setup_url: (raw as any).company_setup_url ?? raw.workspace_url,
    dashboard_url: (raw as any).dashboard_url,
    tenant_id: (raw as any).tenant_id,
    slug: (raw as any).slug,
  } as VerifyOtpResponse;
}

export async function resendOtp(payload: { email: string; attempt_id?: string; slug?: string }) {
  const res = await fetchPublic(`${PUBLIC_API_BASE}/resend-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: payload.email }),
  });
  return handle<{ ok: boolean; message: string; debug_otp?: string | null }>(res);
}

export async function getSignupStatus(_attemptId: string) {
  const res = await fetchPublic(`${PUBLIC_API_BASE}/signup-status?attempt_id=${encodeURIComponent(_attemptId)}`);
  if (res.status === 404) return null;
  return handle<{ state?: string; db_status?: string; slug?: string; setup_url?: string }>(res);
}

export async function resumeSignup(payload: { email: string; slug: string }) {
  const res = await fetchPublic(`${PUBLIC_API_BASE}/resume-signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<{
    attempt_id?: string;
    slug?: string;
    first_name?: string;
    last_name?: string;
    company_name?: string;
    phone?: string;
    country?: string;
    plan?: string;
    reservation_expires_at?: string;
    state?: string;
  }>(res);
}

export async function changeSignupSlug(payload: { attempt_id: string; new_slug: string }) {
  const res = await fetchPublic(`${PUBLIC_API_BASE}/change-signup-slug`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<{ slug?: string; reservation_expires_at?: string }>(res);
}

export async function retryProvisioning(payload: { attempt_id: string }) {
  const res = await fetchPublic(`${PUBLIC_API_BASE}/retry-provisioning`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<{ company_setup_url?: string }>(res);
}

export async function cancelSignup(payload: { attempt_id: string }) {
  const res = await fetchPublic(`${PUBLIC_API_BASE}/cancel-signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
}

export type SetupPrefillResponse = {
  prefill: {
    company_legal_name?: string;
    country?: string;
    owner_email?: string;
    address?: { street?: string; city?: string; region?: string; postal?: string; country?: string };
  };
  required_remaining_fields: string[];
  country?: string | null;
};

export async function getSetupPrefill() {
  const res = await fetchWithTenant(`${API_BASE}/public/company-setup/prefill`);
  return handle<SetupPrefillResponse>(res);
}

export async function companySetup(payload: CompanySetupRequest) {
  const res = await fetchWithTenant(`${API_BASE}/public/company-setup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<CompanySetupResponse>(res);
}

export type SetupTenantPayload = {
  legal_name?: string;
  address?: { street: string; city: string; region: string; postal: string; country: string };
  dot_number?: string;
  mc_number?: string;
  cvor_number?: string;
  hst_number?: string;
  operator_license?: string;
  country?: string;
  geo_country?: string;
  fleet_size?: number;
};

export async function setupTenant(payload: SetupTenantPayload) {
  const c = (payload.country || payload.address?.country || "US").substring(0, 2).toUpperCase();
  const req: CompanySetupRequest = {
    legal_name: payload.legal_name ?? "Company",
    address: payload.address ?? {
      street: "TBD",
      city: "TBD",
      region: "TBD",
      postal: "TBD",
      country: c as "US" | "CA",
    },
    usdot_number: payload.dot_number || undefined,
    mc_number: payload.mc_number || undefined,
    cvor_number: payload.cvor_number || undefined,
    operator_license: payload.operator_license || undefined,
    hst_number: payload.hst_number || undefined,
  };
  return companySetup(req);
}

export async function uploadW9(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetchWithTenant(`${API_BASE}/public/company-setup/w9-upload`, {
    method: "POST",
    body: form,
  });
  return handle<UploadedFileResponse>(res);
}

export async function refreshSession() {
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (res.status === 401) return false;
  if (!res.ok) return false;
  return true;
}

export type CompanyProfileFromMe = {
  legal_name: string;
  address: { street: string; city: string; region: string; postal: string; country: string };
};

export async function getAuthMe() {
  const res = await fetchWithTenant(`${API_BASE}/auth/me`);
  return handle<{
    user_id: number | string;
    email: string;
    first_name: string;
    last_name: string;
    tenant_id: number;
    tenant_slug: string;
    tenant_name?: string;
    role?: string | null;
    email_verified?: boolean;
    requires_account_setup?: boolean;
    account_setup_missing?: string[];
    country_code?: string | null;
    company_profile?: CompanyProfileFromMe | null;
  }>(res);
}

export async function logout() {
  const res = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Logout failed");
  }
  return true;
}

export async function login(payload: { email: string; password: string }) {
  const res = await fetchWithTenant(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = "Invalid email or password";
    try {
      const json = text ? (JSON.parse(text) as { detail?: string }) : null;
      if (json?.detail) message = json.detail;
    } catch {
      /* use default */
    }
    throw new Error(message);
  }
  return handle<{ ok: boolean; workspace_url?: string }>(res);
}

/** Request password reset email (no tenant required). */
export async function forgotPassword(payload: { email: string; reset_base_url?: string }) {
  const res = await fetchPublic(`${API_BASE}/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = "Something went wrong. Please try again.";
    try {
      const json = text ? (JSON.parse(text) as { detail?: string }) : null;
      if (json?.detail) {
        message = json.detail;
        if (res.status === 403 && (json.detail.toLowerCase().includes("tenant not found") || json.detail.includes("not found in registry"))) {
          message = "This workspace doesn't exist. Check the URL or use the link from your sign-up email.";
        }
      }
    } catch {
      /* use default */
    }
    throw new Error(message);
  }
  return handle<{ ok: boolean; message: string; sent?: boolean }>(res);
}

/** Set new password with token from reset email (no tenant required). */
export async function resetPassword(payload: { token: string; new_password: string }) {
  const res = await fetchPublic(`${API_BASE}/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = "Invalid or expired link. Please request a new password reset.";
    try {
      const json = text ? (JSON.parse(text) as { detail?: string }) : null;
      if (json?.detail) message = json.detail;
    } catch {
      /* use default */
    }
    throw new Error(message);
  }
  return handle<{ ok: boolean; message: string }>(res);
}

// ---- Loads, Brokers, Dashboard ----
export async function getDashboardSummary() {
  const res = await fetchWithTenant(`${API_BASE}/dashboard/summary`);
  return handle<DashboardSummary>(res);
}

export async function seedDemoData() {
  const res = await fetchWithTenant(`${API_BASE}/dashboard/seed-demo`, { method: "POST" });
  if (!res.ok) {
    const text = await res.text();
    let message = text || "Seed failed";
    try {
      const json = JSON.parse(text) as { detail?: string };
      if (json.detail) message = json.detail;
    } catch {
      /* use message as-is */
    }
    throw new Error(message);
  }
  return handle<{ ok?: boolean; message?: string }>(res);
}

export async function listLoads(params: {
  status?: string[];
  driver_id?: number;
  broker_id?: number;
  pickup_start?: string;
  pickup_end?: string;
  page?: number;
  size?: number;
} = {}) {
  const url = new URL(`${API_BASE}/loads`, window.location.origin);
  if (params.status) params.status.forEach((s) => url.searchParams.append("status", s));
  if (params.driver_id) url.searchParams.set("driver_id", String(params.driver_id));
  if (params.broker_id) url.searchParams.set("broker_id", String(params.broker_id));
  if (params.pickup_start) url.searchParams.set("pickup_start", params.pickup_start);
  if (params.pickup_end) url.searchParams.set("pickup_end", params.pickup_end);
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<Load>>(res);
}

export async function getLoad(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/loads/${id}`);
  return handle<Load>(res);
}

export async function listBrokers(params: { page?: number; size?: number } = {}) {
  const url = new URL(`${API_BASE}/brokers`, window.location.origin);
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<Broker>>(res);
}

export async function getDriverSummary(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/drivers/${id}/summary`);
  return handle<DriverSummary>(res);
}

export async function listDrivers(params: { limit?: number; offset?: number; include_inactive?: boolean } = {}) {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set("limit", String(params.limit));
  if (params.offset != null) sp.set("offset", String(params.offset));
  if (params.include_inactive != null) sp.set("include_inactive", String(params.include_inactive));
  const qs = sp.toString();
  const url = `${API_BASE}/drivers${qs ? `?${qs}` : ""}`;
  const res = await fetchWithTenant(url);
  return handle<Driver[]>(res);
}

export async function createDriverOnboardingSubmission(payload: DriverOnboardingSubmissionCreate) {
  const res = await fetchWithTenant(`${API_BASE}/driver-onboarding/submissions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<DriverOnboardingCreateResponse>(res);
}

export async function getMyDriverOnboardingSubmission() {
  const res = await fetchWithTenant(`${API_BASE}/driver-onboarding/submissions/me`);
  return handle<DriverOnboardingSubmission | null>(res);
}

export async function listDriverOnboardingSubmissions(params: {
  status?: string;
  limit?: number;
  offset?: number;
} = {}) {
  const url = new URL(`${API_BASE}/driver-onboarding/submissions`, window.location.origin);
  if (params.status) url.searchParams.set("status", params.status);
  if (params.limit) url.searchParams.set("limit", String(params.limit));
  if (params.offset) url.searchParams.set("offset", String(params.offset));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<DriverOnboardingSubmission[]>(res);
}

export async function getDriverOnboardingSubmission(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/driver-onboarding/submissions/${id}`);
  return handle<DriverOnboardingSubmission>(res);
}

export async function submitDriverOnboardingSubmission(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/driver-onboarding/submissions/${id}/submit`, { method: "POST" });
  return handle<DriverOnboardingSubmission>(res);
}

export async function approveDriverOnboardingSubmission(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/driver-onboarding/submissions/${id}/approve`, { method: "POST" });
  return handle<DriverOnboardingApproveResponse>(res);
}

export async function rejectDriverOnboardingSubmission(id: number, rejection_reason: string) {
  const res = await fetchWithTenant(`${API_BASE}/driver-onboarding/submissions/${id}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rejection_reason }),
  });
  return handle<DriverOnboardingSubmission>(res);
}

// ---- Types ----
export type PayPeriod = {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  status: string;
  created_at: string;
  updated_at: string;
  closed_at?: string | null;
};

export type PayPeriodCreate = {
  name: string;
  start_date: string;
  end_date: string;
};

export type PayRunItem = {
  id: number;
  payee_id: number;
  source_type: string;
  description: string;
  amount_signed: number;
  currency: string;
  quantity?: number | null;
  unit_rate?: number | null;
  charge_category_id?: number | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
};

export type PayRun = {
  id: number;
  pay_period_id: number;
  pay_document_type: string;
  worker_type_snapshot: string;
  base_currency_snapshot: string;
  pay_date: string;
  status: string;
  payout_status: string;
  calculation_snapshot_json?: Record<string, unknown> | null;
  totals_snapshot?: Record<string, unknown> | null;
  finalized_at?: string | null;
  finalized_by?: number | null;
  created_at: string;
  updated_at: string;
  items?: PayRunItem[];
};

export type PayRunSummary = PayRun;

export type PayRunDetail = Omit<PayRun, "items">;

export type PayRunPayeeRow = {
  payee_id: number;
  display_name: string;
  net_amount: number;
  flags: {
    negative_net: boolean;
    has_overrides: boolean;
    missing_payout_preference: boolean;
  };
};

export type PayRunCreatePayload = {
  pay_period_id: number;
  pay_document_type: string;
  worker_type_snapshot: string;
  pay_date: string;
  base_currency_snapshot: string;
};

export type PayDocument = {
  id: number;
  tenant_id: number;
  pay_run_id: number;
  payee_id: number;
  document_type: string;
  file_storage_key: string;
  version: number;
  sha256?: string | null;
  generated_at: string;
  generated_by?: number | null;
};

export type Me = {
  user_id: number | null;
  tenant_id: number;
  roles: string[];
  requires_account_setup?: boolean;
  account_setup_missing?: string[];
  country_code?: string | null;
  tenant_slug?: string | null;
};

export type SlugAvailabilityResponse = {
  available: boolean;
  slug: string;
  suggestions?: string[] | null;
};

export type SignupAddress = {
  street: string;
  city: string;
  region: string;
  postal: string;
  country: string;
};

export type SignupPayload = {
  first_name: string;
  last_name: string;
  email: string;
  confirm_email: string;
  phone: string;
  company_name: string;
  slug: string;
  address: SignupAddress;
  password: string;
  confirm_password: string;
  plan: string;
  accept_terms: boolean;
  is_owner_or_admin: boolean;
};

export type SignupResponse = {
  success: boolean;
  tenant_slug?: string;
  redirect_url?: string;
  message?: string;
  user_id?: number;
  tenant_id?: number;
  email?: string;
  debug_otp?: string | null;
};

export type VerifyOtpRequest = {
  email: string;
  otp: string;
};

export type VerifyOtpResponse = {
  success: boolean;
  message: string;
  requires_company_setup: boolean;
  workspace_url: string;
  tenant_id?: number | null;
  slug?: string | null;
  verified?: boolean;
};

export type CompanySetupRequest = {
  legal_name: string;
  address: {
    street: string;
    city: string;
    region: string;
    postal: string;
    country: string;
  };
  usdot_number?: string;
  mc_number?: string;
  cvor_number?: string;
  operator_license?: string;
  hst_number?: string;
  w9_storage_key?: string;
  w9_original_filename?: string;
};

export type CompanySetupResponse = {
  tenant_status: string;
  db_status?: string | null;
  dashboard_url: string;
};

export type UploadedFileResponse = {
  storage_key: string;
  original_filename?: string | null;
  content_type?: string | null;
  file_size_bytes: number;
  sha256?: string;
};

export type PagedResponse<T> = {
  items: T[];
  page: number;
  size: number;
  total: number;
};

export type DashboardSummary = {
  active_loads: number;
  in_transit: number;
  delayed: number;
  delivered_today: number;
  miles_this_week: number;
  revenue_this_week: number;
  drivers_active: number;
  drivers_total: number;
  drivers?: Driver[];
};

export type Broker = {
  id: number;
  name: string;
  mc_number?: string | null;
  phone?: string | null;
  email?: string | null;
  notes?: string | null;
};

export type Load = {
  id: number;
  load_number: string;
  broker_id?: number | null;
  driver_id?: number | null;
  pickup_date?: string | null;
  delivery_date?: string | null;
  pickup_location?: string | null;
  delivery_location?: string | null;
  rate?: number | null;
  miles?: number | null;
  status: string;
  broker?: Broker | null;
  driver?: { id: number; first_name: string; last_name: string } | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DriverSummary = {
  driver: {
    id: number;
    first_name: string;
    last_name: string;
    phone?: string | null;
    email?: string | null;
    license_number?: string | null;
    license_expiry?: string | null;
    notes?: string | null;
    is_active: boolean;
  };
  stats: {
    miles_this_week: number;
    revenue_this_week: number;
    active_loads: number;
  };
  upcoming_loads: Array<{
    id: number;
    load_number: string;
    pickup_date?: string | null;
    delivery_date?: string | null;
    pickup_location?: string | null;
    delivery_location?: string | null;
    status: string;
  }>;
};

export type Driver = {
  id: number;
  first_name: string;
  last_name: string;
  phone?: string | null;
  email?: string | null;
  is_active: boolean;
};

export type DriverOnboardingSubmission = {
  id: number;
  tenant_id: number;
  created_by_user_id: number;
  status: "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED";
  source: string;
  submitted_at?: string | null;
  reviewed_at?: string | null;
  reviewed_by_user_id?: number | null;
  rejection_reason?: string | null;
  first_name: string;
  last_name: string;
  phone?: string | null;
  email?: string | null;
  address_street?: string | null;
  address_city?: string | null;
  address_region?: string | null;
  address_postal?: string | null;
  address_country?: string | null;
  driver_license_number?: string | null;
  license_region?: string | null;
  license_expiry?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
};

export type DriverOnboardingSubmissionCreate = {
  first_name: string;
  last_name: string;
  phone?: string;
  email?: string;
  address_street?: string;
  address_city?: string;
  address_region?: string;
  address_postal?: string;
  address_country?: string;
  driver_license_number?: string;
  license_region?: string;
  license_expiry?: string;
  notes?: string;
  submit?: boolean;
};

export type DriverOnboardingCreateResponse = {
  submission: DriverOnboardingSubmission;
  missing_required_documents: string[];
};

export type DriverOnboardingApproveResponse = {
  submission: DriverOnboardingSubmission;
  driver: Driver;
};
