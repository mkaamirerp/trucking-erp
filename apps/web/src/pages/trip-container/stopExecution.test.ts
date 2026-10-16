import { describe, expect, it } from "vitest";
import { showArrive, showDepart } from "./stopExecution";

const pickup = { stop_type: "PICKUP", arrived_at: null, departed_at: null };

describe("stop execution eligibility", () => {
  it("shows Arrive only for an in-progress Trip and an active membership", () => {
    expect(showArrive("in_progress", "active", pickup)).toBe(true);
    expect(showArrive("assigned", "active", pickup)).toBe(false);
    expect(showArrive("in_progress", "planned", pickup)).toBe(false);
    expect(showArrive("in_progress", "active", { ...pickup, stop_type: "YARD" })).toBe(false);
    expect(showArrive("in_progress", "active", { ...pickup, arrived_at: "2026-10-16T12:00:00Z" })).toBe(false);
  });

  it("shows Depart only after arrival and before departure", () => {
    expect(showDepart("in_progress", "active", pickup)).toBe(false);
    expect(
      showDepart("in_progress", "active", { ...pickup, arrived_at: "2026-10-16T12:00:00Z" }),
    ).toBe(true);
    expect(
      showDepart("in_progress", "active", {
        ...pickup,
        arrived_at: "2026-10-16T12:00:00Z",
        departed_at: "2026-10-16T13:00:00Z",
      }),
    ).toBe(false);
  });
});
