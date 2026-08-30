const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";
const PUBLIC_API_BASE = import.meta.env.VITE_PUBLIC_API_BASE || "/api/v1/public";

export { API_BASE };

/** Tenant is resolved server-side from the request Host (workspace subdomain). Do not send X-Tenant-* from the browser. */
function withTenantHeaders(init?: RequestInit): RequestInit {
  const headers = new Headers(init?.headers as HeadersInit | undefined);
  return { ...init, headers, credentials: "include" };
}

export function fetchWithTenant(input: RequestInfo | URL, init?: RequestInit) {
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.toString()
        : input instanceof Request
          ? input.url
          : String(input);
  return fetch(input, withTenantHeaders(init)).catch((e) => {
    const reason = e instanceof Error ? e.message : String(e);
    throw new Error(`Network error calling ${url}: ${reason || "Failed to fetch"}`);
  });
}

export function fetchPublic(input: RequestInfo | URL, init?: RequestInit) {
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.toString()
        : input instanceof Request
          ? input.url
          : String(input);
  return fetch(input, { ...init, credentials: "include" }).catch((e) => {
    const reason = e instanceof Error ? e.message : String(e);
    throw new Error(`Network error calling ${url}: ${reason || "Failed to fetch"}`);
  });
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    const err = new Error(text || res.statusText);
    (err as Error & { status?: number }).status = res.status;
    throw err;
  }
  return res.json();
}

/** FastAPI returns `{ "detail": { ... } }` for HTTPException with a dict detail. */
export const LOAD_VERSION_CONFLICT = "LOAD_VERSION_CONFLICT" as const;

export type LoadVersionConflictDetail = {
  code: typeof LOAD_VERSION_CONFLICT;
  load_id: number;
  client_version: number;
  server_version: number | null;
  server_snapshot: Load | null;
};

export function parseLoadVersionConflict(err: unknown): LoadVersionConflictDetail | null {
  if (!(err instanceof Error) || !err.message) return null;
  try {
    const outer = JSON.parse(err.message) as { detail?: unknown };
    const d = outer.detail;
    if (d && typeof d === "object" && !Array.isArray(d)) {
      const rec = d as Record<string, unknown>;
      if (rec.code === LOAD_VERSION_CONFLICT) return d as LoadVersionConflictDetail;
    }
  } catch {
    return null;
  }
  return null;
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

export type LoadSettlementItem = PayRunItem & {
  pay_run_id: number;
  pay_run_status: string;
  pay_period_start: string;
  pay_period_end: string;
};

export type LoadSettlementResponse = {
  load_id: number;
  items: LoadSettlementItem[];
  total_earnings: number;
  total_deductions: number;
  net_total: number;
};

export async function getLoadSettlement(loadId: number) {
  const res = await fetchWithTenant(`${API_BASE}/payroll/loads/${loadId}/settlement`);
  return handle<LoadSettlementResponse>(res);
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

/** Public workspace status (used on subdomain login + routing). Includes Turnstile site key when API is fully configured. */
export type PublicTenantStatus = {
  exists: boolean;
  slug: string;
  status?: string;
  db_status?: string;
  ready?: boolean;
  reason?: string;
  turnstile_site_key?: string | null;
};

export async function getTenantStatus(slug: string): Promise<PublicTenantStatus> {
  const url = new URL(`${PUBLIC_API_BASE}/tenant/${encodeURIComponent(slug)}`, window.location.origin);
  const res = await fetchPublic(url.toString().replace(window.location.origin, ""));
  if (!res.ok) {
    const text = await res.text();
    const err = new Error(text || res.statusText) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<PublicTenantStatus>;
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

export type WorkspaceIntakeSession = {
  selected_package_code: string;
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
};

export type WorkspaceIntakeConsumeResult = WorkspaceIntakeSession & { ok?: boolean };

export async function submitWorkspaceIntake(payload: {
  first_name: string;
  last_name: string;
  email: string;
  confirm_email: string;
  phone_number: string;
  selected_package_code: string;
}) {
  const res = await fetchPublic(`${PUBLIC_API_BASE}/workspace-intake`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<{ ok: boolean; message?: string }>(res);
}

export async function consumeWorkspaceIntakeToken(intake_token: string) {
  const res = await fetchPublic(`${PUBLIC_API_BASE}/workspace-intake/consume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ intake_token }),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = "Invalid or expired link";
    try {
      const json = text ? (JSON.parse(text) as { detail?: string }) : null;
      if (json?.detail) message = String(json.detail);
    } catch {
      /* use default */
    }
    throw new Error(message);
  }
  return handle<WorkspaceIntakeConsumeResult>(res);
}

export async function getWorkspaceIntakeSession(): Promise<WorkspaceIntakeSession | null> {
  const res = await fetchPublic(`${PUBLIC_API_BASE}/workspace-intake/session`);
  if (res.status === 401) return null;
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Session check failed");
  }
  return handle<WorkspaceIntakeSession>(res);
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

export type CreateWorkspacePayload = {
  workspace_slug: string;
  company_legal_name: string;
  first_name: string;
  last_name: string;
  phone: string;
  address: SignupAddress;
};

/** Authenticated: new tenant from platform (cookies / JWT). No tenant header required. */
export async function createWorkspace(payload: CreateWorkspacePayload) {
  const res = await fetchPublic(`${API_BASE}/auth/workspaces`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = "Could not create workspace";
    try {
      const json = text ? (JSON.parse(text) as { detail?: string | Array<{ msg?: string }> }) : null;
      if (json?.detail) {
        message = Array.isArray(json.detail)
          ? (json.detail as Array<{ msg?: string }>).map((d) => d?.msg ?? "").filter(Boolean).join(". ") || message
          : String(json.detail);
      }
    } catch {
      /* use default */
    }
    throw new Error(message);
  }
  return handle<
    VerifyOtpResponse & {
      verified?: boolean;
      tenant_id?: number;
      slug?: string;
    }
  >(res);
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

export async function resendOtp(payload: { email: string; signup_id?: string | null; attempt_id?: string; slug?: string }) {
  const signupId = payload.signup_id ?? payload.attempt_id ?? undefined;
  const res = await fetchPublic(`${PUBLIC_API_BASE}/resend-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: payload.email, signup_id: signupId || undefined }),
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

export async function cancelSignup(payload: { signup_id?: string; attempt_id?: string }) {
  const signup_id = payload.signup_id ?? payload.attempt_id;
  const res = await fetchPublic(`${PUBLIC_API_BASE}/cancel-signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ signup_id: signup_id || undefined, attempt_id: payload.attempt_id }),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = text || "Cancel failed";
    try {
      const json = text ? (JSON.parse(text) as { detail?: string }) : null;
      if (json?.detail) message = String(json.detail);
    } catch {
      /* keep raw */
    }
    throw new Error(message);
  }
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
    tenant_local_user_id?: number | null;
    tenant_auth_mode?: string | null;
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

/** Backend signals Turnstile must be satisfied before password check (after failed-attempt streak). */
export class LoginVerificationRequiredError extends Error {
  override readonly name = "LoginVerificationRequiredError";
  constructor() {
    super("Additional verification required.");
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Backend requires email OTP step-up after password; body includes login_challenge_id only (with detail). */
export class LoginStepUpRequiredError extends Error {
  override readonly name = "LoginStepUpRequiredError";
  readonly loginChallengeId: string;
  /** True when admin/platform cleared a sign-in block; next step is email verification. */
  readonly afterSignInUnlock: boolean;
  constructor(loginChallengeId: string, afterSignInUnlock = false) {
    super("Additional verification required.");
    this.loginChallengeId = loginChallengeId;
    this.afterSignInUnlock = afterSignInUnlock;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

const LOGIN_VERIFICATION_DETAIL = "Additional verification required.";

/** POST /auth/login returned 429 with retry_after_seconds (sign-in rate limit). */
export class LoginRateLimitedError extends Error {
  override readonly name = "LoginRateLimitedError";
  readonly retryAfterSeconds: number;
  readonly retryAt: string;
  constructor(message: string, retryAfterSeconds: number, retryAt: string) {
    super(message);
    this.retryAfterSeconds = retryAfterSeconds;
    this.retryAt = retryAt;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

function throwLoginHttpError(status: number, message: string): never {
  const err = new Error(message) as Error & { status?: number };
  err.status = status;
  throw err;
}

export async function login(payload: {
  email: string;
  password: string;
  turnstile_token?: string | null;
  login_challenge_id?: string | null;
  /** If true, API may set device-trust cookie after success. Default: omit (false on server). */
  trust_this_device?: boolean;
}) {
  const body: Record<string, string | boolean> = { email: payload.email, password: payload.password };
  if (payload.turnstile_token) body.turnstile_token = payload.turnstile_token;
  if (payload.login_challenge_id) body.login_challenge_id = payload.login_challenge_id;
  if (payload.trust_this_device === true) body.trust_this_device = true;
  if (payload.trust_this_device === false) body.trust_this_device = false;
  const res = await fetchWithTenant(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    // Avoid attributing 5xx / HTML bodies to invalid credentials; authErrorToMessage maps 5xx separately.
    let message = res.status === 401 ? "Invalid email or password" : "";
    try {
      const json = text ? (JSON.parse(text) as Record<string, unknown>) : null;
      if (res.status === 429 && json && typeof json.detail === "object" && json.detail !== null) {
        const inner = json.detail as Record<string, unknown>;
        if (typeof inner.retry_after_seconds === "number") {
          const msg =
            typeof inner.detail === "string"
              ? inner.detail
              : "Too many sign-in attempts. Please wait before trying again.";
          const retryAt = typeof inner.retry_at === "string" ? inner.retry_at : "";
          throw new LoginRateLimitedError(msg, Math.max(1, Math.floor(inner.retry_after_seconds)), retryAt);
        }
      }
      if (res.status === 403 && json?.detail === LOGIN_VERIFICATION_DETAIL) {
        const cid = json.login_challenge_id;
        if (typeof cid === "string" && cid.length === 36) {
          const afterUnlock = json.after_sign_in_unlock === true;
          throw new LoginStepUpRequiredError(cid, afterUnlock);
        }
        throw new LoginVerificationRequiredError();
      }
      if (typeof json?.detail === "string") message = json.detail;
    } catch (e) {
      if (e instanceof LoginVerificationRequiredError) throw e;
      if (e instanceof LoginStepUpRequiredError) throw e;
      if (e instanceof LoginRateLimitedError) throw e;
    }
    throwLoginHttpError(res.status, message);
  }
  return handle<{ ok: boolean; workspace_url?: string; familiar_device?: boolean }>(res);
}

export async function loginStepUpIssue(payload: { login_challenge_id: string }) {
  const res = await fetchWithTenant(`${API_BASE}/auth/login-step-up/issue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = "Something went wrong. Please try again.";
    try {
      const json = text ? (JSON.parse(text) as { detail?: string }) : null;
      if (json?.detail) message = json.detail;
    } catch {
      /* use default */
    }
    throwLoginHttpError(res.status, message);
  }
  return handle<{ ok: boolean; message?: string }>(res);
}

export async function loginStepUpVerify(payload: { login_challenge_id: string; otp: string }) {
  const res = await fetchWithTenant(`${API_BASE}/auth/login-step-up/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login_challenge_id: payload.login_challenge_id, otp: payload.otp.trim() }),
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
    throwLoginHttpError(res.status, message);
  }
  return handle<{ ok: boolean }>(res);
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
export type DispatchNumberingState = {
  trip_number_prefix: string | null;
  prefix_locked: boolean;
};

export async function getDispatchNumbering() {
  const res = await fetchWithTenant(`${API_BASE}/admin/dispatch-numbering`);
  return handle<DispatchNumberingState>(res);
}

export async function putDispatchNumbering(payload: { trip_number_prefix: string }) {
  const res = await fetchWithTenant(`${API_BASE}/admin/dispatch-numbering`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<DispatchNumberingState>(res);
}

export type BrokerIntakeSettings = {
  broker_auto_create_from_global: boolean;
};

export async function getBrokerIntakeSettings() {
  const res = await fetchWithTenant(`${API_BASE}/admin/broker-intake-settings`);
  return handle<BrokerIntakeSettings>(res);
}

export async function patchBrokerIntakeSettings(payload: BrokerIntakeSettings) {
  const res = await fetchWithTenant(`${API_BASE}/admin/broker-intake-settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<BrokerIntakeSettings>(res);
}

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

/** Read-only trip container (operational) — members from trip_loads. */
export type TripMemberLoad = {
  trip_load_id: number;
  load_id: number;
  status_within_trip: string;
  sequence_hint: number | null;
  added_at: string;
  completed_at?: string | null;
  removed_at: string | null;
  load_number: string;
  broker_name_snapshot?: string | null;
  broker_load_reference?: string | null;
  commodity?: string | null;
  rate?: number | null;
  customer_rate?: number | null;
  stop_route_summary?: string | null;
};

/** OPEN membership: planned|active and both terminal timestamps null. */
export function isOpenTripMembership(m: {
  status_within_trip?: string | null;
  completed_at?: string | null;
  removed_at?: string | null;
}): boolean {
  const st = (m.status_within_trip || "").toLowerCase();
  return (
    (st === "planned" || st === "active") &&
    m.completed_at == null &&
    m.removed_at == null
  );
}

export type TripDetail = {
  id: number;
  tenant_id: number;
  trip_number: string;
  status: string;
  job_type: string;
  driver_id?: number | null;
  driver?: {
    id: number;
    first_name: string;
    last_name: string;
    phone?: string | null;
    email?: string | null;
  } | null;
  truck_id?: number | null;
  truck?: { id: number; unit_number: string } | null;
  trailer_id?: number | null;
  trailer?: { id: number; unit_number: string; trailer_type?: string | null } | null;
  assigned_at?: string | null;
  completed_at?: string | null;
  cancelled_at?: string | null;
  planned_start_at?: string | null;
  expected_completion_at?: string | null;
  created_at: string;
  updated_at: string;
  legacy_dispatch_trip_id?: number | null;
  member_loads: TripMemberLoad[];
};

export async function getTrip(tripId: number) {
  const res = await fetchWithTenant(`${API_BASE}/trips/${tripId}`);
  return handle<TripDetail>(res);
}

export type TripListItem = {
  id: number;
  trip_number: string;
  status: string;
  job_type: string;
  driver_id?: number | null;
  driver?: TripDetail["driver"];
  truck_id?: number | null;
  truck?: { id: number; unit_number: string } | null;
  trailer_id?: number | null;
  trailer?: { id: number; unit_number: string; trailer_type?: string | null } | null;
  assigned_at?: string | null;
  completed_at?: string | null;
  cancelled_at?: string | null;
  planned_start_at?: string | null;
  expected_completion_at?: string | null;
  created_at: string;
  updated_at: string;
  member_load_count: number;
  first_member?: {
    load_number: string;
    broker_name_snapshot?: string | null;
    broker_load_reference?: string | null;
    stop_route_summary?: string | null;
  } | null;
};

export async function listTrips(params: { search?: string; status?: string; page?: number; size?: number } = {}) {
  const url = new URL(`${API_BASE}/trips`, window.location.origin);
  if (params.search?.trim()) url.searchParams.set("search", params.search.trim());
  if (params.status?.trim()) url.searchParams.set("status", params.status.trim());
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<TripListItem>>(res);
}

/** POST /trips — create planned trip container; mirrors CreatePlannedTripBody on the API. */
export type CreatePlannedTripBody = {
  status?: string | null;
  job_type?: string | null;
  driver_id?: number | null;
  truck_id?: number | null;
  trailer_id?: number | null;
  load_ids?: number[];
};

export async function createPlannedTrip(body: CreatePlannedTripBody): Promise<TripDetail> {
  const res = await fetchWithTenant(`${API_BASE}/trips`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<TripDetail>(res);
}

/** POST /trips/{id}/loads — attach an existing load to the trip container. */
export type AddTripLoadBody = {
  load_id: number;
  sequence_hint?: number | null;
};

export async function addLoadToTrip(tripId: number, body: AddTripLoadBody): Promise<TripDetail> {
  const res = await fetchWithTenant(`${API_BASE}/trips/${tripId}/loads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<TripDetail>(res);
}

/** POST /trips/{id}/loads/{loadId}/remove — soft-remove membership; no body. */
export async function removeLoadFromTrip(tripId: number, loadId: number): Promise<TripDetail> {
  const res = await fetchWithTenant(`${API_BASE}/trips/${tripId}/loads/${loadId}/remove`, {
    method: "POST",
  });
  return handle<TripDetail>(res);
}

/** POST /api/v1/trips/{id}/cancel — cancel planned trip container; no body. */
export async function cancelTrip(tripId: number): Promise<TripDetail> {
  const res = await fetchWithTenant(`${API_BASE}/trips/${tripId}/cancel`, {
    method: "POST",
  });
  return handle<TripDetail>(res);
}


/** POST /api/v1/trips/{id}/execution-signal — Decision 7: start execution from accepted signal. */
export type TripExecutionSignalBody = {
  source: "dispatcher_manual" | "driver_app";
  reason_note?: string | null;
  signal_at?: string | null;
};

export async function postTripExecutionSignal(tripId: number, body: TripExecutionSignalBody): Promise<TripDetail> {
  const res = await fetchWithTenant(`${API_BASE}/trips/${tripId}/execution-signal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<TripDetail>(res);
}

/** PUT /api/v1/trips/{id}/assignment — Decision 14A: driver/truck/trailer only (all keys required; null clears). */
export type TripAssignmentPayload = {
  driver_id: number | null;
  truck_id: number | null;
  trailer_id: number | null;
};

export async function updateTripAssignment(tripId: number, body: TripAssignmentPayload): Promise<TripDetail> {
  const res = await fetchWithTenant(`${API_BASE}/trips/${tripId}/assignment`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<TripDetail>(res);
}

/** PUT /api/v1/trips/{id}/schedule — COMMIT 4a: scheduling bounds only (both keys required; null clears). */
export type TripSchedulePayload = {
  planned_start_at: string | null;
  expected_completion_at: string | null;
};

export async function updateTripSchedule(tripId: number, body: TripSchedulePayload): Promise<TripDetail> {
  const res = await fetchWithTenant(`${API_BASE}/trips/${tripId}/schedule`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<TripDetail>(res);
}

export async function createLoad(payload: LoadWritePayload) {
  const res = await fetchWithTenant(`${API_BASE}/loads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<Load>(res);
}

export type LoadDocumentParseReference = {
  kind: string;
  value: string;
  label?: string | null;
  primary_candidate?: boolean | null;
  confidence?: string | null;
};

export type LoadDocumentParseStop = {
  stop_type: string;
  sequence: number;
  facility_name?: string | null;
  street?: string | null;
  city?: string | null;
  state_or_province?: string | null;
  postal_code?: string | null;
  country?: string | null;
  reference_number?: string | null;
  appointment_type?: string | null;
  appointment_date?: string | null;
  appointment_time_text?: string | null;
  notes?: string | null;
};

export type LoadDocumentParseExtracted = {
  broker_name_snapshot?: string | null;
  broker_contact_name_snapshot?: string | null;
  broker_contact_phone_snapshot?: string | null;
  broker_contact_email_snapshot?: string | null;
  broker_load_reference?: string | null;
  /** Digits as extracted from PDF — resolve tenant broker via /brokers/resolve-identity */
  broker_mc_number_snapshot?: string | null;
  broker_dot_number_snapshot?: string | null;
  mode?: string | null;
  equipment_type?: string | null;
  trailer_type?: string | null;
  trailer_size?: string | null;
  commodity?: string | null;
  estimated_weight?: number | null;
  temperature_requirement?: string | null;
  rate?: number | null;
  customer_rate?: number | null;
  miles?: number | null;
  customs_broker_name?: string | null;
  references: LoadDocumentParseReference[];
  stops: LoadDocumentParseStop[];
};

export type LoadDocumentParseResponse = {
  document: { filename: string };
  extracted: LoadDocumentParseExtracted;
  raw_text: string;
  warnings: string[];
  field_confidence: Record<string, string>;
  context?: Record<string, unknown>;
};

/** Multipart PDF upload — hydrates workspace fields only; does not create a load. */
export async function parseLoadWorkspaceDocument(
  file: File,
  opts?: { emailThreadId?: number | null; loadId?: number | null },
) {
  const fd = new FormData();
  fd.append("file", file);
  if (opts?.emailThreadId != null && Number.isFinite(opts.emailThreadId)) {
    fd.append("email_thread_id", String(opts.emailThreadId));
  }
  if (opts?.loadId != null && Number.isFinite(opts.loadId)) {
    fd.append("load_id", String(opts.loadId));
  }
  const res = await fetchWithTenant(`${API_BASE}/loads/parse-document`, {
    method: "POST",
    body: fd,
  });
  return handle<LoadDocumentParseResponse>(res);
}

/** Load Lab — persisted extraction run (tenant DB). */
export type LoadLabRun = {
  id: number;
  tenant_id: number;
  created_at: string;
  updated_at: string;
  source_route: string;
  created_by_platform_user_id: string | null;
  file_sha256: string;
  filename: string;
  mime_type: string;
  file_size_bytes: number;
  status: string;
  extraction_path: string | null;
  dedupe_prior_run_id: number | null;
  parser_version: string;
  schema_version: string;
  prompt_version: string;
  model_name: string;
  ocr_engine_version: string | null;
  normalizer_version: string;
  classification_label: string | null;
  relevance: string | null;
  normalized_package: Record<string, unknown> | null;
  parse_response?: Record<string, unknown> | null;
  ai_model_output?: Record<string, unknown> | null;
  warnings: unknown[] | null;
  pipeline_error: string | null;
  semantic_model_name?: string | null;
  semantic_prompt_version?: string | null;
  semantic_schema_version?: string | null;
  semantic_extract_status?: string | null;
  semantic_validation_result?: Record<string, unknown> | null;
  lab_confidence?: Record<string, unknown> | null;
  contradictions?: unknown[] | null;
  lab_review_status?: string | null;
  lab_review_summary?: string | null;
};

export type LoadLabRunUploadResult = {
  run: LoadLabRun;
  reused_existing_run: boolean;
};

export async function uploadLoadLabRun(file: File, opts?: { forceRerun?: boolean }) {
  const fd = new FormData();
  fd.append("file", file);
  if (opts?.forceRerun) fd.append("force_rerun", "true");
  const res = await fetchWithTenant(`${API_BASE}/load-lab/runs/upload`, { method: "POST", body: fd });
  return handle<LoadLabRunUploadResult>(res);
}

export async function listLoadLabRuns(limit = 30) {
  const res = await fetchWithTenant(`${API_BASE}/load-lab/runs?limit=${encodeURIComponent(String(limit))}`);
  return handle<LoadLabRun[]>(res);
}

export async function clearLoadLabRuns() {
  const res = await fetchWithTenant(`${API_BASE}/load-lab/runs`, { method: "DELETE" });
  return handle<{ deleted: number }>(res);
}

export async function getLoadLabRun(runId: number) {
  const res = await fetchWithTenant(`${API_BASE}/load-lab/runs/${runId}`);
  return handle<LoadLabRun>(res);
}

/** Tenant admin only — OpenAI connectivity (GET /v1/models); does not parse PDFs. */
export type LoadLabOpenaiSmokeResult = {
  ok: boolean;
  http_status: number | null;
  sample_model_id?: string | null;
  detail?: string | null;
};

export async function postLoadLabOpenaiSmoke() {
  const res = await fetchWithTenant(`${API_BASE}/load-lab/openai-smoke`, { method: "POST" });
  return handle<LoadLabOpenaiSmokeResult>(res);
}

export async function postLoadLabSemanticExtract(
  runId: number,
  opts?: { force?: boolean; mode?: string; responseContract?: string }
) {
  const qs: string[] = [];
  if (opts?.force) qs.push("force=true");
  if (opts?.mode?.trim()) qs.push(`mode=${encodeURIComponent(opts.mode.trim())}`);
  if (opts?.responseContract?.trim())
    qs.push(`response_contract=${encodeURIComponent(opts.responseContract.trim())}`);
  const q = qs.length ? `?${qs.join("&")}` : "";
  const res = await fetchWithTenant(`${API_BASE}/load-lab/runs/${runId}/semantic-extract${q}`, { method: "POST" });
  return handle<LoadLabRun>(res);
}

export async function postLoadLabRecomputeReview(runId: number) {
  const res = await fetchWithTenant(`${API_BASE}/load-lab/runs/${runId}/lab-review`, { method: "POST" });
  return handle<LoadLabRun>(res);
}

export type BrokerResolveIdentity = {
  broker_id: number | null;
  matched_by: "mc" | "dot" | null;
  broker: Broker | null;
};

export async function resolveBrokerIdentity(params: { mc_number?: string; dot_number?: string }) {
  const url = new URL(`${API_BASE}/brokers/resolve-identity`, window.location.origin);
  if (params.mc_number?.trim()) url.searchParams.set("mc_number", params.mc_number.trim());
  if (params.dot_number?.trim()) url.searchParams.set("dot_number", params.dot_number.trim());
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<BrokerResolveIdentity>(res);
}

export type LoadUpdatePayload = LoadWritePayload & { expected_concurrency_version: number };

export async function updateLoad(id: number, payload: LoadUpdatePayload) {
  const res = await fetchWithTenant(`${API_BASE}/loads/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<Load>(res);
}

/** POST /loads/{id}/mark-ready — draft → ready; requires expected_concurrency_version from last read/save. */
export async function markLoadReady(loadId: number, expectedConcurrencyVersion: number) {
  const res = await fetchWithTenant(`${API_BASE}/loads/${loadId}/mark-ready`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_concurrency_version: expectedConcurrencyVersion }),
  });
  return handle<Load>(res);
}

export type CustomsBroker = {
  id: number;
  tenant_id?: number;
  legal_name: string;
  phone_primary?: string | null;
  is_active?: boolean;
  fax?: string | null;
};

export async function listCustomsBrokers(params: {
  page?: number;
  size?: number;
  include_inactive?: boolean;
} = {}) {
  const url = new URL(`${API_BASE}/customs-brokers`, window.location.origin);
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  if (params.include_inactive) url.searchParams.set("include_inactive", "true");
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<CustomsBroker>>(res);
}

export async function confirmLoadDocumentSnapshot(loadId: number, expectedConcurrencyVersion: number) {
  const res = await fetchWithTenant(`${API_BASE}/loads/${loadId}/confirm-document-snapshot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_concurrency_version: expectedConcurrencyVersion }),
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
  const base = (API_BASE || "/api/v1").replace(/\/+$/, "");
  const url = new URL(`${base}/loads/${loadId}/notes`, window.location.origin);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<LoadNote[]>(res);
}

export async function addLoadNote(loadId: number, body: string) {
  const base = (API_BASE || "/api/v1").replace(/\/+$/, "");
  const url = new URL(`${base}/loads/${loadId}/notes`, window.location.origin);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  });
  return handle<LoadNote>(res);
}

export async function listBrokers(
  params: {
    page?: number;
    size?: number;
    q?: string;
    include_archived?: boolean;
    sort?: "name_asc" | "name_desc" | "id_desc";
  } = {}
) {
  const url = new URL(`${API_BASE}/brokers`, window.location.origin);
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  if (params.q?.trim()) url.searchParams.set("q", params.q.trim());
  if (params.include_archived) url.searchParams.set("include_archived", "true");
  if (params.sort) url.searchParams.set("sort", params.sort);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<Broker>>(res);
}

export async function createBroker(payload: Partial<Broker> & { name?: string; display_name?: string; legal_name?: string }) {
  const res = await fetchWithTenant(`${API_BASE}/brokers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<Broker>(res);
}

export async function getBroker(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/brokers/${id}`);
  return handle<Broker>(res);
}

export async function updateBroker(id: number, payload: Partial<Broker>) {
  const res = await fetchWithTenant(`${API_BASE}/brokers/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<Broker>(res);
}

export type BrokerWorkspace = {
  broker: Broker;
  contacts: BrokerContact[];
  domains: BrokerDomain[];
  aliases: BrokerAlias[];
  known_senders: BrokerKnownSender[];
};

export async function getBrokerWorkspace(brokerId: number, params: { include_archived?: boolean } = {}) {
  const url = new URL(`${API_BASE}/brokers/${brokerId}/workspace`, window.location.origin);
  if (params.include_archived === false) url.searchParams.set("include_archived", "false");
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<BrokerWorkspace>(res);
}

export async function archiveBroker(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/brokers/${id}/archive`, { method: "POST" });
  return handle<Broker>(res);
}

export async function unarchiveBroker(id: number) {
  const res = await fetchWithTenant(`${API_BASE}/brokers/${id}/unarchive`, { method: "POST" });
  return handle<Broker>(res);
}

export type BrokerContact = {
  id: number;
  broker_id: number;
  name: string;
  first_name?: string | null;
  last_name?: string | null;
  role?: string | null;
  department?: string | null;
  phone?: string | null;
  extension?: string | null;
  fax?: string | null;
  email?: string | null;
  is_primary: boolean;
  notes?: string | null;
  is_active: boolean;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type BrokerDomain = {
  id: number;
  tenant_id: number;
  broker_id: number;
  domain: string;
  is_primary: boolean;
  notes?: string | null;
  is_active: boolean;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type BrokerAlias = {
  id: number;
  tenant_id: number;
  broker_id: number;
  alias: string;
  alias_type: string;
  is_active: boolean;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type BrokerKnownSender = {
  id: number;
  tenant_id: number;
  broker_id: number;
  email_normalized: string;
  notes?: string | null;
  is_active: boolean;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
};

export async function listBrokerContacts(brokerId: number, params: { page?: number; size?: number; include_archived?: boolean } = {}) {
  const url = new URL(`${API_BASE}/brokers/${brokerId}/contacts`, window.location.origin);
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  if (params.include_archived) url.searchParams.set("include_archived", "true");
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<BrokerContact>>(res);
}

export async function createBrokerContact(
  brokerId: number,
  payload: {
    name: string;
    first_name?: string | null;
    last_name?: string | null;
    role?: string | null;
    department?: string | null;
    phone?: string | null;
    extension?: string | null;
    fax?: string | null;
    email?: string | null;
    is_primary?: boolean;
    notes?: string | null;
  }
) {
  const res = await fetchWithTenant(`${API_BASE}/brokers/${brokerId}/contacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<BrokerContact>(res);
}

export async function listBrokerDomains(brokerId: number, params: { page?: number; size?: number; include_archived?: boolean } = {}) {
  const url = new URL(`${API_BASE}/brokers/${brokerId}/domains`, window.location.origin);
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  if (params.include_archived) url.searchParams.set("include_archived", "true");
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<BrokerDomain>>(res);
}

export async function createBrokerDomain(
  brokerId: number,
  payload: { domain: string; is_primary?: boolean; notes?: string | null }
) {
  const res = await fetchWithTenant(`${API_BASE}/brokers/${brokerId}/domains`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<BrokerDomain>(res);
}

export async function listBrokerAliases(brokerId: number, params: { page?: number; size?: number; include_archived?: boolean } = {}) {
  const url = new URL(`${API_BASE}/brokers/${brokerId}/aliases`, window.location.origin);
  if (params.page) url.searchParams.set("page", String(params.page));
  if (params.size) url.searchParams.set("size", String(params.size));
  if (params.include_archived) url.searchParams.set("include_archived", "true");
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PagedResponse<BrokerAlias>>(res);
}

export async function createBrokerAlias(
  brokerId: number,
  payload: { alias: string; alias_type?: string }
) {
  const res = await fetchWithTenant(`${API_BASE}/brokers/${brokerId}/aliases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<BrokerAlias>(res);
}

export async function createBrokerKnownSender(
  brokerId: number,
  payload: { email: string; notes?: string | null }
) {
  const res = await fetchWithTenant(`${API_BASE}/brokers/${brokerId}/known-senders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<BrokerKnownSender>(res);
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

export async function listDrivers(
  params: { limit?: number; offset?: number; include_inactive?: boolean; q?: string } = {},
) {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set("limit", String(params.limit));
  if (params.offset != null) sp.set("offset", String(params.offset));
  if (params.include_inactive != null) sp.set("include_inactive", String(params.include_inactive));
  if (params.q != null && params.q.trim() !== "") sp.set("q", params.q.trim());
  const qs = sp.toString();
  const url = `${API_BASE}/drivers${qs ? `?${qs}` : ""}`;
  const res = await fetchWithTenant(url);
  return handle<Driver[]>(res);
}

export type DriverAssignmentHints = { truck_id: number | null; trailer_id: number | null };

export async function getDriverAssignmentHints(driverId: number) {
  const res = await fetchWithTenant(`${API_BASE}/drivers/${driverId}/assignment-hints`);
  return handle<DriverAssignmentHints>(res);
}

export async function getTruckSuggestedTrailer(truckId: number) {
  const res = await fetchWithTenant(`${API_BASE}/trucks/${truckId}/suggested-trailer`);
  return handle<{ trailer_id: number | null }>(res);
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
  /** pending | pending_downstream | complete */
  setup_status?: string;
  application_type?: string;
  requested_role_code?: string;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  submitted_at?: string | null;
  source?: string | null;
  created_at: string;
  /** submitted | processing | hr_payroll | complete | rejected — admin queue routing (API excludes complete). */
  current_workflow_lane?: string;
  /** Set when admin opens detail / starts review (SUBMITTED only until approve/reject). */
  reviewed_at?: string | null;
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
  onboarded_at?: string | null;
  onboarded_by_user_id?: number | null;
  /** pending | pending_downstream | complete */
  setup_status?: string;
  /** submitted | processing | hr_payroll | complete | rejected */
  current_workflow_lane?: string;
  rejection_reason?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  email?: string | null;
  address_street?: string | null;
  address_city?: string | null;
  address_region?: string | null;
  address_postal?: string | null;
  zip_code?: string | null;
  address_country?: string | null;
  driver_license_number?: string | null;
  license_region?: string | null;
  license_expiry?: string | null;
  notes?: string | null;
  submitted_at?: string | null;
  created_at: string;
  updated_at: string;
  intake_payload?: Record<string, unknown> | null;
  /** Admin GET: frozen intake JSON at applicant submit (evidence). */
  intake_submitted_snapshot?: Record<string, unknown> | null;
  /** Admin GET: audit entries for review-field edits. */
  intake_review_audit?: Array<{ at?: string; by_user_id?: number; changed_keys?: string[] }> | null;
  /** When true, applicant may upload step-4 documents after submit (document-resume token). */
  document_resume_active?: boolean;
};

/** Used by OnboardingApplicantPage (same shape as ApplicantApplication). */
export type PersonApplication = ApplicantApplication;

/** Admin PATCH body for correcting structured applicant fields (review workspace). */
export type PersonApplicationReviewPatchPayload = {
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  email?: string | null;
  address_street?: string | null;
  address_city?: string | null;
  address_region?: string | null;
  address_postal?: string | null;
  zip_code?: string | null;
  address_country?: string | null;
  notes?: string | null;
  driver_license_number?: string | null;
  license_region?: string | null;
  license_expiry?: string | null;
  middle_name?: string | null;
  date_of_birth?: string | null;
  license_issue_date?: string | null;
  cdl_class?: string | null;
  endorsements?: string | null;
  restrictions?: string | null;
  conditions?: string | null;
};

export type ApplicantApplicationUpdatePayload = {
  first_name?: string;
  last_name?: string;
  phone?: string;
  email?: string;
  address_street?: string;
  address_city?: string;
  address_region?: string;
  address_postal?: string;
  zip_code?: string;
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

/** Idempotent: while SUBMITTED, sets reviewed_at so the admin queue moves the row to Processing. */
export async function markAdminReviewEngaged(applicationId: number): Promise<ApplicantApplication> {
  const res = await fetchWithTenant(
    `${API_BASE}/driver-onboarding/applications/${applicationId}/mark-admin-review-engaged`,
    { method: "POST" },
  );
  return handle<ApplicantApplication>(res);
}

// ---- People workspace (maintained `people` master; tenant admin + admin_sensitive) ----

export type PersonRoleSummary = {
  id: number;
  role_code: string;
  is_primary: boolean;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
};

export type DriverProfileSummary = {
  license_number?: string | null;
  license_region?: string | null;
  license_expiry?: string | null;
  is_active: boolean;
};

export type DriverPersonExtensionSummary = {
  employment_relationship_type: string;
  driver_operating_subtype: string;
  is_team_driver: boolean;
  provides_own_truck: boolean;
  provides_own_trailer: boolean;
  equipment_contribution_type: string;
  insurance_commercial_approved: boolean;
};

export type OperationalDriverSummary = {
  driver_id: number;
  is_active: boolean;
  first_name: string;
  last_name: string;
  payee_id?: number | null;
};

export type CompensationSummary = {
  payee_id?: number | null;
  worker_type?: string | null;
  gross_calc_type?: string | null;
  hourly_rate?: string | null;
  cpm_loaded?: string | null;
  cpm_empty?: string | null;
  percent_rate?: string | null;
  salary_amount?: string | null;
  flat_amount?: string | null;
  settlement_frequency?: string | null;
  participates_in_fuel_discount_program?: boolean | null;
  dispatch_fee_enabled?: boolean | null;
  dispatch_fee_rate?: string | null;
  dispatch_fee_basis?: string | null;
};

export type LinkedPersonApplicationSummary = {
  id: number;
  status: string;
  setup_status?: string | null;
  /** Raw `person_applications.current_workflow_lane`. */
  current_workflow_lane?: string | null;
};

export type PeopleListItem = {
  id: number;
  tenant_id: number;
  first_name: string;
  last_name: string;
  phone?: string | null;
  email?: string | null;
  city?: string | null;
  region?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  /** Active `person_roles` only; read-only list hint. */
  active_role_codes: string[];
  primary_role_code?: string | null;
  /** Latest linked onboarding application (same ordering as detail). */
  latest_application?: LinkedPersonApplicationSummary | null;
};

export type PeopleDetail = PeopleListItem & {
  street_address?: string | null;
  postal_code?: string | null;
  zip_code?: string | null;
  country?: string | null;
  notes?: string | null;
  platform_user_id?: string | null;
  roles: PersonRoleSummary[];
  driver_profile?: DriverProfileSummary | null;
  driver_person_extension?: DriverPersonExtensionSummary | null;
  operational_drivers: OperationalDriverSummary[];
  compensation: CompensationSummary;
};

export type PeopleCorePatchPayload = {
  first_name?: string;
  last_name?: string;
  phone?: string | null;
  email?: string | null;
  street_address?: string | null;
  city?: string | null;
  region?: string | null;
  postal_code?: string | null;
  zip_code?: string | null;
  country?: string | null;
  notes?: string | null;
  is_active?: boolean;
};

export type DriverProfilePatchPayload = {
  license_number?: string | null;
  license_region?: string | null;
  license_expiry?: string | null;
  is_active?: boolean;
};

export type PeoplePatchResult = {
  person: PeopleDetail;
  synced_operational_driver_ids: number[];
};

/** People workspace maintenance corrections (subset of tenant_audit_logs). */
export type PeopleAuditLogEntry = {
  id: number;
  action: string;
  created_at: string;
  actor_user_id?: number | null;
  actor_email?: string | null;
  ip?: string | null;
  user_agent?: string | null;
  changed_keys: string[];
  snapshot: Record<string, unknown>;
};

export type AuditEventRow = {
  id: number;
  event_at: string;
  actor_user_id?: number | null;
  actor_label?: string | null;
  module: string;
  entity_type: string;
  entity_id: string;
  entity_label?: string | null;
  action: string;
  request_id?: string | null;
  correlation_id?: string | null;
  source: string;
  visibility: string;
  changed_fields: Record<string, { before?: unknown; after?: unknown; redacted?: boolean }>;
};

export async function listAuditEventsByEntity(
  entityType: string,
  entityId: string,
  opts?: { limit?: number; offset?: number },
): Promise<AuditEventRow[]> {
  const q = new URLSearchParams({
    entity_type: entityType,
    entity_id: entityId,
    limit: String(opts?.limit ?? 50),
    offset: String(opts?.offset ?? 0),
  });
  const res = await fetchWithTenant(`${API_BASE}/audit-events/by-entity?${q.toString()}`);
  return handle<AuditEventRow[]>(res);
}

export async function listPersonWorkspaceAuditLog(
  personId: number,
  params: { limit?: number; offset?: number } = {},
): Promise<PeopleAuditLogEntry[]> {
  const url = new URL(`${API_BASE}/people/${personId}/audit-log`, window.location.origin);
  if (params.limit != null) url.searchParams.set("limit", String(params.limit));
  if (params.offset != null) url.searchParams.set("offset", String(params.offset));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PeopleAuditLogEntry[]>(res);
}

export async function listPeopleForWorkspace(params: {
  q?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<PeopleListItem[]> {
  const url = new URL(`${API_BASE}/people`, window.location.origin);
  if (params.q?.trim()) url.searchParams.set("q", params.q.trim());
  if (params.limit != null) url.searchParams.set("limit", String(params.limit));
  if (params.offset != null) url.searchParams.set("offset", String(params.offset));
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""));
  return handle<PeopleListItem[]>(res);
}

export async function getPersonWorkspaceDetail(personId: number): Promise<PeopleDetail> {
  const res = await fetchWithTenant(`${API_BASE}/people/${personId}`);
  return handle<PeopleDetail>(res);
}

export async function patchPersonWorkspaceCore(
  personId: number,
  payload: PeopleCorePatchPayload,
): Promise<PeoplePatchResult> {
  const res = await fetchWithTenant(`${API_BASE}/people/${personId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<PeoplePatchResult>(res);
}

export async function patchPersonDriverProfile(
  personId: number,
  payload: DriverProfilePatchPayload,
): Promise<PeoplePatchResult> {
  const res = await fetchWithTenant(`${API_BASE}/people/${personId}/driver-profile`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<PeoplePatchResult>(res);
}

export type PersonApplicationDocumentRequestPayload = {
  doc_types: string[];
  subject: string;
  body: string;
};

export type PersonApplicationDocumentRequestResult = {
  email_sent: boolean;
  email_error?: string | null;
};

/** Admin: combined document request email + rotate applicant resume token. */
export async function requestPersonApplicationDocuments(
  applicationId: number,
  payload: PersonApplicationDocumentRequestPayload,
): Promise<PersonApplicationDocumentRequestResult> {
  const res = await fetchWithTenant(
    `${API_BASE}/driver-onboarding/applications/${applicationId}/request-documents`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return handle<PersonApplicationDocumentRequestResult>(res);
}

/** Admin: upload a step-4 document on behalf of the applicant. */
export async function adminUploadPersonApplicationDocument(params: {
  applicationId: number;
  docType: string;
  file: File;
}): Promise<ApplicantApplication> {
  const form = new FormData();
  form.append("doc_type", params.docType);
  form.append("file", params.file);
  const res = await fetchWithTenant(
    `${API_BASE}/driver-onboarding/applications/${params.applicationId}/document-upload`,
    { method: "POST", body: form },
  );
  return handle<ApplicantApplication>(res);
}

/** Admin: mark document accepted or clear acceptance. */
export async function setPersonApplicationDocumentAccepted(params: {
  applicationId: number;
  docType: string;
  accepted: boolean;
}): Promise<ApplicantApplication> {
  const res = await fetchWithTenant(
    `${API_BASE}/driver-onboarding/applications/${params.applicationId}/documents/accept`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_type: params.docType, accepted: params.accepted }),
    },
  );
  return handle<ApplicantApplication>(res);
}

export async function patchPersonApplicationReviewFields(
  applicationId: number,
  payload: PersonApplicationReviewPatchPayload,
): Promise<ApplicantApplication> {
  const res = await fetchWithTenant(
    `${API_BASE}/driver-onboarding/applications/${applicationId}/review-fields`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
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

export type CombinedDriverApproveReadiness = {
  applies: boolean;
  ready: boolean;
  blocking_code?: string | null;
  detail?: string | null;
};

/** Combined tenant: create Person (+ driver entities) while SUBMITTED so admin setup cards can be used before approve. */
export async function materializePersonForCombinedSetup(applicationId: number): Promise<ApplicantApplication> {
  const res = await fetchWithTenant(
    `${API_BASE}/driver-onboarding/applications/${applicationId}/materialize-person-for-combined-setup`,
    { method: "POST" },
  );
  return handle<ApplicantApplication>(res);
}

/** Combined + DRIVER+DRIVER + SUBMITTED: whether required in-page setup is complete (Approve allowed). */
export async function getCombinedDriverApproveReadiness(
  applicationId: number,
): Promise<CombinedDriverApproveReadiness> {
  const res = await fetchWithTenant(
    `${API_BASE}/driver-onboarding/applications/${applicationId}/combined-driver-approve-readiness`,
  );
  return handle<CombinedDriverApproveReadiness>(res);
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

export async function completePersonApplicationOnboarding(id: number): Promise<ApplicantApplication> {
  const res = await fetchWithTenant(`${API_BASE}/driver-onboarding/applications/${id}/complete-onboarding`, {
    method: "POST",
  });
  return handle<ApplicantApplication>(res);
}

/** Combined-mode driver compensation (payees + compensation_profiles). */
export type DriverCompensationSetupOut = {
  payee_id: number | null;
  worker_type: string | null;
  gross_calc_type: string | null;
  percent_rate: string | null;
  cpm_loaded: string | null;
  cpm_empty: string | null;
  hourly_rate: string | null;
  salary_amount: string | null;
  flat_amount: string | null;
  settlement_frequency: string | null;
  participates_in_fuel_discount_program: boolean;
  dispatch_fee_enabled: boolean;
  dispatch_fee_rate: string;
  dispatch_fee_basis: string;
  employment_relationship_type: string | null;
};

export type DriverCompensationSetupWrite = {
  gross_calc_type: "CPM" | "PERCENT_REVENUE" | "FLAT_PER_LOAD" | "HOURLY" | "SALARY";
  percent_rate?: string | null;
  cpm_loaded?: string | null;
  cpm_empty?: string | null;
  hourly_rate?: string | null;
  salary_amount?: string | null;
  flat_amount?: string | null;
  settlement_frequency: string;
  participates_in_fuel_discount_program: boolean;
  dispatch_fee_enabled: boolean;
  dispatch_fee_rate: string;
  dispatch_fee_basis: string;
};

export async function getApplicationDriverCompensationSetup(
  applicationId: number,
): Promise<DriverCompensationSetupOut> {
  const res = await fetchWithTenant(
    `${API_BASE}/driver-onboarding/applications/${applicationId}/driver-compensation-setup`,
  );
  return handle<DriverCompensationSetupOut>(res);
}

export async function putApplicationDriverCompensationSetup(
  applicationId: number,
  payload: DriverCompensationSetupWrite,
): Promise<DriverCompensationSetupOut> {
  const res = await fetchWithTenant(
    `${API_BASE}/driver-onboarding/applications/${applicationId}/driver-compensation-setup`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return handle<DriverCompensationSetupOut>(res);
}

/** People workspace: same payload/read model as onboarding compensation (payees + compensation_profiles). */
export async function getPersonWorkspaceCompensationSetup(personId: number): Promise<DriverCompensationSetupOut> {
  const res = await fetchWithTenant(`${API_BASE}/people/${personId}/compensation-setup`);
  return handle<DriverCompensationSetupOut>(res);
}

export async function patchPersonWorkspaceCompensationSetup(
  personId: number,
  payload: DriverCompensationSetupWrite,
): Promise<PeoplePatchResult> {
  const res = await fetchWithTenant(`${API_BASE}/people/${personId}/compensation-setup`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<PeoplePatchResult>(res);
}

export type PersonSetupUiMode = "combined" | "segmented";

export async function patchPersonSetupUiMode(person_setup_ui_mode: PersonSetupUiMode): Promise<{ person_setup_ui_mode: string }> {
  const res = await fetchWithTenant(`${API_BASE}/admin/person-setup-ui-mode`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ person_setup_ui_mode }),
  });
  return handle<{ person_setup_ui_mode: string }>(res);
}

export async function patchDocRequestLinkExpiryDays(days: number): Promise<{ doc_request_link_expiry_days: number }> {
  const res = await fetchWithTenant(`${API_BASE}/admin/doc-request-link-expiry`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_request_link_expiry_days: days }),
  });
  return handle<{ doc_request_link_expiry_days: number }>(res);
}

/** Phase 3A driver extension (tenant admin + admin_sensitive). */
export type DriverPersonExtensionWrite = {
  employment_relationship_type: string;
  driver_operating_subtype: string;
  is_team_driver: boolean;
  team_role_type: string | null;
  provides_own_truck: boolean;
  provides_own_trailer: boolean;
  equipment_contribution_type: string;
  insurance_commercial_approved: boolean;
};

export type DriverPersonExtensionOut = DriverPersonExtensionWrite & {
  id: number;
  tenant_id: number;
  person_id: number;
  created_at: string;
  updated_at: string;
};

/** Returns null when no extension row exists (person must exist). */
export async function getDriverPersonExtension(personId: number): Promise<DriverPersonExtensionOut | null> {
  const res = await fetchWithTenant(`${API_BASE}/driver-person-extensions/${personId}`);
  if (res.status === 404) {
    const text = await res.text();
    let detail = "";
    try {
      detail = String((JSON.parse(text) as { detail?: unknown }).detail ?? "");
    } catch {
      /* ignore */
    }
    if (detail === "Person not found") {
      throw new Error("Person not found for driver configuration.");
    }
    if (detail === "Driver extension not found") return null;
    throw new Error(text || "Not found");
  }
  return handle<DriverPersonExtensionOut>(res);
}

export async function putDriverPersonExtension(
  personId: number,
  payload: DriverPersonExtensionWrite,
): Promise<DriverPersonExtensionOut> {
  const res = await fetchWithTenant(`${API_BASE}/driver-person-extensions/${personId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<DriverPersonExtensionOut>(res);
}

/**
 * People workspace: role-attached driver configuration (`driver_person_extensions`).
 * Returns null when no row exists yet (person must exist).
 */
export async function getPersonWorkspaceDriverRoleConfiguration(
  personId: number,
): Promise<DriverPersonExtensionOut | null> {
  const res = await fetchWithTenant(`${API_BASE}/people/${personId}/driver-role-configuration`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  const raw: unknown = await res.json();
  if (raw == null) return null;
  return raw as DriverPersonExtensionOut;
}

export async function patchPersonWorkspaceDriverRoleConfiguration(
  personId: number,
  payload: DriverPersonExtensionWrite,
): Promise<PeoplePatchResult> {
  const res = await fetchWithTenant(`${API_BASE}/people/${personId}/driver-role-configuration`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<PeoplePatchResult>(res);
}

/** Get person application by invite token (used on OnboardingApplicantPage). */
export async function getPersonApplicationByOnboardingToken(token: string): Promise<PersonApplication> {
  return getApplicantApplication(token);
}

/** SSE URL for invite-token application change signals (EventSource; no custom headers). */
export function buildApplicantApplicationEventsUrl(onboardingToken: string): string {
  const url = new URL(
    `${API_BASE}/driver-onboarding/applicant/application/events`,
    window.location.origin,
  );
  url.searchParams.set("token", onboardingToken);
  return url.toString().replace(window.location.origin, "");
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

export type DlCaptureLinkResult = {
  application_id: number;
  token: string;
  link: string;
  expires_at: string;
};

/** Issue restricted phone DL capture link (applicant invite token auth). */
export async function issueApplicantDlCaptureLink(onboardingToken: string): Promise<DlCaptureLinkResult> {
  const url = new URL(
    `${API_BASE}/driver-onboarding/applicant/application/dl-capture-link`,
    window.location.origin,
  );
  url.searchParams.set("token", onboardingToken);
  const res = await fetchWithTenant(url.toString().replace(window.location.origin, ""), {
    method: "POST",
  });
  return handle<DlCaptureLinkResult>(res);
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
  /** Present when API returns tenant person setup mode (combined vs segmented). */
  person_setup_ui_mode?: PersonSetupUiMode | string;
  /** Days a document-request applicant link stays valid (1–90, default 21). */
  doc_request_link_expiry_days?: number;
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

export type SignInSecurity = {
  sign_in_status: string;
  all_clear: boolean;
  reasons: string[];
  trigger_sources: string[];
  timestamps: Record<string, string | null>;
  restriction_summary: Record<string, unknown>;
  lock_scope: Record<string, unknown>;
  note: string;
};

export async function listTenantUsers(): Promise<UserMember[]> {
  const res = await fetchWithTenant(`${API_BASE}/admin/users`);
  return handle<UserMember[]>(res);
}

export async function getTenantUserSignInSecurity(userId: string): Promise<SignInSecurity> {
  const res = await fetchWithTenant(`${API_BASE}/admin/users/${encodeURIComponent(userId)}/sign-in-security`);
  return handle<SignInSecurity>(res);
}

export type InviteUserPayload = {
  username: string;
  email: string;
  phone?: string | null;
  access_level?: string;  // READ_ONLY | FULL_ACCESS
};

export async function inviteTenantUser(payload: InviteUserPayload): Promise<{
  ok: boolean;
  email: string;
  status: string;
  message: string;
  email_sent?: boolean;
}> {
  const res = await fetchWithTenant(`${API_BASE}/admin/users/invite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<{
    ok: boolean;
    email: string;
    status: string;
    message: string;
    email_sent?: boolean;
  }>(res);
}

export async function unlockTenantUserSignIn(userId: string): Promise<{
  ok: boolean;
  cleared: unknown;
  state_after: unknown;
  note: string;
  operator_message?: string;
}> {
  const res = await fetchWithTenant(`${API_BASE}/admin/users/${encodeURIComponent(userId)}/unlock-sign-in`, {
    method: "POST",
  });
  return handle<{
    ok: boolean;
    cleared: unknown;
    state_after: unknown;
    note: string;
    operator_message?: string;
  }>(res);
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

export async function resendTenantUserInvite(userId: string): Promise<{
  ok: boolean;
  email: string;
  message: string;
  email_sent?: boolean;
}> {
  const res = await fetchWithTenant(`${API_BASE}/admin/users/${encodeURIComponent(userId)}/resend-invite`, {
    method: "POST",
  });
  return handle<{ ok: boolean; email: string; message: string; email_sent?: boolean }>(res);
}

export async function removeTenantUserFromWorkspace(userId: string): Promise<{ ok: boolean; message: string }> {
  const res = await fetchWithTenant(`${API_BASE}/admin/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
  return handle<{ ok: boolean; message: string }>(res);
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
  imap_security?: string | null;
  smtp_host: string | null;
  smtp_port: number | null;
  smtp_username: string | null;
  smtp_security?: string | null;
  reply_to?: string | null;
  use_ssl: boolean | null;
  use_tls: boolean | null;
  oauth_provider: string | null;
  oauth_account_email: string | null;
  connection_status?: string | null;
  last_tested_at: string | null;
  last_test_status: string | null;
  last_inbound_test_at?: string | null;
  last_outbound_test_at?: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  /** Last successful IMAP sync (Other provider) or Gmail delta (ISO). */
  last_inbound_sync_at?: string | null;
  last_sync_status?: string | null;
  last_sync_error?: string | null;
  imap_uidvalidity?: number | null;
  imap_last_seen_uid?: number | null;
  gmail_history_cursor_present?: boolean | null;
  gmail_watch_active?: boolean | null;
  gmail_watch_expires_at?: string | null;
  last_gmail_webhook_at?: string | null;
  /** Server has GMAIL_PUBSUB_TOPIC_NAME (platform ops). */
  gmail_pubsub_topic_configured?: boolean | null;
  /** True only when push path is viable end-to-end per server checks (not “OAuth OK”). */
  gmail_automatic_ingestion_ready?: boolean | null;
  gmail_automatic_ingestion_blockers?: string[] | null;
  gmail_automatic_ingestion_warnings?: string[] | null;
  /** Microsoft 365 Graph (when primary is OAuth Microsoft account). */
  ms_graph_subscription_id?: string | null;
  ms_graph_subscription_status?: string | null;
  ms_graph_subscription_expiration_at?: string | null;
  ms_graph_delta_cursor_present?: boolean | null;
  ms_graph_last_notification_at?: string | null;
  ms_graph_last_delta_sync_at?: string | null;
  ms_graph_last_sync_status?: string | null;
  ms_graph_last_sync_error?: string | null;
  created_at: string;
  updated_at: string;
};

export type GmailIngestionHealth = {
  oauth_connected: boolean;
  gmail_pubsub_topic_configured: boolean;
  history_cursor_present: boolean;
  watch_registered_and_valid: boolean;
  watch_expires_at: string | null;
  last_webhook_at: string | null;
  last_delta_sync_at: string | null;
  automatic_ingestion_ready: boolean;
  blockers: string[];
  warnings: string[];
  proof_steps: string[];
};

export type EmailConfigUpdatePayload = {
  email_address: string;
  display_name?: string | null;
  reply_to?: string | null;
  mailbox_type?: string;
  provider_name?: string | null;
  connection_mode?: string;
  inbound_enabled?: boolean;
  outbound_enabled?: boolean;
  is_primary?: boolean;
  imap_host?: string | null;
  imap_port?: number | null;
  imap_username?: string | null;
  imap_password?: string | null;
  imap_security?: string | null;
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_username?: string | null;
  smtp_password?: string | null;
  smtp_security?: string | null;
  use_ssl?: boolean | null;
  use_tls?: boolean | null;
  oauth_provider?: string | null;
  oauth_account_email?: string | null;
  oauth_access_token?: string | null;
  oauth_refresh_token?: string | null;
};

export type EmailIntakeReviewCard = {
  id: number;
  primary_code: string;
  detail_json: Record<string, unknown> | null;
  status: string;
  claimed_by_tenant_user_id: number | null;
  claimed_at: string | null;
  resolved_at: string | null;
  dismissed_at: string | null;
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
  linked_trip_number?: string | null;
  linked_broker_name?: string | null;
  pickup_delivery_summary?: string | null;
  intake_review?: EmailIntakeReviewCard | null;
};

export type InboxThreadDetail = InboxThreadListItem;

export type EmailIntakeReviewRow = EmailIntakeReviewCard & {
  tenant_id: number;
  email_thread_id: number;
  last_routing_reason_snapshot: string | null;
  created_at: string;
  updated_at: string;
};

export type EmailIntakeReviewEventRow = {
  id: number;
  event_type: string;
  actor_kind: string;
  actor_tenant_user_id: number | null;
  actor_platform_user_id: string | null;
  old_value_json: Record<string, unknown> | null;
  new_value_json: Record<string, unknown> | null;
  reason_code: string | null;
  payload_note: string | null;
  created_at: string;
};

export type EmailIntakeReviewBundle = {
  review: EmailIntakeReviewRow | null;
  events: EmailIntakeReviewEventRow[];
};

export type InboxMessageAttachmentItem = {
  id: number;
  filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  is_inline: boolean;
  download_status: string;
  external_attachment_id: string;
};

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
  attachments?: InboxMessageAttachmentItem[];
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

export async function testPrimaryEmailConfig(): Promise<{
  ok: boolean;
  status: string;
  direction?: string | null;
  message?: string;
  last_tested_at?: string;
}> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/primary/test`, { method: "POST" });
  return handle(res);
}

export async function testPrimaryEmailInbound(): Promise<{
  ok: boolean;
  status: string;
  direction?: string | null;
  message?: string;
  last_tested_at?: string;
}> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/primary/test-inbound`, { method: "POST" });
  return handle(res);
}

export async function testPrimaryEmailOutbound(): Promise<{
  ok: boolean;
  status: string;
  direction?: string | null;
  message?: string;
  last_tested_at?: string;
}> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/primary/test-outbound`, { method: "POST" });
  return handle(res);
}

export async function syncOtherImapNow(maxMessages = 50): Promise<{
  ok: boolean;
  tenant_id: number;
  provider: string;
  threads_upserted: number;
  messages_upserted: number;
  attachments_upserted: number;
  uids_fetched: number;
}> {
  const res = await fetchWithTenant(
    `${API_BASE}/admin/email-config/other/sync-now?max_messages=${maxMessages}`,
    { method: "POST" },
  );
  return handle(res);
}

export async function disconnectPrimaryEmailConfig(): Promise<{ ok: boolean; message: string }> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/primary/disconnect`, { method: "POST" });
  return handle<{ ok: boolean; message: string }>(res);
}

export async function registerGmailWatch(): Promise<{
  ok: boolean;
  historyId?: string | null;
  gmail_watch_expires_at?: string | null;
}> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/gmail/register-watch`, { method: "POST" });
  return handle(res);
}

export async function renewGmailWatch(force = false): Promise<{
  ok: boolean;
  skipped?: string;
  gmail_watch_expires_at?: string | null;
  renew_within_hours?: number;
  historyId?: string | null;
}> {
  const q = force ? "?force=true" : "";
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/gmail/renew-watch${q}`, { method: "POST" });
  return handle(res);
}

export async function syncGmailNow(maxThreads = 30): Promise<{
  ok: boolean;
  tenant_id: number;
  provider: string;
  threads_scanned: number;
  threads_upserted: number;
  messages_upserted: number;
  attachments_upserted: number;
  history_pages?: number;
  last_sync_at?: string | null;
}> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/gmail/sync-now?max_threads=${maxThreads}`, {
    method: "POST",
  });
  return handle(res);
}

export async function getGmailIngestionHealth(): Promise<GmailIngestionHealth> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/gmail/ingestion-health`);
  return handle<GmailIngestionHealth>(res);
}

export async function getMicrosoftOAuthStatus(): Promise<{ oauth_configured: boolean }> {
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/microsoft/oauth-status`);
  return handle<{ oauth_configured: boolean }>(res);
}

export async function renewMicrosoftSubscription(force = false): Promise<{ ok: boolean; renewed: boolean }> {
  const q = force ? "?force=true" : "";
  const res = await fetchWithTenant(`${API_BASE}/admin/email-config/microsoft/renew-subscription${q}`, {
    method: "POST",
  });
  return handle<{ ok: boolean; renewed: boolean }>(res);
}

export async function syncMicrosoftNow(maxPages = 25): Promise<{
  ok: boolean;
  tenant_id: number;
  provider: string;
  messages_processed: number;
  delta_pages: number;
  delta_cursor_advanced: boolean;
}> {
  const res = await fetchWithTenant(
    `${API_BASE}/admin/email-config/microsoft/sync-now?max_pages=${maxPages}`,
    { method: "POST" },
  );
  return handle(res);
}

/** Same delta sync as Pub/Sub push; `email_inbox` entitlement. Fallback only — production uses Gmail push. */
export async function pullGmailDeltaFromInbox(maxThreads = 30): Promise<{
  ok: boolean;
  tenant_id: number;
  provider: string;
  threads_scanned: number;
  threads_upserted: number;
  messages_upserted: number;
  attachments_upserted: number;
  history_pages?: number;
  last_sync_at?: string | null;
}> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/gmail/pull-delta?max_threads=${maxThreads}`, {
    method: "POST",
  });
  return handle(res);
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

export async function getEmailThreadIntakeReview(threadId: number): Promise<EmailIntakeReviewBundle> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/intake-review`);
  return handle<EmailIntakeReviewBundle>(res);
}

export async function getEmailThreadMessages(threadId: number): Promise<InboxMessageItem[]> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/messages`);
  return handle<InboxMessageItem[]>(res);
}

export async function disregardEmailThread(threadId: number): Promise<InboxThreadDetail> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/disregard`, { method: "POST" });
  return handle<InboxThreadDetail>(res);
}

export async function recomputeEmailThreadIntake(threadId: number): Promise<InboxThreadDetail> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/recompute-intake`, { method: "POST" });
  return handle<InboxThreadDetail>(res);
}

export async function uploadPdfToEmailThread(threadId: number, file: File): Promise<InboxThreadDetail> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/upload-pdf`, {
    method: "POST",
    body: form,
  });
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

/** Duplicate review: link thread to suggested prior load (or same id as review detail). */
export async function duplicateIntakeReviewLinkPrior(
  threadId: number,
  body: { prior_load_id?: number | null } = {},
): Promise<EmailThreadDraftOrLinkResult> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/intake-review/duplicate/link-prior`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prior_load_id: body.prior_load_id ?? null }),
  });
  return handle<EmailThreadDraftOrLinkResult>(res);
}

export async function duplicateIntakeReviewConfirm(threadId: number, note?: string | null): Promise<EmailIntakeReviewRow> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/intake-review/duplicate/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note: note ?? null }),
  });
  return handle<EmailIntakeReviewRow>(res);
}

export async function duplicateIntakeReviewDismissFalsePositive(
  threadId: number,
  note?: string | null,
): Promise<EmailIntakeReviewRow> {
  const res = await fetchWithTenant(
    `${API_BASE}/email-threads/${threadId}/intake-review/duplicate/dismiss-false-positive`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: note ?? null }),
    },
  );
  return handle<EmailIntakeReviewRow>(res);
}

/** Resolve intake review — reason_code must be from shared JSON resolve.write set. */
export async function resolveEmailThreadIntakeReview(
  threadId: number,
  body: { reason_code: string; note?: string | null },
): Promise<EmailIntakeReviewRow> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/intake-review/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason_code: body.reason_code, note: body.note ?? null }),
  });
  return handle<EmailIntakeReviewRow>(res);
}

/** Dismiss intake review — reason_code from shared dismiss.write set. */
export async function dismissEmailThreadIntakeReview(
  threadId: number,
  body: { reason_code: string; note?: string | null },
): Promise<EmailIntakeReviewRow> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/intake-review/dismiss`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason_code: body.reason_code, note: body.note ?? null }),
  });
  return handle<EmailIntakeReviewRow>(res);
}

/** Reopen closed intake review — reason_code from shared reopen.write set. */
export async function reopenEmailThreadIntakeReview(
  threadId: number,
  body: { reason_code: string; note?: string | null },
): Promise<EmailIntakeReviewRow> {
  const res = await fetchWithTenant(`${API_BASE}/email-threads/${threadId}/intake-review/reopen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason_code: body.reason_code, note: body.note ?? null }),
  });
  return handle<EmailIntakeReviewRow>(res);
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
  charge_category_code?: string | null;
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
  requires_otp?: boolean;
  signup_id?: string | null;
  tenant_slug?: string;
  redirect_url?: string;
  message?: string;
  user_id?: number;
  tenant_id?: number;
  email?: string;
  debug_otp?: string | null;
  code?: string;
  next_step?: string;
};

export type VerifyOtpRequest = {
  email: string;
  otp: string;
  signup_id?: string | null;
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
  legal_name?: string | null;
  display_name?: string | null;
  mc_number?: string | null;
  dot_number?: string | null;
  scac?: string | null;
  phone?: string | null;
  phone_secondary?: string | null;
  email?: string | null;
  email_secondary?: string | null;
  website?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  address_city?: string | null;
  address_region?: string | null;
  address_postal?: string | null;
  address_country?: string | null;
  classification_notes?: string | null;
  internal_notes?: string | null;
  notes?: string | null;
  is_active?: boolean;
  archived_at?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type CustomsBrokerSummary = {
  id: number;
  legal_name: string;
  is_active: boolean;
  phone_primary?: string | null;
};

export type LoadCustomsSnapshot = {
  load_id: number;
  tenant_id: number;
  legal_name_snapshot?: string | null;
  address_line1_snapshot?: string | null;
  address_line2_snapshot?: string | null;
  city_snapshot?: string | null;
  admin_area_snapshot?: string | null;
  postal_code_snapshot?: string | null;
  country_code_snapshot?: string | null;
  phone_primary_snapshot?: string | null;
  phone_secondary_snapshot?: string | null;
  fax_snapshot?: string | null;
  generic_email_snapshot?: string | null;
  website_url_snapshot?: string | null;
  customs_broker_id_at_confirm?: number | null;
  confirmed_at: string;
};

/** Shape returned by the API — includes server-assigned fields. */
export type LoadStopRead = {
  id: number;
  load_id: number;
  stop_type: string;
  sequence: number;
  facility_name?: string | null;
  street?: string | null;
  city?: string | null;
  state_or_province?: string | null;
  postal_code?: string | null;
  country?: string | null;
  reference_number?: string | null;
  appointment_type?: string | null;
  appointment_date?: string | null;
  appointment_time_text?: string | null;
  scheduled_at?: string | null;
  notes?: string | null;
  commodity_notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

/** Backward-compat alias — use LoadStopRead for read paths, LoadStopWrite for write paths. */
export type LoadStop = LoadStopRead;

/** Shape sent to the API on create/update — no server-assigned fields. */
export type LoadStopWrite = {
  id?: number;
  stop_type: string;
  sequence: number;
  facility_name?: string | null;
  street?: string | null;
  city?: string | null;
  state_or_province?: string | null;
  postal_code?: string | null;
  country?: string | null;
  reference_number?: string | null;
  appointment_type?: string | null;
  appointment_date?: string | null;
  appointment_time_text?: string | null;
  notes?: string | null;
  commodity_notes?: string | null;
};

/** Payload shape for load create/update — stops use the write shape (no server-assigned stop fields). */
export type LoadWritePayload = Omit<Partial<Load>, "stops"> & { stops?: LoadStopWrite[] | null };

export type Load = {
  id: number;
  load_number: string | null;
  customs_broker_id?: number | null;
  customs_broker?: CustomsBrokerSummary | null;
  document_snapshot_confirmed_at?: string | null;
  document_snapshot_confirmed_by_user_id?: string | null;
  document_snapshot_version?: number;
  customs_snapshot?: LoadCustomsSnapshot | null;
  broker_load_reference?: string | null;
  broker_name_snapshot?: string | null;
  broker_contact_name_snapshot?: string | null;
  broker_contact_phone_snapshot?: string | null;
  broker_contact_extension_snapshot?: string | null;
  broker_contact_email_snapshot?: string | null;
  broker_id?: number | null;
  broker_contact_id?: number | null;
  driver_id?: number | null;
  truck_id?: number | null;
  trailer_id?: number | null;
  pickup_date?: string | null;
  delivery_date?: string | null;
  pickup_time?: string | null;
  delivery_time?: string | null;
  pickup_location?: string | null;
  delivery_location?: string | null;
  mode?: string | null;
  equipment_type?: string | null;
  trailer_type?: string | null;
  trailer_size?: string | null;
  commodity?: string | null;
  estimated_weight?: number | null;
  hazmat_flag?: boolean | null;
  temperature_requirement?: string | null;
  pallet_case_count?: string | null;
  internal_notes?: string | null;
  rate?: number | null;
  customer_rate?: number | null;
  miles?: number | null;
  /** Denormalized from active dispatch trip; read-only in UI. */
  trip_number?: string | null;
  active_dispatch_trip_id?: number | null;
  /** Mirrored from trips when assigned; use trip workspace for operational view. */
  active_trip_id?: number | null;
  broker_match_method?: string | null;
  broker_match_confidence_tier?: string | null;
  broker_match_explanation?: string | null;
  review_required?: boolean;
  is_duplicate_of_load_id?: number | null;
  status: string;
  broker?: Broker | null;
  broker_contact?: {
    id: number;
    broker_id: number;
    name: string;
    phone?: string | null;
    extension?: string | null;
    email?: string | null;
  } | null;
  driver?: {
    id: number;
    first_name: string;
    last_name: string;
    phone?: string | null;
    email?: string | null;
  } | null;
  truck?: { id: number; unit_number: string } | null;
  trailer?: { id: number; unit_number: string; trailer_type?: string | null } | null;
  stops?: LoadStop[] | null;
  created_at?: string | null;
  updated_at?: string | null;
  /** Optimistic concurrency token; required on mutating requests (CAS). */
  concurrency_version?: number;
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
    trip_number?: string | null;
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
  /** Present on list responses when tenant schema includes license fields. */
  license_expiry_date?: string | null;
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
  zip_code?: string | null;
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
  zip_code?: string;
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
