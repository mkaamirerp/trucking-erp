import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getPlatformAdminApiKey,
  platformAdminFetch,
  platformAdminJson,
  PlatformAdminHttpError,
  PlatformAdminUnauthorizedError,
  setPlatformAdminApiKey,
} from "./platformAdminFetch";

describe("platformAdminFetch layer", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("stores and reads the API key via sessionStorage helpers", () => {
    expect(getPlatformAdminApiKey()).toBe("");
    setPlatformAdminApiKey("  k1  ");
    expect(sessionStorage.getItem("platform_admin_api_key")).toBe("k1");
    expect(getPlatformAdminApiKey()).toBe("k1");
    setPlatformAdminApiKey("");
    expect(getPlatformAdminApiKey()).toBe("");
    expect(sessionStorage.getItem("platform_admin_api_key")).toBeNull();
  });

  it("sends platform admin headers when a key is stored", async () => {
    setPlatformAdminApiKey("secret");
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await platformAdminFetch("/platform/tenants");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/platform\/tenants$/);
    const headers = init.headers as Headers;
    expect(headers.get("X-Platform-Admin-Key")).toBe("secret");
    expect(headers.get("X-TruckERP-Platform-Admin-Key")).toBe("secret");
  });

  it("omits X-Platform-Admin-Key when no key is stored", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await platformAdminFetch("/platform/tenants");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("X-Platform-Admin-Key")).toBeNull();
  });

  it("throws PlatformAdminUnauthorizedError on 401 before reading body", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "nope" }), { status: 401 }));

    await expect(platformAdminFetch("/platform/tenants")).rejects.toBeInstanceOf(PlatformAdminUnauthorizedError);
  });

  it("platformAdminJson parses JSON on success", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    const data = await platformAdminJson<{ ok: boolean }>("/platform/tenants");
    expect(data).toEqual({ ok: true });
  });

  it("platformAdminJson throws PlatformAdminHttpError with FastAPI detail string", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "bad request" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    );

    try {
      await platformAdminJson("/platform/tenants");
      expect.fail("expected PlatformAdminHttpError");
    } catch (e) {
      expect(e).toBeInstanceOf(PlatformAdminHttpError);
      expect((e as PlatformAdminHttpError).message).toBe("bad request");
      expect((e as PlatformAdminHttpError).status).toBe(400);
    }
  });
});
