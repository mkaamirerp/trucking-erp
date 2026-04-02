import React, { createContext, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import { getTenantStatus } from "../api";
import { getTenantSlugFromHost } from "../tenant";

type TenantStatus = {
  exists: boolean;
  ready: boolean;
  status?: string;
  reason?: string;
};

type TenantContextType = {
  slug: string | null;
  tenantStatus: TenantStatus | null;
  isValidating: boolean;
  isValid: boolean;
};

const TenantContext = createContext<TenantContextType | undefined>(undefined);

export function TenantProvider({ children }: { children: ReactNode }) {
  const slug = getTenantSlugFromHost();

  const [tenantStatus, setTenantStatus] = useState<TenantStatus | null>(null);
  const [isValidating, setIsValidating] = useState<boolean>(!!slug);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      if (!slug) {
        setTenantStatus(null);
        setIsValidating(false);
        return;
      }

      setIsValidating(true);
      try {
        const status = await getTenantStatus(slug);
        if (!cancelled) setTenantStatus(status);
      } catch (e: any) {
        if (!cancelled) {
          setTenantStatus({ exists: true, ready: false, reason: e?.message || "Tenant not ready" });
        }
      } finally {
        if (!cancelled) setIsValidating(false);
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const isValid = useMemo(() => {
    if (!slug) return true; // main domain: don't gate on tenant
    if (!tenantStatus) return false;
    return tenantStatus.exists && tenantStatus.ready;
  }, [slug, tenantStatus]);

  const value: TenantContextType = { slug, tenantStatus, isValidating, isValid };

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant(): TenantContextType {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error("useTenant must be used within a TenantProvider");
  return ctx;
}
