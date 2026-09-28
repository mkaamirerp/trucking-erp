import { describe, expect, it } from "vitest";
import { buildFuelProcessedReturnPath, readFuelProcessedReturn } from "./bvdUploadCompletion";

describe("fuel processed return", () => {
  it("builds and reads post-process Fuel home query", () => {
    const path = buildFuelProcessedReturnPath("972201");
    expect(path).toContain("/fuel");
    expect(path).toContain("fuelProcessed=1");
    expect(path).toContain("invoice=972201");
    expect(readFuelProcessedReturn(path.split("?")[1] ?? "")).toEqual({ invoiceNumber: "972201" });
  });
});
