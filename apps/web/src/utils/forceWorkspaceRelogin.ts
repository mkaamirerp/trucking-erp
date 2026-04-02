import { clearAuthStorage } from "./sessionCheck";
import { getTenantSlugFromHost } from "../tenant";

/** Full page navigation to login after server rejected the session (sv/mode/workspace mismatch). */
export function forceWorkspaceRelogin(): void {
  if (typeof window === "undefined") return;
  clearAuthStorage();
  const slug = getTenantSlugFromHost();
  window.location.assign(slug ? `/login?workspace=${encodeURIComponent(slug)}` : "/login");
}

export function shouldForceReloginFrom403Body(body: string): boolean {
  const t = (body || "").toLowerCase();
  return t.includes("workspace") && (t.includes("match") || t.includes("host"));
}
