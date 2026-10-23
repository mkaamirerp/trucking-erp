import { describe, expect, it } from "vitest";
import { listCreateLoadHardMissing } from "./workspaceCreateLoadValidation";
import { initialWorkspaceFieldsManual } from "./loadWorkspaceShared";

/** Task 3: Create load gate blocks until hard requirements (Task 2b alignment). */
describe("manual new load create gate", () => {
  it("lists hard missing on empty form (no server draft required)", () => {
    const missing = listCreateLoadHardMissing(initialWorkspaceFieldsManual(), []);
    expect(missing.length).toBeGreaterThan(0);
    expect(missing).toContain("Load # / PO #");
  });

  it("passes when promotable minimums are filled", () => {
    const stops = initialWorkspaceFieldsManual().draftStops;
    stops[0] = { ...stops[0], city: "Toronto", state_or_province: "ON" };
    stops[1] = { ...stops[1], city: "Montreal", state_or_province: "QC" };
    const missing = listCreateLoadHardMissing(
      {
        ...initialWorkspaceFieldsManual(),
        brokerNameSnapshot: "Acme",
        brokerLoadReference: "PO-1",
        draftStops: stops,
      },
      [],
    );
    expect(missing).toEqual([]);
  });
});
