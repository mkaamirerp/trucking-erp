/**
 * Session validation utility
 * Always validates session with server - never relies on client-side token existence
 */

import { authErrorToMessage } from "./authErrorToMessage";

const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

export type SessionCheckResult = 
  | { valid: true; data: SessionData }
  | { valid: false; status: number; error: string };

export type SessionData = {
  user_id: number | string;
  tenant_local_user_id?: number | null;
  tenant_auth_mode?: string | null;
  email?: string;
  first_name?: string;
  last_name?: string;
  tenant_id: number;
  tenant_slug?: string | null;
  tenant_name?: string;
  role?: string | null;
  roles?: string[]; // For backward compatibility
  email_verified?: boolean;
  requires_account_setup?: boolean;
  account_setup_missing?: string[];
  country_code?: string | null;
  theme?: string | null;
};

/**
 * Check session validity by calling API_BASE/auth/me
 * This endpoint uses get_current_user dependency which properly validates JWT/cookies
 * and returns current user info with full authentication check
 * 
 * @returns SessionCheckResult indicating if session is valid
 */
export async function checkSession(): Promise<SessionCheckResult> {
  try {
    const response = await fetch(`${API_BASE}/auth/me`, {
      method: "GET",
      credentials: "include", // Include cookies
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (response.status === 200) {
      const data = await response.json();
      // Normalize response: auth/me returns 'role' (singular), but we need 'roles' (array) for compatibility
      const normalizedData: SessionData = {
        ...data,
        tenant_local_user_id:
          data.tenant_local_user_id != null ? Number(data.tenant_local_user_id) : undefined,
        tenant_auth_mode: (data.tenant_auth_mode as string | null) ?? undefined,
        roles: data.roles || (data.role ? [data.role] : []),
      };
      return { valid: true, data: normalizedData };
    }

    // 401 Unauthorized or 403 Forbidden
    if (response.status === 401 || response.status === 403) {
      const errorText = await response.text().catch(() => "Session expired");
      return {
        valid: false,
        status: response.status,
        error: authErrorToMessage(response.status, errorText || "Session expired"),
      };
    }

    // Other errors
    const errorText = await response.text().catch(() => "Session check failed");
    return {
      valid: false,
      status: response.status,
      error: authErrorToMessage(response.status, errorText || "Session check failed"),
    };
  } catch (error) {
    // Network errors, etc.
    return { 
      valid: false, 
      status: 0, 
      error: error instanceof Error ? error.message : "Network error" 
    };
  }
}

/**
 * Keys that may hold auth/session/tenant data — clear all on logout so no traces remain.
 * Covers: tokens, user/me cache, signup/setup flow state, tenant/slug used during setup.
 */
const SENSITIVE_STORAGE_KEYS = [
  "auth_token",
  "access_token",
  "refresh_token",
  "user",
  "me",
  "setup_tenant_id",
  "setup_slug",
  "signupDraft",
];

export type ClearAuthStorageOptions = {
  /** When false, only clears client storage — use after a best-effort POST /auth/logout already ran (e.g. user logout). Default true. */
  notifyServer?: boolean;
};

/**
 * Clear all auth-related storage so no traces remain in the browser.
 * Optionally POST /auth/logout to clear HttpOnly cookies (default: one best-effort request).
 */
export function clearAuthStorage(options?: ClearAuthStorageOptions): void {
  SENSITIVE_STORAGE_KEYS.forEach((key) => {
    try {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    } catch {
      // Ignore if storage unavailable (e.g. private mode)
    }
  });

  if (options?.notifyServer === false) return;

  fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  }).catch(() => {
    // Ignore errors — client storage is cleared; cookies may still be cleared by response
  });
}

/**
 * Logout and clear all traces; returns a promise that resolves when server cookies are cleared.
 * Prefer this when you need to wait before redirecting (e.g. ensure cookies gone).
 */
export async function logoutAndClearTraces(): Promise<void> {
  SENSITIVE_STORAGE_KEYS.forEach((key) => {
    try {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    } catch {
      // Ignore
    }
  });

  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } catch {
    // Client storage already cleared
  }
}
