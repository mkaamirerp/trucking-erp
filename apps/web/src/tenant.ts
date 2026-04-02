/**
 * Extract tenant slug from hostname
 * Examples:
 * - demo.truckerp.me -> demo
 * - truckerp.me -> null (main domain)
 * - www.truckerp.me -> null (reserved)
 * - localhost -> null
 */
export function getTenantSlugFromHost(): string | null {
  if (typeof window === "undefined") return null;

  const hostname = window.location.hostname.toLowerCase();

  // Local / LAN dev hosts
  if (
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname.startsWith("192.168.") ||
    hostname.startsWith("10.")
  ) {
    return null;
  }

  const base = "truckerp.me";

  // Main domain (apex)
  if (hostname === base) return null;

  // Must be a subdomain of truckerp.me
  if (!hostname.endsWith("." + base)) return null;

  const sub = hostname.slice(0, -(base.length + 1)); // remove ".truckerp.me"
  if (!sub) return null;

  // Reserved subdomains that should NOT be treated as tenants
  const reserved = new Set(["www", "api", "app"]);
  if (reserved.has(sub)) return null;

  // Reject obviously invalid slugs (optional hardening)
  if (!/^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/.test(sub)) return null;

  return sub;
}

/**
 * Origin where `/platform` works (apex hostname). On workspace hosts like `demo.truckerp.me`,
 * the control plane is served from the bare domain (same pattern as {@link getTenantSlugFromHost}).
 */
export function getControlPlaneBaseUrl(): string {
  if (typeof window === "undefined") {
    return "";
  }
  const { protocol, hostname } = window.location;
  const hostLower = hostname.toLowerCase();
  const base = "truckerp.me";
  const suffix = "." + base;
  if (hostLower.endsWith(suffix)) {
    const sub = hostLower.slice(0, -suffix.length);
    if (sub && sub !== "www" && sub !== "api" && sub !== "app") {
      return `${protocol}//${base}`;
    }
  }
  return `${protocol}//${hostname}`;
}
