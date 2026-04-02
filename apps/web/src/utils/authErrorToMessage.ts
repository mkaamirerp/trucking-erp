/**
 * Maps API auth/tenant error (status + body) to a user-friendly message.
 * Use for 401/403 from /me, tenant middleware, login, or any auth check.
 */
export function authErrorToMessage(status: number, bodyOrMessage: string): string {
  let detail = bodyOrMessage?.trim() || "";
  try {
    if (detail.startsWith("{")) {
      const json = JSON.parse(detail) as { detail?: string };
      detail = (json.detail ?? "").trim();
    }
  } catch {
    // Keep original if not JSON
  }

  const d = detail.toLowerCase();

  // Login form: no account for this email (e.g. fresh DB / wrong workspace)
  if (d.includes("no account exists with this email")) {
    return "No account exists with this email. Sign up for this workspace or try a different email.";
  }
  // Login form: invalid credentials
  if (d.includes("invalid email or password")) {
    return "Invalid email or password. Try again or use Forgot password.";
  }

  // Session / token (only use "expired" when it's clearly a token issue)
  if (d.includes("token expired") || d.includes("invalid token") || d.includes("invalid refresh token") || d.includes("missing refresh token")) {
    return "Your session has ended. Please sign in again.";
  }
  // "Not authenticated" = no token or not logged in (neutral message so it fits both first visit and expired session)
  if (d.includes("not authenticated")) {
    return "Please sign in to continue.";
  }

  // Tenant / access
  if (d.includes("user does not have access") || d.includes("not part of tenant") || d.includes("user membership not found")) {
    return "You don't have access to this workspace. Sign in with an account that has access, or contact your admin.";
  }
  if (d.includes("tenant not found") || d.includes("tenant context required") || d.includes("tenant not ready")) {
    return "This workspace isn't available. Check the URL or try again later.";
  }
  if (d.includes("tenant slug required") || d.includes("company subdomain")) {
    return "Use your company sign-in URL (e.g. yourcompany.truckerp.me) to log in.";
  }

  // JWT/host workspace mismatch — keep wording that forceWorkspaceRelogin detectors can recognize
  if (d.includes("workspace") && (d.includes("match") || d.includes("host"))) {
    return detail || "Open the app from your workspace URL and sign in again.";
  }

  // Fallbacks by status
  if (status === 401) return "Sign in with your email and password, or sign up if you don't have an account.";
  if (status === 403) return "You don't have access. Please sign in with an account that has access to this workspace.";
  if (detail) return detail;
  return "Something went wrong. Please try again.";
}
