import { describe, expect, it } from "vitest";
import {
  countOpenMemberships,
  suggestedCustodyStep,
  tripCompleteEligibility,
  type LoadCustodySnapshot,
} from "./tripWorkspaceExecution";
import type { TripDetail, TripMemberLoad } from "@/api";

function member(partial: Partial<TripMemberLoad> & { load_id: number }): TripMemberLoad {
  return {
    trip_load_id: partial.trip_load_id ?? partial.load_id,
    load_id: partial.load_id,
    status_within_trip: partial.status_within_trip ?? "planned",
    sequence_hint: null,
    added_at: "2026-01-01T00:00:00Z",
    completed_at: partial.completed_at ?? null,
    removed_at: partial.removed_at ?? null,
    load_number: partial.load_number ?? `L-${partial.load_id}`,
  };
}

function trip(partial: Partial<TripDetail> & { id: number }): TripDetail {
  return {
    id: partial.id,
    tenant_id: 1,
    trip_number: partial.trip_number ?? "T-1",
    status: partial.status ?? "planned",
    job_type: "freight_load",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    member_loads: partial.member_loads ?? [],
    cancelled_at: partial.cancelled_at ?? null,
    completed_at: partial.completed_at ?? null,
  };
}

describe("tripCompleteEligibility", () => {
  it("allows complete when in_progress and no open memberships", () => {
    const t = trip({
      id: 1,
      status: "in_progress",
      member_loads: [member({ load_id: 10, status_within_trip: "completed", completed_at: "2026-01-02T00:00:00Z" })],
    });
    expect(tripCompleteEligibility(t).canComplete).toBe(true);
  });

  it("blocks when open active membership remains", () => {
    const t = trip({
      id: 1,
      status: "in_progress",
      member_loads: [member({ load_id: 10, status_within_trip: "active" })],
    });
    const r = tripCompleteEligibility(t);
    expect(r.canComplete).toBe(false);
    expect(r.reason).toMatch(/active/i);
  });

  it("blocks when open planned membership remains", () => {
    const t = trip({
      id: 1,
      status: "in_progress",
      member_loads: [member({ load_id: 10, status_within_trip: "planned" })],
    });
    expect(tripCompleteEligibility(t).canComplete).toBe(false);
  });

  it("blocks when not in_progress", () => {
    const t = trip({ id: 1, status: "assigned" });
    expect(tripCompleteEligibility(t).canComplete).toBe(false);
  });
});

describe("suggestedCustodyStep", () => {
  const snap = (partial: Partial<LoadCustodySnapshot> & { load_id: number }): LoadCustodySnapshot => ({
    load_id: partial.load_id,
    custody_owner: partial.custody_owner ?? "unknown",
    custody_placement: partial.custody_placement ?? "unknown",
    custody_trip_id: partial.custody_trip_id ?? null,
    custody_terminal_id: partial.custody_terminal_id ?? null,
  });

  it("accept for planned + unknown custody", () => {
    expect(
      suggestedCustodyStep(member({ load_id: 1, status_within_trip: "planned" }), snap({ load_id: 1 }), 5),
    ).toBe("accept");
  });

  it("yard_handoff for active + trip custody on same trip", () => {
    expect(
      suggestedCustodyStep(
        member({ load_id: 1, status_within_trip: "active" }),
        snap({ load_id: 1, custody_owner: "trip", custody_trip_id: 5 }),
        5,
      ),
    ).toBe("yard_handoff");
  });

  it("take for planned + terminal custody", () => {
    expect(
      suggestedCustodyStep(
        member({ load_id: 1, status_within_trip: "planned" }),
        snap({ load_id: 1, custody_owner: "terminal", custody_terminal_id: 9 }),
        5,
      ),
    ).toBe("take");
  });
});

describe("countOpenMemberships", () => {
  it("counts planned and active open rows", () => {
    const t = trip({
      id: 1,
      member_loads: [
        member({ load_id: 1, status_within_trip: "planned" }),
        member({ load_id: 2, status_within_trip: "removed", removed_at: "2026-01-01T00:00:00Z" }),
        member({ load_id: 3, status_within_trip: "active" }),
      ],
    });
    expect(countOpenMemberships(t)).toBe(2);
  });
});
