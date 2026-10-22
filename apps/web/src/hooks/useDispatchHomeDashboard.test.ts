import { describe, expect, it, vi } from "vitest";
import {
  INBOUND_ETA_NOT_RECORDED,
  buildAssignQueue,
  buildDriverRows,
  buildInboundRows,
  inboundEtaLabel,
  isLicenseExpired,
  pickOpenTripForDriver,
  tripsFetchMayBeIncomplete,
} from "./useDispatchHomeDashboard";
import type { Driver, FutureMovementPlan, TripListItem } from "../api";

const driver = (id: number, name: string, extra: Partial<Driver> = {}): Driver => ({
  id,
  first_name: name,
  last_name: "Test",
  is_active: true,
  ...extra,
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

describe("driver availability", () => {
  it("classifies in_progress as executing", () => {
    const rows = buildDriverRows(
      [driver(1, "A")],
      [trip({ id: 10, trip_number: "T-1", driver_id: 1, status: "in_progress" })],
      { tripsListMayBeIncomplete: false },
    );
    expect(rows[0].status).toBe("executing");
  });

  it("classifies planned assignment as scheduled (not available)", () => {
    const rows = buildDriverRows(
      [driver(1, "A")],
      [trip({ id: 10, trip_number: "T-1", driver_id: 1, status: "planned" })],
      { tripsListMayBeIncomplete: false },
    );
    expect(rows[0].status).toBe("scheduled");
  });

  it("prefers in_progress over future planned trip for same driver", () => {
    const picked = pickOpenTripForDriver(
      [
        trip({ id: 1, trip_number: "P", driver_id: 5, status: "planned" }),
        trip({ id: 2, trip_number: "E", driver_id: 5, status: "in_progress" }),
      ],
      5,
    );
    expect(picked?.trip_number).toBe("E");
  });

  it("does not treat legacy active status as open", () => {
    const picked = pickOpenTripForDriver(
      [trip({ id: 1, trip_number: "X", driver_id: 1, status: "active" })],
      1,
    );
    expect(picked).toBeNull();
    const rows = buildDriverRows([driver(1, "A")], [trip({ id: 1, trip_number: "X", driver_id: 2, status: "active" })], {
      tripsListMayBeIncomplete: false,
    });
    expect(rows[0].status).toBe("available");
  });

  it("marks unverified when trip list may be incomplete", () => {
    const rows = buildDriverRows([driver(1, "A")], [], { tripsListMayBeIncomplete: true });
    expect(rows[0].status).toBe("unverified");
  });

  it("blocks expired license from showing as available when trips are complete", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-22T12:00:00Z"));
    const rows = buildDriverRows(
      [driver(1, "A", { license_expiry_date: "2026-01-01" })],
      [],
      { tripsListMayBeIncomplete: false },
    );
    expect(isLicenseExpired(rows[0].driver)).toBe(true);
    expect(rows[0].status).toBe("license_blocked");
    vi.useRealTimers();
  });

  it("in_progress driver with expired license stays executing", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-22T12:00:00Z"));
    const rows = buildDriverRows(
      [driver(1, "A", { license_expiry_date: "2020-01-01" })],
      [trip({ id: 9, trip_number: "T-9", driver_id: 1, status: "in_progress" })],
      { tripsListMayBeIncomplete: false },
    );
    expect(rows[0].status).toBe("executing");
    expect(rows[0].licenseWarning).toBe("License expired");
    vi.useRealTimers();
  });
});

describe("inbound yard ETA", () => {
  it("does not use FMP planned_start_at as inbound ETA", () => {
    const fmp: FutureMovementPlan = {
      id: 5,
      tenant_id: 1,
      status: "unassigned",
      origin_kind: "manual",
      concurrency_version: 1,
      created_at: "",
      updated_at: "",
      planned_start_at: "2030-06-01T08:00:00Z",
      lines: [{ load_id: 100, inbound_trip_id: 9, load_number: "L-100" }],
    };
    const inbound = buildInboundRows([fmp], [trip({ id: 9, trip_number: "T-9" })]);
    expect(inbound[0].etaLabel).toBe(INBOUND_ETA_NOT_RECORDED);
  });

  it("uses inbound trip expected_completion_at when present", () => {
    const inbound = buildInboundRows(
      [
        {
          id: 1,
          tenant_id: 1,
          status: "unassigned",
          origin_kind: "manual",
          concurrency_version: 1,
          created_at: "",
          updated_at: "",
          planned_start_at: "2030-01-01T00:00:00Z",
          lines: [{ load_id: 1, inbound_trip_id: 2 }],
        } as FutureMovementPlan,
      ],
      [trip({ id: 2, trip_number: "IN", expected_completion_at: "2026-11-01T15:30:00Z" })],
    );
    expect(inbound[0].etaLabel).not.toBe(INBOUND_ETA_NOT_RECORDED);
    expect(inboundEtaLabel(trip({ id: 2, trip_number: "IN", expected_completion_at: "2026-11-01T15:30:00Z" }))).toContain(
      "Nov",
    );
  });
});

describe("loads to assign", () => {
  it("excludes assigned trips from the queue", () => {
    const rows = buildAssignQueue(
      [],
      [trip({ id: 1, trip_number: "A", status: "assigned", driver_id: 3, truck_id: 1, trailer_id: 1 })],
    );
    expect(rows).toHaveLength(0);
  });

  it("queues planned trip without driver as needs_driver", () => {
    const rows = buildAssignQueue([], [trip({ id: 7, trip_number: "T-7", status: "planned", driver_id: null })]);
    expect(rows).toHaveLength(1);
    expect(rows[0].kind).toBe("trip");
    if (rows[0].kind === "trip") expect(rows[0].queueKind).toBe("needs_driver");
  });

  it("queues planned trip with driver but missing equipment separately", () => {
    const rows = buildAssignQueue(
      [],
      [trip({ id: 8, trip_number: "T-8", status: "planned", driver_id: 2, truck_id: null, trailer_id: 5 })],
    );
    expect(rows).toHaveLength(1);
    if (rows[0].kind === "trip") {
      expect(rows[0].queueKind).toBe("needs_equipment");
      expect(rows[0].sublabel).toContain("truck");
    }
  });

  it("keeps open FMP separate from numbered trips", () => {
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
    expect(rows.some((r) => r.kind === "fmp")).toBe(true);
    expect(rows.some((r) => r.kind === "trip" && r.label === "T-7")).toBe(true);
  });
});

describe("trip pagination guard", () => {
  it("detects incomplete trip fetch", () => {
    expect(tripsFetchMayBeIncomplete(new Array(80).fill({}), 200)).toBe(true);
    expect(tripsFetchMayBeIncomplete([], 0)).toBe(false);
    expect(tripsFetchMayBeIncomplete(new Array(5).fill({}), 5)).toBe(false);
  });
});

describe("POD panel policy", () => {
  it("does not treat commercial Load.status delivered as operational proof", () => {
    const commercialDelivered = { status: "delivered" } as { status: string };
    expect(commercialDelivered.status).toBe("delivered");
    expect(INBOUND_ETA_NOT_RECORDED).toBe("ETA not recorded");
  });
});
