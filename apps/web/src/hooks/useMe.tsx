import { createContext, ReactNode, useContext } from "react";
import { useFetch } from "./useFetch";

export type MeResponse = {
  user_id: number | null;
  tenant_id: number;
  roles: string[];
};

type MeContextValue = {
  me: MeResponse | null;
  loading: boolean;
  error: string | null;
};

const MeContext = createContext<MeContextValue>({ me: null, loading: true, error: null });

export function MeProvider({ children }: { children: ReactNode }) {
  const { data, loading, error } = useFetch<MeResponse>("/api/v1/me", []);
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
