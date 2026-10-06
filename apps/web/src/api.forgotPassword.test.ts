import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { forgotPassword } from "./api";

describe("forgotPassword", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ok: true, sent: true, message: "If an account exists" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends only email and does not include a caller-controlled reset origin", async () => {
    const data = await forgotPassword({ email: "owner@example.com" });
    expect(data.ok).toBe(true);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({ email: "owner@example.com" });
    expect(body.reset_base_url).toBeUndefined();
  });
});
