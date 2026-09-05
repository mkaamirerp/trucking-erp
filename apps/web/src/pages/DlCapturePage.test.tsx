import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DlCapturePage, {
  DL_CAPTURE_UPLOAD_NETWORK_MESSAGE,
  DL_CAPTURE_UPLOAD_TIMEOUT_MESSAGE,
  DL_CAPTURE_UPLOAD_TIMEOUT_MS,
} from "./DlCapturePage";

vi.mock("../lib/normalizeDlUpload", () => ({
  normalizeDlUpload: async (file: File) => file,
}));

const FRONT_READY = {
  step: "FRONT",
  front_status: "MISSING",
  back_status: "MISSING",
  front_confirmed: false,
  back_confirmed: false,
};

const FRONT_PROCESSED_UNCONFIRMED = {
  step: "FRONT",
  front_status: "PROCESSED",
  back_status: "MISSING",
  front_confirmed: false,
  back_confirmed: false,
  front_preview_file_id: "demo/applicant_dl/application/60/processed-front.jpg",
};

const FRONT_CONFIRMED_BACK_READY = {
  step: "BACK",
  front_status: "PROCESSED",
  back_status: "MISSING",
  front_confirmed: true,
  back_confirmed: false,
  front_preview_file_id: "demo/applicant_dl/application/60/processed-front.jpg",
};

const BACK_FAILED = {
  step: "BACK",
  front_status: "PROCESSED",
  back_status: "FAILED",
  front_confirmed: true,
  back_confirmed: false,
  front_preview_file_id: "demo/applicant_dl/application/60/processed-front.jpg",
  message: "We couldn't clearly detect all four edges.",
};

const BACK_PROCESSED_UNCONFIRMED = {
  step: "BACK",
  front_status: "PROCESSED",
  back_status: "PROCESSED",
  front_confirmed: true,
  back_confirmed: false,
  front_preview_file_id: "demo/applicant_dl/application/60/processed-front.jpg",
  back_preview_file_id: "demo/applicant_dl/application/60/processed-back.jpg",
};

const COMPLETE = {
  step: "COMPLETE",
  front_status: "PROCESSED",
  back_status: "PROCESSED",
  front_confirmed: true,
  back_confirmed: true,
  front_preview_file_id: "demo/applicant_dl/application/60/processed-front.jpg",
  back_preview_file_id: "demo/applicant_dl/application/60/processed-back.jpg",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function photoFile() {
  return new File(["fake-bytes"], "licence.jpg", { type: "image/jpeg" });
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("DlCapturePage upload hang / retry", () => {
  const fetchMock = vi.fn();
  let root: Root | null = null;
  let host: HTMLDivElement | null = null;
  let closeSpy: ReturnType<typeof vi.spyOn> | null = null;

  beforeEach(() => {
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    URL.createObjectURL = vi.fn(() => "blob:dl-preview") as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn();
    closeSpy = vi.spyOn(window, "close").mockImplementation(() => {});
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
    closeSpy?.mockRestore();
    closeSpy = null;
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function renderPage() {
    act(() => {
      root!.render(
        <MemoryRouter initialEntries={["/dl-capture/test-token"]}>
          <Routes>
            <Route path="/dl-capture/:token" element={<DlCapturePage />} />
          </Routes>
        </MemoryRouter>,
      );
    });
  }

  function button(label: string) {
    return Array.from(host!.querySelectorAll("button")).find((b) => b.textContent === label);
  }

  async function loadFrontSession() {
    fetchMock.mockResolvedValueOnce(jsonResponse(FRONT_READY));
    renderPage();
    await flush();
  }

  async function choosePhoto() {
    const input = host!.querySelectorAll('input[type="file"]')[1] as HTMLInputElement;
    await act(async () => {
      Object.defineProperty(input, "files", { configurable: true, value: [photoFile()] });
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flush();
  }

  async function retakeFromCamera() {
    const input = host!.querySelectorAll('input[type="file"]')[0] as HTMLInputElement;
    await act(async () => {
      Object.defineProperty(input, "files", { configurable: true, value: [photoFile()] });
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flush();
  }

  it("times out a hung upload, stops Processing, and restores Take Front DL", async () => {
    await loadFrontSession();
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });

    await choosePhoto();
    expect(host!.textContent).toMatch(/Uploading|Processing licence image/);
    expect((host!.querySelector("button") as HTMLButtonElement).disabled).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DL_CAPTURE_UPLOAD_TIMEOUT_MS);
    });
    await flush();

    expect(host!.textContent).toContain(DL_CAPTURE_UPLOAD_TIMEOUT_MESSAGE);
    expect(host!.textContent).not.toContain("Processing licence image…");
    const take = button("Take Front DL");
    const choose = button("Choose Existing Photo");
    expect(take?.disabled).toBe(false);
    expect(choose?.disabled).toBe(false);
  });

  it("returns to READY on 502 so the user can retry", async () => {
    await loadFrontSession();
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Bad Gateway" }, 502));

    await choosePhoto();
    await flush();

    expect(host!.textContent).toContain("Bad Gateway");
    expect(host!.textContent).not.toContain("Processing licence image…");
    expect(button("Take Front DL")?.disabled).toBe(false);
  });

  it("returns to READY on network error so the user can retry", async () => {
    await loadFrontSession();
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await choosePhoto();
    await flush();

    expect(host!.textContent).toContain(DL_CAPTURE_UPLOAD_NETWORK_MESSAGE);
    expect(host!.textContent).not.toContain("Processing licence image…");
    expect(button("Take Front DL")?.disabled).toBe(false);
  });

  it("keeps FOUR_CORNERS_NOT_CONFIRMED message and allows retry", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(FRONT_CONFIRMED_BACK_READY));
    renderPage();
    await flush();

    fetchMock.mockResolvedValueOnce(jsonResponse(BACK_FAILED));
    await choosePhoto();
    await flush();

    expect(host!.textContent).toContain("We couldn't clearly detect all four edges.");
    expect(host!.textContent).toContain("Back Driver Licence");
    expect(host!.textContent).not.toContain("Processing licence image…");
    expect(button("Take Back DL")?.disabled).toBe(false);
  });

  it("clears the previous error when a new photo attempt starts", async () => {
    await loadFrontSession();
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Bad Gateway" }, 502));
    await choosePhoto();
    await flush();
    expect(host!.textContent).toContain("Bad Gateway");

    let resolveSecond: ((value: Response) => void) | undefined;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          resolveSecond = resolve;
        }),
    );
    await choosePhoto();
    expect(host!.textContent).not.toContain("Bad Gateway");
    expect(host!.textContent).toMatch(/Uploading|Processing licence image/);

    await act(async () => {
      resolveSecond?.(jsonResponse(FRONT_PROCESSED_UNCONFIRMED));
    });
    await flush();
  });

  it("on FRONT success shows processed image and confirmation, not BACK", async () => {
    await loadFrontSession();
    fetchMock.mockResolvedValueOnce(jsonResponse(FRONT_PROCESSED_UNCONFIRMED));
    await choosePhoto();
    await flush();

    expect(host!.textContent).toContain("Front Driver Licence");
    expect(host!.textContent).not.toContain("Back Driver Licence");
    expect(host!.textContent).not.toContain("Front accepted");
    expect(button("Retake")).toBeTruthy();
    expect(button("Use This Photo")).toBeTruthy();
    expect(button("Take Front DL")).toBeUndefined();
    const img = host!.querySelector("img") as HTMLImageElement | null;
    expect(img?.src).toContain("processed-front.jpg");
    expect(host!.textContent).not.toContain("Processing licence image…");
  });

  it("Use This Photo on FRONT moves the UI to BACK capture", async () => {
    await loadFrontSession();
    fetchMock.mockResolvedValueOnce(jsonResponse(FRONT_PROCESSED_UNCONFIRMED));
    await choosePhoto();
    await flush();

    fetchMock.mockResolvedValueOnce(jsonResponse(FRONT_CONFIRMED_BACK_READY));
    await act(async () => {
      button("Use This Photo")?.click();
    });
    await flush();

    const confirmCall = fetchMock.mock.calls.find(
      (c) => typeof c[0] === "string" && String(c[0]).includes("/confirm"),
    );
    expect(confirmCall).toBeTruthy();
    expect(host!.textContent).toContain("Back Driver Licence");
    expect(host!.textContent).toContain("Take Back DL");
    expect(host!.textContent).toContain("Choose Existing Photo");
    expect(host!.textContent).toContain("Front accepted");
    expect(button("Use This Photo")).toBeUndefined();
  });

  it("Retake on FRONT stays on FRONT and can replace the processed image", async () => {
    await loadFrontSession();
    fetchMock.mockResolvedValueOnce(jsonResponse(FRONT_PROCESSED_UNCONFIRMED));
    await choosePhoto();
    await flush();

    const replacement = {
      ...FRONT_PROCESSED_UNCONFIRMED,
      front_preview_file_id: "demo/applicant_dl/application/60/processed-front-retake.jpg",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(replacement));
    await retakeFromCamera();
    await flush();

    const uploadCall = fetchMock.mock.calls.find(
      (c) => typeof c[0] === "string" && String(c[0]).includes("/upload"),
    );
    expect(uploadCall).toBeTruthy();
    expect(host!.textContent).toContain("Front Driver Licence");
    expect(host!.textContent).not.toContain("Back Driver Licence");
    const img = host!.querySelector("img") as HTMLImageElement | null;
    expect(img?.src).toContain("processed-front-retake.jpg");
    expect(button("Use This Photo")).toBeTruthy();
  });

  it("ignores a stale hung request after a newer attempt succeeds", async () => {
    await loadFrontSession();

    let resolveStale: ((value: Response) => void) | undefined;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveStale = resolve;
        }),
    );
    await choosePhoto();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DL_CAPTURE_UPLOAD_TIMEOUT_MS);
    });
    await flush();
    expect(host!.textContent).toContain(DL_CAPTURE_UPLOAD_TIMEOUT_MESSAGE);

    fetchMock.mockResolvedValueOnce(jsonResponse(FRONT_PROCESSED_UNCONFIRMED));
    await choosePhoto();
    await flush();
    expect(host!.textContent).toContain("Front Driver Licence");
    expect(button("Use This Photo")).toBeTruthy();

    await act(async () => {
      resolveStale?.(jsonResponse(COMPLETE));
    });
    await flush();

    expect(host!.textContent).toContain("Front Driver Licence");
    expect(host!.textContent).not.toContain("Driver licence received");
    expect(button("Use This Photo")).toBeTruthy();
  });

  it("on BACK success shows processed image and confirmation, not COMPLETE", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(FRONT_CONFIRMED_BACK_READY));
    renderPage();
    await flush();

    fetchMock.mockResolvedValueOnce(jsonResponse(BACK_PROCESSED_UNCONFIRMED));
    await choosePhoto();
    await flush();

    expect(host!.textContent).toContain("Back Driver Licence");
    expect(button("Retake")).toBeTruthy();
    expect(button("Use This Photo")).toBeTruthy();
    expect(host!.textContent).not.toContain("Driver licence received");
    const img = host!.querySelector("img") as HTMLImageElement | null;
    expect(img?.src).toContain("processed-back.jpg");
  });

  it("Use This Photo on BACK shows completion even if window.close is blocked", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(BACK_PROCESSED_UNCONFIRMED));
    renderPage();
    await flush();

    fetchMock.mockResolvedValueOnce(jsonResponse(COMPLETE));
    await act(async () => {
      button("Use This Photo")?.click();
    });
    await flush();

    expect(host!.textContent).toContain("Driver licence received");
    expect(host!.textContent).toContain("You can return to the other device.");
    expect(button("Close")).toBeTruthy();
    expect(closeSpy).toHaveBeenCalled();

    await act(async () => {
      button("Close")?.click();
    });
    expect(host!.textContent).toContain("Driver licence received");
    expect(closeSpy).toHaveBeenCalledTimes(2);
  });
});
