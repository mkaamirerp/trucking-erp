import { describe, expect, it } from "vitest";
import { fuelProviderTableLabel } from "./fuelProviderDisplay";

describe("fuelProviderTableLabel", () => {
  it("formats manual entry without underscore", () => {
    expect(fuelProviderTableLabel("MANUAL_ENTRY")).toBe("Manual Entry");
  });
});
