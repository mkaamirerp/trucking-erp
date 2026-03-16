import { createContext, ReactNode, useContext } from "react";
import { useLocation } from "react-router-dom";
import { useFetch } from "./useFetch";

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
  const isPublicPath = PUBLIC_PATHS.some((p) => p === location.pathname || location.pathname.startsWith(p + "/"));
  const { data, loading, error } = useFetch<MeResponse>("/api/v1/me", [], isPublicPath ? false : true);
  return <MeContext.Provider value={{ me: data, loading, error }}>{children}</MeContext.Provider>;
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
