/**
 * Maps API auth/tenant error (status + body) to a user-friendly message.
 * Use for 401/403 from /me, tenant middleware, login, or any auth check.
 *
 * Rules: 5xx → server error; invalid-credentials copy only for 401 + exact server detail;
 * never let generic 401/403 fallbacks replace an explicit server detail.
 */

const SERVER_ERROR_USER_MESSAGE = "Server error — contact support.";
/** FastAPI login invalid-credentials detail — must match for friendly copy (case-insensitive). */
const INVALID_CREDENTIALS_SERVER_DETAIL = "invalid email or password";
const INVALID_CREDENTIALS_USER_MESSAGE =
  "Invalid email or password. Try again or use Forgot password.";

function parseDetail(bodyOrMessage: string): string {
  const raw = (bodyOrMessage ?? "").trim();
  if (!raw.startsWith("{")) {
    return raw;
  }
  try {
    const json = JSON.parse(raw) as { detail?: unknown };
    const d = json.detail;
    if (typeof d === "string") {
      return d.trim();
    }
  } catch {
    // keep raw
  }
  return raw;
}

export function authErrorToMessage(status: number, bodyOrMessage: string): string {
  const detail = parseDetail(bodyOrMessage);
  const d = detail.toLowerCase();

  if (status >= 500 && status <= 599) {
    return SERVER_ERROR_USER_MESSAGE;
  }

  // Login form: no account for this email (e.g. fresh DB / wrong workspace)
  if (d.includes("no account exists with this email")) {
    return "No account exists with this email. Sign up for this workspace or try a different email.";
  }

  // Session / token (only use "expired" when it's clearly a token issue)
  if (
    d.includes("token expired") ||
    d.includes("invalid token") ||
    d.includes("invalid refresh token") ||
    d.includes("missing refresh token")
  ) {
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

  // Intentional auth messages: preserve server wording (do not replace with generic 401 text)
  if (d.includes("password not set")) {
    return detail;
  }

  // 401 + exact invalid-credentials detail only (not substring matches on HTML/body noise)
  if (status === 401 && d === INVALID_CREDENTIALS_SERVER_DETAIL) {
    return INVALID_CREDENTIALS_USER_MESSAGE;
  }

  if (detail) {
    return detail;
  }

  if (status === 401) {
    return "Sign in with your email and password, or sign up if you don't have an account.";
  }
  if (status === 403) {
    return "You don't have access. Please sign in with an account that has access to this workspace.";
  }
  return "Something went wrong. Please try again.";
}
