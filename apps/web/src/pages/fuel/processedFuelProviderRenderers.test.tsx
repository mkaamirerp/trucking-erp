import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";

const bvdView = vi.hoisted(() =>
  vi.fn(() => <div data-testid="bvd-record-view" />),
);
const nationwideView = vi.hoisted(() =>
  vi.fn(() => <div data-testid="nationwide-record-view" />),
);

vi.mock("./BvdProcessedEvidencePanel", () => ({ default: () => null }));
vi.mock("./NationwideProcessedEvidencePanel", () => ({ default: () => null }));

vi.mock("../fuelBvdReview/FuelBvdProcessedRecordView", () => ({
  default: (props: { importId: string }) => {
    bvdView(props);
    return null;
  },
}));

vi.mock("../fuelNationwideReview/FuelNationwideProcessedRecordView", () => ({
  default: (props: { importId: string }) => {
    nationwideView(props);
    return null;
  },
}));

import { getProcessedFuelRecordOverlay } from "./processedFuelProviderRenderers";

describe("processedFuelProviderRenderers record overlays", () => {
  async function renderOverlay(providerCode: string, sourceImportRef: string) {
    const Overlay = getProcessedFuelRecordOverlay(providerCode);
    expect(Overlay).toBeTruthy();
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <Overlay
          sourceImportRef={sourceImportRef}
          variant="overlay"
          onClose={() => undefined}
        />,
      );
      await new Promise((r) => setTimeout(r, 0));
    });
    root.unmount();
    container.remove();
  }

  it("maps sourceImportRef to importId for BVD full record overlay", async () => {
    await renderOverlay("BVD", "bvd-native-uuid");
    expect(bvdView).toHaveBeenCalledWith(
      expect.objectContaining({ importId: "bvd-native-uuid", variant: "overlay" }),
    );
  });

  it("maps sourceImportRef to importId for Nationwide full record overlay", async () => {
    await renderOverlay("NATIONWIDE", "nw-native-uuid");
    expect(nationwideView).toHaveBeenCalledWith(
      expect.objectContaining({ importId: "nw-native-uuid", variant: "overlay" }),
    );
  });
});
