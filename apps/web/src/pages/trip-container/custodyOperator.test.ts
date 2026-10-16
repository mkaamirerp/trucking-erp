import { describe, expect, it } from "vitest";
import type { LoadCustodySnapshot, TripDetail, TripMemberLoad } from "@/api";
import {
  canCompleteTrip,
  formatCustodyApiError,
  showAcceptCustody,
  showFinalDelivery,
  showHandoff,
  showTakeCustody,
} from "./custodyOperator";

function member(status: string, extra: Partial<TripMemberLoad> = {}): TripMemberLoad {
  return {
    trip_load_id: 1,
    load_id: 9,
    status_within_trip: status,
    sequence_hint: 0,
    added_at: "2026-10-16T00:00:00Z",
    completed_at: status === "completed" ? "2026-10-16T01:00:00Z" : null,
    removed_at: null,
    load_number: "L9",
    ...extra,
  };
}

function trip(status: string, members: TripMemberLoad[], extra: Partial<TripDetail> = {}): TripDetail {
  return {
    id: 3,
    tenant_id: 1,
    trip_number: "T3",
    status,
    job_type: "linehaul",
    driver_id: 1,
    truck_id: 2,
    trailer_id: 8,
    cancelled_at: null,
    created_at: "2026-10-16T00:00:00Z",
    updated_at: "2026-10-16T00:00:00Z",
    member_loads: members,
    ...extra,
  };
}

function snap(partial: Partial<LoadCustodySnapshot>): LoadCustodySnapshot {
  return {
    load_id: 9,
    custody_owner: "unknown",
    custody_placement: "unknown",
    ...partial,
  };
}

describe("custody operator eligibility", () => {
  const moving = trip("in_progress", [member("planned")]);

  it("shows Accept Custody only for a planned membership with unknown custody", () => {
    expect(showAcceptCustody(moving, member("planned"), snap({ custody_owner: "unknown" }))).toBe(true);
    expect(showAcceptCustody(moving, member("active"), snap({ custody_owner: "unknown" }))).toBe(false);
    expect(showAcceptCustody(moving, member("planned"), snap({ custody_owner: "terminal", custody_terminal_id: 4, custody_placement: "staged" }))).toBe(false);
    expect(showTakeCustody(moving, member("planned"), snap({ custody_owner: "unknown" }))).toBe(false);
  });

  it("shows Take Custody only when the planned Load is at a terminal the Trip can take", () => {
    const staged = snap({ custody_owner: "terminal", custody_terminal_id: 4, custody_placement: "staged" });
    expect(showTakeCustody(moving, member("planned"), staged)).toBe(true);
    expect(showTakeCustody(moving, member("active"), staged)).toBe(false);
    expect(
      showTakeCustody(
        moving,
        member("planned"),
        snap({ custody_owner: "terminal", custody_terminal_id: 4, custody_placement: "on_trailer", custody_trailer_id: 8 }),
      ),
    ).toBe(true);
    expect(
      showTakeCustody(
        moving,
        member("planned"),
        snap({ custody_owner: "terminal", custody_terminal_id: 4, custody_placement: "on_trailer", custody_trailer_id: 99 }),
      ),
    ).toBe(false);
    expect(showAcceptCustody(moving, member("planned"), staged)).toBe(false);
  });

  it("shows Handoff only while this Trip holds an active membership", () => {
    const held = snap({ custody_owner: "trip", custody_trip_id: 3, custody_placement: "on_trailer" });
    expect(showHandoff(trip("in_progress", [member("active")]), member("active"), held)).toBe(true);
    expect(showHandoff(trip("in_progress", [member("planned")]), member("planned"), held)).toBe(false);
    expect(showHandoff(trip("in_progress", [member("active")]), member("active"), snap({ custody_owner: "terminal", custody_terminal_id: 4, custody_placement: "staged" }))).toBe(false);
  });

  it("shows Final Delivery only for an in-progress Trip holding that Load", () => {
    const held = snap({ custody_owner: "trip", custody_trip_id: 3, custody_placement: "on_trailer" });
    expect(showFinalDelivery(trip("in_progress", [member("active")]), member("active"), held)).toBe(true);
    expect(showFinalDelivery(trip("assigned", [member("active")]), member("active"), held)).toBe(false);
    expect(showFinalDelivery(trip("in_progress", [member("planned")]), member("planned"), held)).toBe(false);
    expect(
      showFinalDelivery(
        trip("in_progress", [member("active")]),
        member("active"),
        snap({ custody_owner: "terminal", custody_terminal_id: 4, custody_placement: "staged" }),
      ),
    ).toBe(false);
    expect(
      showFinalDelivery(
        trip("in_progress", [member("active")]),
        member("active"),
        snap({ custody_owner: "unknown" }),
      ),
    ).toBe(false);
  });

  it("keeps Complete Trip unavailable until the Trip is in progress and every membership is closed", () => {
    expect(canCompleteTrip(trip("in_progress", [member("active")]))).toBe(false);
    expect(canCompleteTrip(trip("in_progress", [member("planned")]))).toBe(false);
    expect(canCompleteTrip(trip("assigned", [member("completed")]))).toBe(false);
    expect(canCompleteTrip(trip("in_progress", [member("completed")]))).toBe(true);
  });

  it("formats backend custody errors", () => {
    const err = new Error(JSON.stringify({ detail: { detail: "Membership is not active", code: "MEMBERSHIP_NOT_ACTIVE" } }));
    expect(formatCustodyApiError(err)).toBe("Membership is not active (MEMBERSHIP_NOT_ACTIVE)");
  });
});
