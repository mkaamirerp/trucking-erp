import { createContext, ReactNode, useContext, useMemo } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import type { SessionData } from "../utils/sessionCheck";

export type MeResponse = {
  /** Platform user id (UUID string from API). */
  user_id: number | string | null;
  email?: string | null;
  /** Present in tenant_auth_mode=tenant: tenant_users.id for this workspace. */
  tenant_local_user_id?: number | null;
  tenant_auth_mode?: string | null;
  tenant_id: number;
  roles: string[];
  requires_account_setup?: boolean;
  account_setup_missing?: string[];
  country_code?: string | null;
  tenant_slug?: string | null;
};

type MeContextValue = {
  me: MeResponse | null;
  loading: boolean;
  error: string | null;
};

const MeContext = createContext<MeContextValue>({ me: null, loading: true, error: null });

/** Same shape as useFetch+auth/me had; data comes from AuthContext (checkSession already calls /auth/me). */
function sessionToMe(session: SessionData | null): MeResponse | null {
  if (!session) return null;
  return {
    user_id: session.user_id ?? null,
    email: session.email,
    tenant_local_user_id:
      session.tenant_local_user_id != null ? Number(session.tenant_local_user_id) : null,
    tenant_auth_mode: session.tenant_auth_mode ?? undefined,
    tenant_id: session.tenant_id ?? 0,
    roles: Array.isArray(session.roles)
      ? session.roles
      : session.role
        ? [String(session.role)]
        : [],
    requires_account_setup: session.requires_account_setup,
    account_setup_missing: session.account_setup_missing ?? undefined,
    country_code: session.country_code ?? undefined,
    tenant_slug: session.tenant_slug ?? undefined,
  };
}

const PUBLIC_PATHS = [
  "/",
  "/signup",
  "/login",
  "/forgot-password",
  "/reset-password",
  "/accept-invite",
  "/company-setup",
  "/account-setup",
  "/onboarding",
  "/create-workspace",
];

export function MeProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { authReady, isValid, isLoggingOut, session } = useAuth();
  const isPublicPath = PUBLIC_PATHS.some((p) => p === location.pathname || location.pathname.startsWith(p + "/"));
  // Same gate as before; /me payload is session (validateSession -> checkSession -> GET /auth/me only once)
  const enabled = !isPublicPath && authReady && isValid && !isLoggingOut;
  const me = useMemo(() => (enabled ? sessionToMe(session) : null), [enabled, session]);
  const error: string | null = null;
  const effectiveLoading = !enabled || (enabled && session == null);
  return <MeContext.Provider value={{ me, loading: effectiveLoading, error }}>{children}</MeContext.Provider>;
}

export function useMe() {
  return useContext(MeContext);
}

export function hasRole(me: MeResponse | null, role: string) {
  if (!me) return false;
  const target = role.toUpperCase();
  return (me.roles || []).map((r) => r.toUpperCase()).includes(target);
}

/** Temporary: centralized in auth/roles. Replace with RBAC later. */
export { isTenantAdmin, hasFullAccess } from "../auth/roles";
