import { describe, expect, it } from "vitest";
import {
  deriveOperatorLoadStatus,
  isOperatorUnassignedLoad,
  operatorLoadStatusDisplayText,
} from "./operatorLoadStatus";

describe("deriveOperatorLoadStatus", () => {
  it("maps draft and cancelled", () => {
    expect(deriveOperatorLoadStatus({ status: "draft" }).label).toBe("Draft");
    expect(deriveOperatorLoadStatus({ status: "cancelled" }).label).toBe("Cancelled");
  });

  it("maps stored ready to Unassigned", () => {
    expect(deriveOperatorLoadStatus({ status: "ready" }).label).toBe("Unassigned");
    expect(deriveOperatorLoadStatus({ status: "unassigned" }).label).toBe("Unassigned");
  });

  it("maps trip mirrors before unassigned", () => {
    expect(
      deriveOperatorLoadStatus({ status: "ready", open_planned_trip_id: 9 }).label,
    ).toBe("Assigned");
    expect(deriveOperatorLoadStatus({ status: "ready", open_future_movement_plan_id: 3 }).label).toBe(
      "Assigned",
    );
    expect(deriveOperatorLoadStatus({ status: "ready", active_trip_id: 4 }).label).toBe("In transit");
  });

  it("maps movement stored statuses to In transit", () => {
    for (const s of ["dispatched", "arrived_pickup", "in_transit", "arrived_delivery"]) {
      expect(deriveOperatorLoadStatus({ status: s }).label).toBe("In transit");
    }
  });

  it("maps delivered via status or custody", () => {
    expect(deriveOperatorLoadStatus({ status: "delivered" }).label).toBe("Delivered");
    expect(deriveOperatorLoadStatus({ status: "ready", custody_owner: "delivered" }).label).toBe(
      "Delivered",
    );
  });

  it("never returns Ready", () => {
    const r = deriveOperatorLoadStatus({ status: "ready" });
    expect(operatorLoadStatusDisplayText(r)).not.toMatch(/ready/i);
  });

  it("returns unknown legacy values without throwing", () => {
    const r = deriveOperatorLoadStatus({ status: "issue_hold" });
    expect(r.kind).toBe("unknown");
    if (r.kind === "unknown") {
      expect(r.label).toBe("issue_hold");
    }
  });

  it("isOperatorUnassignedLoad matches derive label", () => {
    expect(isOperatorUnassignedLoad({ status: "ready" })).toBe(true);
    expect(isOperatorUnassignedLoad({ status: "ready", open_planned_trip_id: 1 })).toBe(false);
  });
});
