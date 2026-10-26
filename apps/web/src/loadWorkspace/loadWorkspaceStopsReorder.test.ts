import { describe, expect, it } from "vitest";
import { newDraftStop, normalizeDraftStopSequences, reorderDraftStopsByKey } from "./loadWorkspaceShared";

describe("reorderDraftStopsByKey", () => {
  it("swaps stops and renumbers when duplicate sequence values exist", () => {
    const a = { ...newDraftStop(0), _key: "a", facility_name: "First" };
    const b = { ...newDraftStop(0), _key: "b", facility_name: "Second" };
    const c = { ...newDraftStop(0), _key: "c", facility_name: "Third" };
    const next = reorderDraftStopsByKey([a, b, c], "a", 1);
    expect(next.map((s) => s.facility_name)).toEqual(["Second", "First", "Third"]);
    expect(next.map((s) => s.sequence)).toEqual([0, 1, 2]);
  });

  it("normalizeDraftStopSequences assigns unique indices", () => {
    const rows = [
      { ...newDraftStop(5), _key: "x" },
      { ...newDraftStop(5), _key: "y" },
    ];
    expect(normalizeDraftStopSequences(rows).map((r) => r.sequence)).toEqual([0, 1]);
  });
});
