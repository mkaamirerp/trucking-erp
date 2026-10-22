import { describe, expect, it } from "vitest";
import {
  buildAssignQueue,
  buildDriverRows,
  buildInboundRows,
  formatShortEta,
} from "./useDispatchHomeDashboard";
import type { Driver, FutureMovementPlan, TripListItem } from "../api";

const driver = (id: number, name: string): Driver => ({
  id,
  first_name: name,
  last_name: "Test",
  is_active: true,
});

const trip = (partial: Partial<TripListItem> & { id: number; trip_number: string }): TripListItem =>
  ({
    job_type: "freight_load",
    status: "planned",
    created_at: "",
    updated_at: "",
    member_load_count: 1,
    ...partial,
  }) as TripListItem;

describe("useDispatchHomeDashboard helpers", () => {
  it("marks drivers on open trips as assigned", () => {
    const rows = buildDriverRows(
      [driver(1, "A"), driver(2, "B")],
      [trip({ id: 10, trip_number: "T-1", driver_id: 1, status: "active" })],
    );
    expect(rows.find((r) => r.driver.id === 1)?.status).toBe("assigned");
    expect(rows.find((r) => r.driver.id === 2)?.status).toBe("available");
  });

  it("builds inbound rows from FMP lines with inbound trip", () => {
    const fmp: FutureMovementPlan = {
      id: 5,
      tenant_id: 1,
      status: "unassigned",
      origin_kind: "manual",
      concurrency_version: 1,
      created_at: "",
      updated_at: "",
      planned_start_at: "2026-10-25T14:00:00Z",
      lines: [{ load_id: 100, inbound_trip_id: 9, load_number: "L-100" }],
    };
    const inbound = buildInboundRows([fmp], [trip({ id: 9, trip_number: "T-9" })]);
    expect(inbound).toHaveLength(1);
    expect(inbound[0].tripNumber).toBe("T-9");
    expect(inbound[0].loadNumber).toBe("L-100");
  });

  it("separates FMP plans from numbered trips in assign queue", () => {
    const fmp: FutureMovementPlan = {
      id: 3,
      tenant_id: 1,
      status: "unassigned",
      origin_kind: "manual",
      concurrency_version: 1,
      created_at: "",
      updated_at: "",
      lines: [{ load_id: 1 }],
    };
    const rows = buildAssignQueue(
      [fmp],
      [trip({ id: 7, trip_number: "T-7", status: "planned", driver_id: null })],
    );
    expect(rows.some((r) => r.kind === "fmp" && r.id === 3)).toBe(true);
    expect(rows.some((r) => r.kind === "trip" && r.label === "T-7")).toBe(true);
  });

  it("formatShortEta returns em dash for empty", () => {
    expect(formatShortEta(null)).toBe("—");
  });
});
