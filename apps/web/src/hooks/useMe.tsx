import { createContext, ReactNode, useContext } from "react";
import { useLocation } from "react-router-dom";
import { useFetch } from "./useFetch";
import { useAuth } from "../contexts/AuthContext";

export type MeResponse = {
  user_id: number | null;
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

const PUBLIC_PATHS = ["/", "/signup", "/login", "/forgot-password", "/reset-password", "/accept-invite", "/company-setup", "/account-setup", "/onboarding"];

export function MeProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { authReady, isValid, isLoggingOut } = useAuth();
  const isPublicPath = PUBLIC_PATHS.some((p) => p === location.pathname || location.pathname.startsWith(p + "/"));
  // Only fetch /me after auth bootstrap completes and we're authenticated; never during logout
  const enabled = !isPublicPath && authReady && isValid && !isLoggingOut;
  // Use auth/me (authoritative DB-backed role) so AdminRouteGuard sees correct roles on hard refresh
  const { data, loading, error } = useFetch<Record<string, unknown>>("/api/v1/auth/me", [], enabled);
  // Normalize auth/me response (role) to MeResponse (roles array)
  const me: MeResponse | null = data
    ? {
        user_id: (data.user_id as number) ?? null,
        tenant_id: (data.tenant_id as number) ?? 0,
        roles: Array.isArray(data.roles)
          ? (data.roles as string[])
          : data.role
            ? [String(data.role)]
            : [],
        requires_account_setup: data.requires_account_setup as boolean | undefined,
        account_setup_missing: (data.account_setup_missing as string[] | undefined) ?? undefined,
        country_code: (data.country_code as string | null) ?? undefined,
        tenant_slug: (data.tenant_slug as string | null) ?? undefined,
      }
    : null;
  // While disabled (auth not ready), report loading so guards don't redirect on me=null
  const effectiveLoading = !enabled || loading;
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
