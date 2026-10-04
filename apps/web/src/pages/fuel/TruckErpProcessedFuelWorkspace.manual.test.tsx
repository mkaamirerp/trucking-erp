import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("TruckErpProcessedFuelWorkspace MANUAL_ENTRY adapter", () => {
  it("registers MANUAL_ENTRY operational adapter branch", () => {
    const src = readFileSync(
      resolve(import.meta.dirname, "TruckErpProcessedFuelWorkspace.tsx"),
      "utf8",
    );
    expect(src).toContain('code === "MANUAL_ENTRY"');
    expect(src).toContain("adaptManualOperationalTransactionsForProcessedStatement");
    expect(src).not.toMatch(/No operational workspace adapter for MANUAL_ENTRY/);
  });
});
