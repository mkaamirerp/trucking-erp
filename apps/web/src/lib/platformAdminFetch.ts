/**
 * Centralized fetch for /api/v1/platform/* (X-Platform-Admin-Key).
 * Short-term: key in sessionStorage. Later: httpOnly cookie or server-side proxy.
 */

const STORAGE_KEY = "platform_admin_api_key";

const API_BASE = (import.meta.env.VITE_API_BASE || "/api/v1").replace(/\/$/, "");

export function getPlatformAdminApiKey(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem(STORAGE_KEY) || "";
}

export function setPlatformAdminApiKey(key: string): void {
  if (typeof window === "undefined") return;
  if (key.trim()) {
    sessionStorage.setItem(STORAGE_KEY, key.trim());
  } else {
    sessionStorage.removeItem(STORAGE_KEY);
  }
}

export class PlatformAdminUnauthorizedError extends Error {
  override readonly name = "PlatformAdminUnauthorizedError";
  constructor(message = "Unauthorized. Enter a valid platform admin API key.") {
    super(message);
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class PlatformAdminHttpError extends Error {
  override readonly name = "PlatformAdminHttpError";
  constructor(
    message: string,
    public readonly status: number,
    public readonly bodyText: string,
  ) {
    super(message);
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * @param path Path after /api/v1, e.g. `/platform/tenants` or `/platform/tenants/1`.
 */
export async function platformAdminFetch(path: string, init?: RequestInit): Promise<Response> {
  const rel = path.startsWith("/") ? path : `/${path}`;
  const url = `${API_BASE}${rel}`;

  const headers = new Headers(init?.headers);
  const key = getPlatformAdminApiKey();
  if (key) {
    headers.set("X-Platform-Admin-Key", key);
  }
  if (init?.body != null && !headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(url, { ...init, headers });

  if (res.status === 401) {
    throw new PlatformAdminUnauthorizedError();
  }

  return res;
}

export async function platformAdminJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await platformAdminFetch(path, init);
  const text = await res.text();
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = JSON.parse(text) as { detail?: unknown };
      if (typeof j.detail === "string") {
        msg = j.detail;
      } else if (j.detail != null && typeof j.detail === "object" && "detail" in j.detail) {
        const inner = (j.detail as { detail?: string }).detail;
        if (typeof inner === "string") msg = inner;
      }
    } catch {
      if (text) msg = text.slice(0, 200);
    }
    throw new PlatformAdminHttpError(msg, res.status, text);
  }
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}
