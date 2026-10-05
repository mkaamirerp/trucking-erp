import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchWithTenant, uploadTollCsvFile } from "./api";

describe("fetchWithTenant FormData", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ batch_id: 1, source_type: "FILE", file_format: "CSV" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not force JSON Content-Type when the body is FormData", async () => {
    const form = new FormData();
    form.append("file", new File(["Date,Amount\n2026-01-01,1\n"], "tolls.csv", { type: "text/csv" }));
    await fetchWithTenant("/api/v1/tolls/files/csv", { method: "POST", body: form });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("Content-Type")).toBeNull();
    expect(init.body).toBe(form);
  });

  it("lets JSON callers still set application/json", async () => {
    await fetchWithTenant("/api/v1/example", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ok: true }),
    });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("uploadTollCsvFile posts FormData without a JSON content type", async () => {
    const file = new File(["Date,Amount\n2026-01-01,1\n"], "tolls.csv", { type: "text/csv" });
    await uploadTollCsvFile(file);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    const headers = new Headers(init.headers);
    expect(headers.get("Content-Type")).toBeNull();
  });
});
