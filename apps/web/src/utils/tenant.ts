/**
 * Derive tenant slug from current hostname.
 *
 * Examples:
 *   truckerp.me            -> null
 *   www.truckerp.me        -> null
 *   apitestjwt5.truckerp.me -> "apitestjwt5"
 *   localhost / 127.0.0.1  -> null
 */
export function getTenantSlugFromHost(): string | null {
  // In SSR / tests, window might be undefined
  if (typeof window === "undefined") return null;

  const host = window.location.hostname.toLowerCase().trim();

  // Local/dev hosts: treat as "main domain"
  if (host === "localhost" || host === "127.0.0.1") return null;

  const parts = host.split(".").filter(Boolean);

  // Need at least: <slug>.truckerp.me  => 3 parts
  if (parts.length < 3) return null;

  // Ignore www.<domain>
  if (parts[0] === "www") return null;

  return parts[0] || null;
}
