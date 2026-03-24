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
    "dispatch",
    "fleet",
    "loads",
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
    const err = new Error(text || res.statusText);
    (err as any).status = res.status;
    throw err;
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

export async function checkSignupEmailAvailability(email: string) {
  const url = new URL(`${PUBLIC_API_BASE}/check-signup-email`, window.location.origin);
  url.searchParams.set("email", email.trim());
  const res = await fetchPublic(url.toString().replace(window.location.origin, ""));
  if (res.status === 400) {
    const text = await res.text();
    throw new Error(text || "Invalid email");
  }
  return handle<SignupFieldAvailabilityResponse>(res);
}

export async function checkSignupPhoneAvailability(phone: string) {
  const url = new URL(`${PUBLIC_API_BASE}/check-signup-phone`, window.location.origin);
  url.searchParams.set("phone", phone);
  const res = await fetchPublic(url.toString().replace(window.location.origin, ""));
  if (res.status === 400) {
    const text = await res.text();
    throw new Error(text || "Invalid phone");
  }
  return handle<SignupFieldAvailabilityResponse>(res);
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
  company_phone?: string;
  company_email?: string;
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
    company_phone: payload.company_phone || undefined,
    company_email: payload.company_email || undefined,
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
  truck_id?: number;
  trailer_id?: number;
  pickup_start?: string;
  pickup_end?: string;
  search?: string;
  page?: number;
  size?: number;
} = {}) {
  const url = new URL(`${API_BASE}/loads`, window.location.origin);
  if (params.status) params.status.forEach((s) => url.searchParams.append("status", s));
  if (params.driver_id) url.searchParams.set("driver_id", String(params.driver_id));
  if (params.broker_id) url.searchParams.set("broker_id", String(params.broker_id));
  if (params.truck_id) url.searchParams.set("truck_id", String(params.truck_id));
  if (params.trailer_id) url.searchParams.set("trailer_id", String(params.trailer_id));
  if (params.pickup_start) url.searchParams.set("pickup_start", params.pickup_start);
  if (params.pickup_end) url.searchParams.set("pickup_end", params.pickup_end);
  if (params.search && params.search.trim()) url.searchParams.set("search", params.search.trim());
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<Load>>(res);
}

export async function getLoad(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/loads/${id}`);
  return handle<Load>(res);
}

export async function createLoad(payload: Partial<Load>) {
  const res = await fetchWithTenant(`${API_BASE}/loads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<Load>(res);
}

export async function updateLoad(id: number, payload: Partial<Load>) {
  const res = await fetchWithTenant(`${API_BASE}/loads/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<Load>(res);
}

export type DispatchBoard = Record<string, Load[]>;

export async function getDispatchBoard(search?: string) {
  const url = new URL(`${API_BASE}/dispatch/board`, window.location.origin);
  if (search) url.searchParams.set("search", search);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<DispatchBoard>(res);
}

export type LoadNote = {
  id: number;
  body: string;
  author_user_id?: string | null;
  created_at: string;
};

export async function getLoadNotes(loadId: number) {
  const res = await fetchWithTenant(`${API_BASE}/loads/${loadId}/notes`);
  return handle<LoadNote[]>(res);
}

export async function addLoadNote(loadId: number, body: string) {
  const res = await fetchWithTenant(`${API_BASE}/loads/${loadId}/notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  });
  return handle<LoadNote>(res);
}

export async function listBrokers(params: { page?: number; size?: number } = {}) {
  const url = new URL(`${API_BASE}/brokers`, window.location.origin);
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<Broker>>(res);
}

export type Truck = {
  id: number;
  unit_number: string;
  vin: string;
  year?: number | null;
  make?: string | null;
  model?: string | null;
  plate_number?: string | null;
  status?: string;
  ownership_type?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
};
export async function listTrucks(params: { page?: number; size?: number; status?: string[] } = {}) {
  const url = new URL(`${API_BASE}/trucks`, window.location.origin);
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  if (params.status) params.status.forEach((s) => url.searchParams.append("status", s));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<Truck>>(res);
}

export async function getTruck(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/trucks/${id}`);
  return handle<Truck>(res);
}

export type TruckCreatePayload = {
  unit_number: string;
  vin: string;
  year?: number | null;
  make?: string | null;
  model?: string | null;
  color?: string | null;
  plate_number?: string | null;
  plate_region?: string | null;
  ownership_type?: string;
  owner_person_id?: number | null;
  purchase_date?: string | null;
  purchase_price?: number | null;
  engine_make?: string | null;
  engine_model?: string | null;
  engine_serial?: string | null;
  horsepower?: number | null;
  fuel_type?: string | null;
  transmission?: string | null;
  num_axles?: number | null;
  gvwr_lbs?: number | null;
  odometer_at_purchase?: number | null;
  current_odometer?: number | null;
  odometer_last_updated?: string | null;
  insurance_carrier?: string | null;
  insurance_policy_number?: string | null;
  insurance_expiry?: string | null;
  status?: string;
  notes?: string | null;
  [key: string]: unknown;
};
export async function createTruck(payload: TruckCreatePayload) {
  const res = await fetchWithTenant(`${API_BASE}/trucks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<Truck>(res);
}

export type TruckUpdatePayload = Partial<TruckCreatePayload>;
export async function updateTruck(id: number, payload: TruckUpdatePayload) {
  const res = await fetchWithTenant(`${API_BASE}/trucks/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<Truck>(res);
}

export type Trailer = {
  id: number;
  unit_number: string;
  vin?: string | null;
  year?: number | null;
  make?: string | null;
  model?: string | null;
  trailer_type?: string | null;
  plate_number?: string | null;
  status?: string;
  ownership_type?: string;
  length_ft?: number | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
};
export async function listTrailers(params: { page?: number; size?: number; status?: string[] } = {}) {
  const url = new URL(`${API_BASE}/trailers`, window.location.origin);
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  if (params.status) params.status.forEach((s) => url.searchParams.append("status", s));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<Trailer>>(res);
}

export async function getTrailer(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/trailers/${id}`);
  return handle<Trailer>(res);
}

export type TrailerCreatePayload = {
  unit_number: string;
  vin?: string | null;
  year?: number | null;
  make?: string | null;
  model?: string | null;
  plate_number?: string | null;
  plate_region?: string | null;
  trailer_type?: string;
  length_ft?: number | null;
  num_axles?: number | null;
  gvwr_lbs?: number | null;
  door_type?: string | null;
  reefer_make?: string | null;
  reefer_model?: string | null;
  reefer_serial?: string | null;
  ownership_type?: string;
  owner_person_id?: number | null;
  purchase_date?: string | null;
  purchase_price?: number | null;
  insurance_carrier?: string | null;
  insurance_policy_number?: string | null;
  insurance_expiry?: string | null;
  status?: string;
  notes?: string | null;
  [key: string]: unknown;
};
export async function createTrailer(payload: TrailerCreatePayload) {
  const res = await fetchWithTenant(`${API_BASE}/trailers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<Trailer>(res);
}

export type TrailerUpdatePayload = Partial<TrailerCreatePayload>;
export async function updateTrailer(id: number, payload: TrailerUpdatePayload) {
  const res = await fetchWithTenant(`${API_BASE}/trailers/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<Trailer>(res);
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

/** Applicant (invite-link token) flow: no session required. */
export type PersonApplicationRejectRequest = {
  rejection_reason: string;
};

export type PersonApplicationListItem = {
  id: number;
  tenant_id: number;
  status: string;
  application_type?: string;
  requested_role_code?: string;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  submitted_at?: string | null;
  source?: string | null;
  created_at: string;
};

export type ApplicantApplication = {
  id: number;
  tenant_id: number;
  person_id?: number | null;
  status: string;
  source?: string | null;
  application_type?: string;
  requested_role_code?: string;
  reviewed_at?: string | null;
  reviewed_by_user_id?: number | null;
  approved_at?: string | null;
  approved_by_user_id?: number | null;
  rejection_reason?: string | null;
  first_name?: string | null;
  last_name?: string | null;
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
  submitted_at?: string | null;
  created_at: string;
  updated_at: string;
  intake_payload?: Record<string, unknown> | null;
};

/** Used by OnboardingApplicantPage (same shape as ApplicantApplication). */
export type PersonApplication = ApplicantApplication;

export type ApplicantApplicationUpdatePayload = {
  first_name?: string;
  last_name?: string;
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

export async function getApplicantApplication(token: string): Promise<ApplicantApplication> {
  const url = new URL(`${API_BASE}/driver-onboarding/applicant/application`, window.location.origin);
  url.searchParams.set("token", token);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<ApplicantApplication>(res);
}

export async function listPersonApplicationsForAdmin(params: {
  status?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<PersonApplicationListItem[]> {
  const url = new URL(`${API_BASE}/driver-onboarding/applications`, window.location.origin);
  if (params.status) url.searchParams.set("status", params.status);
  if (params.limit) url.searchParams.set("limit", String(params.limit));
  if (params.offset) url.searchParams.set("offset", String(params.offset));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PersonApplicationListItem[]>(res);
}

export async function getPersonApplicationForAdmin(id: number): Promise<ApplicantApplication> {
  const res = await fetchWithTenant(`${API_BASE}/driver-onboarding/applications/${id}`);
  return handle<ApplicantApplication>(res);
}

/** Fetch application file (DL or document) for admin review. Returns object URL for preview. */
export async function getAdminApplicationFileUrl(applicationId: number, fileId: string): Promise<string> {
  const url = new URL(`${API_BASE}/driver-onboarding/applications/${applicationId}/file`, window.location.origin);
  url.searchParams.set("file_id", fileId);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  if (!res.ok) throw new Error("File not found");
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function approvePersonApplicationForAdmin(id: number): Promise<ApplicantApplication> {
  const res = await fetchWithTenant(`${API_BASE}/driver-onboarding/applications/${id}/approve`, {
    method: "POST",
  });
  return handle<ApplicantApplication>(res);
}

export async function rejectPersonApplicationForAdmin(
  id: number,
  payload: PersonApplicationRejectRequest,
): Promise<ApplicantApplication> {
  const res = await fetchWithTenant(`${API_BASE}/driver-onboarding/applications/${id}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<ApplicantApplication>(res);
}

/** Get person application by invite token (used by OnboardingApplicantPage). */
export async function getPersonApplicationByOnboardingToken(token: string): Promise<PersonApplication> {
  return getApplicantApplication(token);
}

/** Get person application by id and token (token is enough; appId unused). */
export async function getPersonApplication(_appId: number, token: string): Promise<PersonApplication> {
  return getApplicantApplication(token);
}

export async function updateApplicantApplication(
  token: string,
  payload: ApplicantApplicationUpdatePayload
): Promise<ApplicantApplication> {
  const url = new URL(`${API_BASE}/driver-onboarding/applicant/application`, window.location.origin);
  url.searchParams.set("token", token);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<ApplicantApplication>(res);
}

/** Save intake payload (step progress); used by OnboardingApplicantPage. */
export async function savePersonApplicationIntake(params: {
  appId: number;
  onboardingToken: string;
  intakePayload: Record<string, unknown>;
}): Promise<PersonApplication> {
  const url = new URL(`${API_BASE}/driver-onboarding/applicant/application/intake`, window.location.origin);
  url.searchParams.set("token", params.onboardingToken);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ intake_payload: params.intakePayload, submit: false }),
  });
  return handle<PersonApplication>(res);
}

/** Submit application with final intake payload; used by OnboardingApplicantPage. */
export async function submitPersonApplication(params: {
  appId: number;
  onboardingToken: string;
  intakePayload: Record<string, unknown>;
}): Promise<PersonApplication> {
  const url = new URL(`${API_BASE}/driver-onboarding/applicant/application/intake`, window.location.origin);
  url.searchParams.set("token", params.onboardingToken);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ intake_payload: params.intakePayload, submit: true }),
  });
  return handle<PersonApplication>(res);
}

export async function resetPersonApplicationDraft(params: {
  appId: number;
  onboardingToken: string;
}): Promise<PersonApplication> {
  const url = new URL(`${API_BASE}/driver-onboarding/applicant/application/reset`, window.location.origin);
  url.searchParams.set("token", params.onboardingToken);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""), {
    method: "POST",
  });
  return handle<PersonApplication>(res);
}

/** Upload DL file (front or back) for applicant; returns updated application with intake_payload. */
export async function uploadPersonApplicationDlFile(params: {
  appId: number;
  onboardingToken: string;
  docType: string;
  file: File;
}): Promise<{ file_id?: string; intake_payload?: Record<string, unknown>; license_extract_status?: string; sanitized_file_id?: string }> {
  const url = new URL(`${API_BASE}/driver-onboarding/applicant/application/dl-upload`, window.location.origin);
  url.searchParams.set("token", params.onboardingToken);
  const form = new FormData();
  form.append("doc_type", params.docType);
  form.append("file", params.file);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""), {
    method: "POST",
    body: form,
  });
  const data = await handle<ApplicantApplication>(res);
  const fileMeta = (data.intake_payload as any)?.files?.[params.docType];
  const processedMeta = (data.intake_payload as any)?.files?.[`${params.docType}_PROCESSED`];
  const fileId = fileMeta?.file_id ?? fileMeta?.storage_key;
  const sanitizedFileId =
    fileMeta?.enh_file_id ??
    processedMeta?.enh_file_id ??
    processedMeta?.file_id ??
    processedMeta?.storage_key ??
    fileId;
  return {
    file_id: fileId,
    intake_payload: data.intake_payload as Record<string, unknown>,
    license_extract_status: (data.intake_payload as any)?.license_extract_status,
    sanitized_file_id: sanitizedFileId,
  };
}

/** Fetch applicant file (e.g. DL image) and return object URL for preview. */
export async function getPersonApplicationFileThumbnail(params: {
  appId: number;
  fileId: string;
  onboardingToken: string;
}): Promise<string> {
  const url = new URL(`${API_BASE}/driver-onboarding/applicant/application/file`, window.location.origin);
  url.searchParams.set("token", params.onboardingToken);
  url.searchParams.set("file_id", params.fileId);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  if (!res.ok) throw new Error("File not found");
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

/** Upload step-4 document (DOT medical, MVR, etc.) for applicant. Returns updated application. */
export async function uploadPersonApplicationDocument(params: {
  appId: number;
  onboardingToken: string;
  docType: string;
  file: File;
}): Promise<PersonApplication> {
  const url = new URL(`${API_BASE}/driver-onboarding/applicant/application/document-upload`, window.location.origin);
  url.searchParams.set("token", params.onboardingToken);
  const form = new FormData();
  form.append("doc_type", params.docType);
  form.append("file", params.file);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""), {
    method: "POST",
    body: form,
  });
  return handle<PersonApplication>(res);
}

/** Stub: not implemented. Used by DriverOnboardingPage. */
export async function uploadDriverLicense(
  _submissionId: number,
  _frontFile: File,
  _backFile: File | null
): Promise<unknown> {
  throw new Error("Driver license upload not implemented");
}

/** Stub: not implemented. Used by DriverOnboardingPage. */
export async function swapDriverLicenseFrontBack(_submissionId: number): Promise<unknown> {
  throw new Error("Swap driver license front/back not implemented");
}

/** Create onboarding invite link (admin). Returns link and optional email_sent/email_error. */
export type OnboardingInviteLinkRequest = {
  email?: string | null;
  phone?: string | null;
  application_type: string;
};
export type OnboardingInviteLinkResponse = {
  application_id: number;
  token: string;
  link: string;
  email_sent: boolean;
  email_error?: string | null;
};
/** Tenant admin: company profile. Includes completeness and fallback signals for document safety. */
export type CompanyProfile = {
  tenant_name: string;
  slug: string;
  timezone: string;
  base_currency: string;
  country_code: string | null;
  legal_name: string | null;
  street: string | null;
  city: string | null;
  region: string | null;
  postal: string | null;
  country: string | null;
  company_phone: string | null;
  company_email: string | null;
  usdot_number: string | null;
  mc_number: string | null;
  cvor_number: string | null;
  operator_license: string | null;
  hst_number: string | null;
  has_w9_file: boolean;
  setup_completed_at: string | null;
  has_business_address: boolean;
  has_company_phone: boolean;
  has_company_email: boolean;
  is_document_contact_complete: boolean;
  company_phone_is_fallback: boolean;
  company_email_is_fallback: boolean;
  address_is_fallback: boolean;
};

export async function getCompanyProfile(): Promise<CompanyProfile> {
  const res = await fetchWithTenant(`${API_BASE}/admin/company-profile`);
  return handle<CompanyProfile>(res);
}

// ---- Tenant admin: users (list, invite, suspend, reactivate, send-password-reset) ----

export type UserMember = {
  user_id: string;
  username: string;
  email: string;
  phone: string | null;
  access_level: string;  // READ_ONLY | FULL_ACCESS
  membership_status: string;
  joined_at: string;
};

export async function listTenantUsers(): Promise<UserMember[]> {
  const res = await fetchWithTenant(`${API_BASE}/admin/users`);
  return handle<UserMember[]>(res);
}

export type InviteUserPayload = {
  username: string;
  email: string;
  phone?: string | null;
  access_level?: string;  // READ_ONLY | FULL_ACCESS
};

export async function inviteTenantUser(payload: InviteUserPayload): Promise<{ ok: boolean; email: string; status: string; message: string }> {
  const res = await fetchWithTenant(`${API_BASE}/admin/users/invite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<{ ok: boolean; email: string; status: string; message: string }>(res);
}

export async function suspendTenantUser(userId: string): Promise<{ ok: boolean; status: string }> {
  const res = await fetchWithTenant(`${API_BASE}/admin/users/${encodeURIComponent(userId)}/suspend`, {
    method: "POST",
  });
  return handle<{ ok: boolean; status: string }>(res);
}

export async function reactivateTenantUser(userId: string): Promise<{ ok: boolean; status: string }> {
  const res = await fetchWithTenant(`${API_BASE}/admin/users/${encodeURIComponent(userId)}/reactivate`, {
    method: "POST",
  });
  return handle<{ ok: boolean; status: string }>(res);
}

// ---- Tenant admin: email config (primary mailbox) ----

export type EmailConfig = {
  id: number;
  tenant_id: number;
  email_address: string;
  display_name: string | null;
  mailbox_type: string;
  provider_name: string | null;
  connection_mode: string;
  is_primary: boolean;
  is_active: boolean;
  inbound_enabled: boolean;
  outbound_enabled: boolean;
  status: string;
  imap_host: string | null;
  imap_port: number | null;
  imap_username: string | null;
  smtp_host: string | null;
  smtp_port: number | null;
  smtp_username: string | null;
  use_ssl: boolean | null;
  use_tls: boolean | null;
  oauth_provider: string | null;
  oauth_account_email: string | null;
  last_tested_at: string | null;
  last_test_status: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type EmailConfigUpdatePayload = {
  email_address: string;
  display_name?: string | null;
  mailbox_type?: string;
  provider_name?: string | null;
  connection_mode?: string;
  inbound_enabled?: boolean;
  outbound_enabled?: boolean;
  imap_host?: string | null;
  imap_port?: number | null;
  imap_username?: string | null;
  imap_password?: string | null;
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_username?: string | null;
  smtp_password?: string | null;
  use_ssl?: boolean | null;
  use_tls?: boolean | null;
  oauth_provider?: string | null;
  oauth_account_email?: string | null;
  oauth_access_token?: string | null;
  oauth_refresh_token?: string | null;
};

export type InboxThreadListItem = {
  id: number;
  provider: string;
  subject: string | null;
  participants_json: unknown;
  snippet: string | null;
  last_message_at: string | null;
  message_count: number;
  unread_count: number;
  linked_load_id: number | null;
  intake_bucket: string;
  confidence_level: string | null;
  confidence_score: number | null;
  routing_reason: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  linked_load_number?: string | null;
  linked_broker_name?: string | null;
  pickup_delivery_summary?: string | null;
};

export type InboxThreadDetail = InboxThreadListItem;

export type InboxMessageItem = {
  id: number;
  thread_id: number;
  provider: string;
  external_message_id: string;
  external_thread_id: string;
  direction: string | null;
  from_email: string | null;
  to_json: unknown;
  cc_json: unknown;
  bcc_json: unknown;
  subject: string | null;
  sent_at: string | null;
  received_at: string | null;
  snippet: string | null;
  body_text: string | null;
  body_html: string | null;
  has_attachments: boolean;
  extraction_status: string | null;
  created_at: string;
  updated_at: string;
};

export type InboxThreadListResponse = {
  items: InboxThreadListItem[];
  page: number;
  size: number;
  total: number;
};

export async function getPrimaryEmailConfig(): Promise<EmailConfig | null> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/primary`);
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Failed to load email config");
  return data as EmailConfig | null;
}

export async function updatePrimaryEmailConfig(payload: EmailConfigUpdatePayload): Promise<EmailConfig> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/primary`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<EmailConfig>(res);
}

export async function testPrimaryEmailConfig(): Promise<{ ok: boolean; status: string; message?: string; last_tested_at?: string }> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/primary/test`, { method: "POST" });
  return handle<{ ok: boolean; status: string; message?: string; last_tested_at?: string }>(res);
}

export async function disconnectPrimaryEmailConfig(): Promise<{ ok: boolean; message: string }> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/primary/disconnect`, { method: "POST" });
  return handle<{ ok: boolean; message: string }>(res);
}

export async function listEmailThreads(params?: {
  status?: string;
  provider?: string;
  intake_bucket?: string;
  page?: number;
  size?: number;
}): Promise<InboxThreadListResponse> {
  const usp = new URLSearchParams();
  if (params?.status) usp.set("status", params.status);
  if (params?.provider) usp.set("provider", params.provider);
  if (params?.intake_bucket) usp.set("intake_bucket", params.intake_bucket);
  if (params?.page) usp.set("page", String(params.page));
  if (params?.size) usp.set("size", String(params.size));
  const q = usp.toString();
  const res = await fetchWithTenant(`${API_BASE}/email-threads${q ? `?${q}` : ""}`);
  return handle<InboxThreadListResponse>(res);
}

export async function getEmailThread(threadId: number): Promise<InboxThreadDetail> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}`);
  return handle<InboxThreadDetail>(res);
}

export async function getEmailThreadMessages(threadId: number): Promise<InboxMessageItem[]> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/messages`);
  return handle<InboxMessageItem[]>(res);
}

export async function disregardEmailThread(threadId: number): Promise<InboxThreadDetail> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/disregard`, { method: "POST" });
  return handle<InboxThreadDetail>(res);
}

export type EmailThreadActionLoadSummary = {
  id: number;
  load_number: string;
  status: string;
};

export type EmailThreadDraftOrLinkResult = {
  thread: InboxThreadDetail;
  load: EmailThreadActionLoadSummary;
};

export async function createDraftLoadFromEmailThread(threadId: number): Promise<EmailThreadDraftOrLinkResult> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/create-draft-load`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return handle<EmailThreadDraftOrLinkResult>(res);
}

export async function linkLoadToEmailThread(threadId: number, loadId: number): Promise<EmailThreadDraftOrLinkResult> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/link-load`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ load_id: loadId }),
  });
  return handle<EmailThreadDraftOrLinkResult>(res);
}

// Tenant-admin password reset removed: password management remains platform-side.

export async function acceptInvite(payload: { token: string; new_password: string }): Promise<{
  ok: boolean;
  message: string;
  workspace_url?: string;
}> {
  const res = await fetchWithTenant(`${API_BASE}/auth/accept-invite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<{ ok: boolean; message: string; workspace_url?: string }>(res);
}

export async function createOnboardingInviteLink(params: OnboardingInviteLinkRequest): Promise<OnboardingInviteLinkResponse> {
  const res = await fetchWithTenant(`${API_BASE}/admin/onboarding/invite-link`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: params.email ?? undefined,
      phone: params.phone ?? undefined,
      application_type: params.application_type || "DRIVER",
    }),
  });
  return handle<OnboardingInviteLinkResponse>(res);
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

export type SignupFieldAvailabilityResponse = {
  available: boolean;
  normalized: string;
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
  company_phone?: string;
  company_email?: string;
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
  broker_load_reference?: string | null;
  broker_name_snapshot?: string | null;
  broker_id?: number | null;
  driver_id?: number | null;
  truck_id?: number | null;
  trailer_id?: number | null;
  pickup_date?: string | null;
  delivery_date?: string | null;
  pickup_time?: string | null;
  delivery_time?: string | null;
  pickup_location?: string | null;
  delivery_location?: string | null;
  equipment_type?: string | null;
  rate?: number | null;
  customer_rate?: number | null;
  miles?: number | null;
  status: string;
  broker?: Broker | null;
  driver?: { id: number; first_name: string; last_name: string } | null;
  truck?: { id: number; unit_number: string } | null;
  trailer?: { id: number; unit_number: string; trailer_type?: string | null } | null;
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

/** Person record returned on approve (matches backend PersonOut). */
export type DriverOnboardingPersonOut = {
  id: number;
  tenant_id: number;
  onboarding_status: string;
  first_name: string;
  last_name: string;
  phone?: string | null;
  email?: string | null;
};

export type DriverOnboardingApproveResponse = {
  submission: DriverOnboardingSubmission;
  person: DriverOnboardingPersonOut;
};
