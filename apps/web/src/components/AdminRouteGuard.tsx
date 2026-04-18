import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useMe, isTenantAdmin } from "../hooks/useMe";

type Props = {
  children: ReactNode;
};

/**
 * Temporary gating. TENANT_MEMBER (READ_ONLY) can access /admin/users only — no other admin pages.
 * FULL_ACCESS (TENANT_ADMIN, TENANT_OWNER) can access all admin routes.
 */
export default function AdminRouteGuard({ children }: Props) {
  const { me, loading } = useMe();
  const location = useLocation();
  const isUsersPath = location.pathname === "/admin/users" || location.pathname.startsWith("/admin/users/");

  // Wait for /me; never redirect when me is null (could be transient state on hard refresh)
  if (loading || !me) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--trk-text-muted)]">
        Loading...
      </div>
    );
  }

  const isAdmin = isTenantAdmin(me.roles ?? []);
  const isMemberOnly = (me.roles ?? []).some(
    (r) => ["TENANT_MEMBER", "MEMBER"].includes(r.trim().toUpperCase())
  ) && !isAdmin;

  // TENANT_MEMBER exception: /admin/users only. All other admin paths require full admin.
  if (isMemberOnly && !isUsersPath) {
    return <Navigate to="/dashboard" replace state={{ message: "Admin access required" }} />;
  }
  if (isUsersPath && (isAdmin || isMemberOnly)) {
    return <>{children}</>;
  }
  if (isAdmin) {
    return <>{children}</>;
  }

  return <Navigate to="/dashboard" replace state={{ message: "Admin access required" }} />;
}
