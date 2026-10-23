import { describe, expect, it } from "vitest";
import {
  formatManualHardMissingLine,
  listManualCreateHardMissing,
  listCreateLoadSoftNotProvided,
} from "./workspaceCreateLoadValidation";
import { initialWorkspaceFieldsManual } from "./loadWorkspaceShared";

describe("manual new load create gate", () => {
  it("lists hard missing on empty stops (no server draft required)", () => {
    const missing = listManualCreateHardMissing(initialWorkspaceFieldsManual());
    expect(missing.length).toBeGreaterThan(0);
    expect(missing.some((m) => m.includes("Pickup") || m.includes("pickup"))).toBe(true);
  });

  it("does not require broker or broker load ref for manual create", () => {
    const stops = initialWorkspaceFieldsManual().draftStops;
    stops[0] = { ...stops[0], city: "Toronto", state_or_province: "ON" };
    stops[1] = { ...stops[1], city: "Montreal", state_or_province: "QC" };
    const missing = listManualCreateHardMissing({
      ...initialWorkspaceFieldsManual(),
      brokerNameSnapshot: "",
      brokerLoadReference: "",
      draftStops: stops,
    });
    expect(missing).toEqual([]);
  });

  it("soft not provided lists gaps without blocking parsed create", () => {
    const soft = listCreateLoadSoftNotProvided(initialWorkspaceFieldsManual(), []);
    expect(soft.length).toBeGreaterThan(0);
    expect(formatManualHardMissingLine(listManualCreateHardMissing(initialWorkspaceFieldsManual()))).toMatch(
      /^Missing:/,
    );
  });
});
