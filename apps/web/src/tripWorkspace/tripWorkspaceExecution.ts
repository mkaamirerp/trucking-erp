import { isOpenTripMembership, type TripDetail, type TripMemberLoad } from "@/api";

export type LoadCustodySnapshot = {
  load_id: number;
  custody_owner: string;
  custody_trip_id?: number | null;
  custody_terminal_id?: number | null;
  custody_placement: string;
  custody_trailer_id?: number | null;
  custody_since_at?: string | null;
  last_custody_event_id?: number | null;
};

export type TripCompleteEligibility = {
  canComplete: boolean;
  reason: string;
};

/** Custody transitions with a dedicated Trip Workspace action (not yard handoff). */
export type CustodyStep = "accept" | "take";

/** Reserved event type in app/constants/custody.py — no public API route yet. */
export const FINAL_DELIVERY_API_UNAVAILABLE =
  "Final delivery at consignee/receiver is not available in the API yet (no final_delivery transition). Use terminal yard handoff only when freight is staged at a yard/terminal.";

/** Backend: POST /trips/{id}/complete requires in_progress and zero OPEN TripLoads. */
export function tripCompleteEligibility(trip: TripDetail): TripCompleteEligibility {
  if (trip.cancelled_at != null) {
    return { canComplete: false, reason: "Trip is cancelled." };
  }
  const status = (trip.status || "").toLowerCase();
  if (status === "completed") {
    return { canComplete: false, reason: "Trip is already completed." };
  }
  if (status !== "in_progress") {
    return {
      canComplete: false,
      reason: "Trip must be in progress before it can be completed.",
    };
  }
  const open = (trip.member_loads ?? []).filter((m) => isOpenTripMembership(m));
  if (open.length === 0) {
    return { canComplete: true, reason: "" };
  }
  const hasActive = open.some((m) => (m.status_within_trip || "").toLowerCase() === "active");
  if (hasActive) {
    return {
      canComplete: false,
      reason:
        "Each active load needs a custody closeout on this trip (terminal yard handoff or final delivery when supported) before the trip can be completed.",
    };
  }
  return {
    canComplete: false,
    reason:
      "Resolve open planned memberships (accept/take custody, terminal handoff, or remove from trip) before completing.",
  };
}

export function countOpenMemberships(trip: TripDetail): number {
  return (trip.member_loads ?? []).filter((m) => isOpenTripMembership(m)).length;
}

export function suggestedCustodyStep(
  membership: TripMemberLoad,
  snapshot: LoadCustodySnapshot | undefined,
  tripId: number,
): CustodyStep | null {
  if (!isOpenTripMembership(membership)) return null;
  const within = (membership.status_within_trip || "").toLowerCase();
  const owner = (snapshot?.custody_owner || "unknown").toLowerCase();
  const custodyTripId = snapshot?.custody_trip_id ?? null;

  if (within === "planned") {
    if (owner === "terminal") return "take";
    if (owner === "unknown") return "accept";
    if (owner === "trip" && custodyTripId === tripId) return "accept";
    return null;
  }
  return null;
}

/** POST yard-handoff: trip custody → terminal + completes ACTIVE membership (terminal handoff only). */
export function canOfferTerminalYardHandoff(
  membership: TripMemberLoad,
  snapshot: LoadCustodySnapshot | undefined,
  tripId: number,
): boolean {
  if (!isOpenTripMembership(membership)) return false;
  const within = (membership.status_within_trip || "").toLowerCase();
  if (within !== "active") return false;
  const owner = (snapshot?.custody_owner || "unknown").toLowerCase();
  const custodyTripId = snapshot?.custody_trip_id ?? null;
  return owner === "trip" && custodyTripId === tripId;
}

export function showFinalDeliveryUnavailableNotice(
  membership: TripMemberLoad,
  snapshot: LoadCustodySnapshot | undefined,
  tripId: number,
): boolean {
  return canOfferTerminalYardHandoff(membership, snapshot, tripId);
}

export function formatTripCompleteError(err: unknown): string {
  if (!(err instanceof Error)) return "Could not complete trip.";
  const raw = err.message?.trim() || "";
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    const detail = parsed.detail;
    if (detail && typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
      const code = (detail as { code?: string }).code;
      switch (code) {
        case "OPEN_ACTIVE_MEMBERSHIP_REMAINS":
          return "Trip still has an active load membership. Close out each active load via custody first.";
        case "OPEN_PLANNED_MEMBERSHIP_REMAINS":
          return "Trip still has a planned load membership. Finish custody or remove the load first.";
        case "INVALID_TRIP_STATUS_FOR_COMPLETE":
          return "This trip status cannot be completed from here.";
        case "TRIP_CANCELLED":
          return "This trip is cancelled.";
        default:
          break;
      }
      const msg =
        typeof (detail as { detail?: unknown }).detail === "string"
          ? (detail as { detail: string }).detail
          : null;
      if (msg) return msg;
    }
  } catch {
    /* use raw */
  }
  if (raw.length > 0 && raw.length < 400) return raw;
  return "Could not complete trip.";
}

export function formatCustodyTransitionError(err: unknown): string {
  if (!(err instanceof Error)) return "Custody action failed.";
  const raw = err.message?.trim() || "";
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    const detail = parsed.detail;
    if (detail && typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
      const msg =
        typeof (detail as { detail?: unknown }).detail === "string"
          ? (detail as { detail: string }).detail
          : null;
      if (msg) return msg;
    }
    if (typeof detail === "string" && detail) return detail;
  } catch {
    /* use raw */
  }
  if (raw.length > 0 && raw.length < 400) return raw;
  return "Custody action failed.";
}

export function formatCustodySnapshotLine(snap: LoadCustodySnapshot | undefined): string {
  if (!snap) return "Custody: loading…";
  const owner = snap.custody_owner || "unknown";
  const placement = snap.custody_placement || "—";
  const parts = [`Custody: ${owner}`, `placement ${placement}`];
  if (snap.custody_trip_id != null) parts.push(`trip #${snap.custody_trip_id}`);
  if (snap.custody_terminal_id != null) parts.push(`terminal #${snap.custody_terminal_id}`);
  return parts.join(" · ");
}
