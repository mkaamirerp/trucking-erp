import { describe, expect, it, beforeEach } from "vitest";
import { readLastFuelProviderCode, writeLastFuelProviderCode } from "./fuelLastProvider";

describe("fuelLastProvider", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("persists last-used provider code", () => {
    writeLastFuelProviderCode("BVD");
    expect(readLastFuelProviderCode()).toBe("BVD");
  });
});
