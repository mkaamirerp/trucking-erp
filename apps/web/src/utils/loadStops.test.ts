import { describe, expect, it } from "vitest";
import type { LoadStop } from "@/api";
import { formatRouteFromStops } from "./loadStops";

function stop(partial: Partial<LoadStop>): LoadStop {
  return { stop_type: "PICKUP", sequence: 0, ...partial };
}

describe("formatRouteFromStops", () => {
  it("shows cities and does not use a facility name as the destination", () => {
    const route = formatRouteFromStops([
      stop({
        stop_type: "PICKUP",
        sequence: 0,
        facility_name: "NCG-MW RAY DORNHECKER",
        city: "Chicago",
        state_or_province: "IL",
      }),
      stop({
        stop_type: "DELIVERY",
        sequence: 1,
        facility_name: "ICS - NC (REIDSVILLE)",
        city: null,
        state_or_province: "NC",
      }),
    ]);
    expect(route).toBe("Chicago, IL → NC");
    expect(route).not.toContain("ICS");
  });
});
