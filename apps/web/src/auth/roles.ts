/**
 * Temporary tenant admin access. Mirrors app/deps/admin.py.
 * Replace with RBAC when locked. Do not scatter role checks elsewhere.
 */

const TENANT_ADMIN_ROLES = new Set(["OWNER", "ADMIN", "TENANT_ADMIN", "TENANT_OWNER"]);
const FULL_ACCESS_ROLES = new Set(["OWNER", "ADMIN", "TENANT_ADMIN", "TENANT_OWNER"]);

export function isTenantAdmin(roles: string[] | null | undefined): boolean {
  if (!roles?.length) return false;
  return roles.some((r) => TENANT_ADMIN_ROLES.has(r.trim().toUpperCase()));
}

/** True if role has FULL_ACCESS (can invite, suspend, reactivate). READ_ONLY = false. */
export function hasFullAccess(roles: string[] | null | undefined): boolean {
  if (!roles?.length) return false;
  return roles.some((r) => FULL_ACCESS_ROLES.has(r.trim().toUpperCase()));
}
