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

/** Normalize paste from SSM console / email (CRLF, stray whitespace). */
export function normalizePlatformAdminKeyInput(key: string): string {
  return key.replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/\n/g, "").trim();
}

/** Preflight key against GET /platform/tenants (no throw). Use before persisting to sessionStorage. */
export async function verifyPlatformAdminKeyWithServer(
  rawKey: string,
): Promise<{ ok: boolean; status: number; detail?: string }> {
  const normalized = normalizePlatformAdminKeyInput(rawKey);
  if (!normalized) {
    return { ok: false, status: 0, detail: "Key is empty." };
  }
  const rel = "/platform/tenants";
  const url = `${API_BASE}${rel.startsWith("/") ? rel : `/${rel}`}`;
  const headers = new Headers();
  headers.set("X-TruckERP-Platform-Admin-Key", normalized);
  headers.set("X-Platform-Admin-Key", normalized);
  let res: Response;
  try {
    res = await fetch(url, { method: "GET", headers });
  } catch {
    return { ok: false, status: 0, detail: "Network error (offline or blocked)." };
  }
  if (res.status === 200) {
    return { ok: true, status: 200 };
  }
  let detail: string | undefined;
  try {
    const j = (await res.json()) as { detail?: unknown };
    detail = typeof j.detail === "string" ? j.detail : undefined;
  } catch {
    /* ignore */
  }
  return { ok: false, status: res.status, detail: detail ?? `HTTP ${res.status}` };
}

export function setPlatformAdminApiKey(key: string): void {
  if (typeof window === "undefined") return;
  const normalized = normalizePlatformAdminKeyInput(key);
  if (normalized) {
    sessionStorage.setItem(STORAGE_KEY, normalized);
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
    /* Hyphen-only name: some reverse proxies mishandle underscores in client header names. */
    headers.set("X-TruckERP-Platform-Admin-Key", key);
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
