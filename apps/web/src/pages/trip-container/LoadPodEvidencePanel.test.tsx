import { act, type ReactNode } from "react";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import LoadPodEvidencePanel from "./LoadPodEvidencePanel";

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function mount(node: ReactNode) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(node);
  });
}

describe("LoadPodEvidencePanel", () => {
  it("uploads a POD without calling delivery or trip completion APIs", async () => {
    const listLoadPodEvidence = vi.fn().mockResolvedValue([]);
    const uploadLoadPodEvidence = vi.fn().mockResolvedValue({
      id: 1,
      load_id: 42,
      file_sha256: "abc",
      file_size_bytes: 10,
      uploaded_at: "2026-10-17T12:00:00Z",
    });
    const downloadLoadPodEvidenceFile = vi.fn();

    mount(
      <LoadPodEvidencePanel
        loadId={42}
        api={{
          listLoadPodEvidence,
          uploadLoadPodEvidence,
          downloadLoadPodEvidenceFile,
        }}
      />
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(listLoadPodEvidence).toHaveBeenCalledWith(42);

    const input = container.querySelector('[data-testid="pod-file-input-42"]') as HTMLInputElement;
    const file = new File(["%PDF-1.4"], "signed.pdf", { type: "application/pdf" });
    await act(async () => {
      Object.defineProperty(input, "files", { value: [file] });
      input.dispatchEvent(new Event("change", { bubbles: true }));
      await Promise.resolve();
    });

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(uploadLoadPodEvidence).toHaveBeenCalledWith(42, file);
    expect(listLoadPodEvidence.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});
