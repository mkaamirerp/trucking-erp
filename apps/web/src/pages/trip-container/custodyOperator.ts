import { isOpenTripMembership, type LoadCustodySnapshot, type TripDetail, type TripMemberLoad } from "@/api";

export type CustodyPlacement = "on_trailer" | "staged";

export function formatCustodyApiError(err: unknown): string {
  if (!(err instanceof Error) || !err.message) return "Request failed";
  try {
    const outer = JSON.parse(err.message) as { detail?: unknown };
    const detail = outer.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const rec = detail as { detail?: unknown; code?: unknown };
      const message = typeof rec.detail === "string" ? rec.detail : "";
      const code = typeof rec.code === "string" ? rec.code : "";
      if (message && code) return `${message} (${code})`;
      if (message) return message;
      if (code) return code;
    }
  } catch {
    /* response body is not JSON */
  }
  return err.message;
}

export function custodyStatusLabel(snapshot: LoadCustodySnapshot | null | undefined): string {
  if (!snapshot) return "Custody unavailable";
  const owner = (snapshot.custody_owner || "").toLowerCase();
  const placement = snapshot.custody_placement || "unknown";
  if (owner === "trip") return `Custody: trip ${snapshot.custody_trip_id ?? "—"} · ${placement}`;
  if (owner === "terminal") return `Custody: terminal ${snapshot.custody_terminal_id ?? "—"} · ${placement}`;
  if (owner === "delivered") return "Custody: delivered";
  if (owner === "unknown") return "Custody: unknown";
  return `Custody: ${snapshot.custody_owner}`;
}

export function tripEligibleForCustody(trip: Pick<TripDetail, "status" | "cancelled_at" | "driver_id" | "truck_id" | "trailer_id">): boolean {
  if (trip.cancelled_at) return false;
  const status = (trip.status || "").toLowerCase();
  if (status !== "assigned" && status !== "in_progress") return false;
  if (trip.trailer_id == null) return false;
  if (status === "assigned" && (trip.driver_id == null || trip.truck_id == null)) return false;
  return true;
}

function plannedMembership(member: TripMemberLoad): boolean {
  return (member.status_within_trip || "").toLowerCase() === "planned" && isOpenTripMembership(member);
}

function activeMembership(member: TripMemberLoad): boolean {
  return (member.status_within_trip || "").toLowerCase() === "active" && isOpenTripMembership(member);
}

export function showAcceptCustody(
  trip: TripDetail,
  member: TripMemberLoad,
  snapshot: LoadCustodySnapshot | null | undefined,
): boolean {
  if (!snapshot || !tripEligibleForCustody(trip) || !plannedMembership(member)) return false;
  return (snapshot.custody_owner || "").toLowerCase() === "unknown";
}

export function showTakeCustody(
  trip: TripDetail,
  member: TripMemberLoad,
  snapshot: LoadCustodySnapshot | null | undefined,
): boolean {
  if (!snapshot || !tripEligibleForCustody(trip) || !plannedMembership(member)) return false;
  if ((snapshot.custody_owner || "").toLowerCase() !== "terminal" || snapshot.custody_terminal_id == null) return false;
  const placement = (snapshot.custody_placement || "").toLowerCase();
  if (placement === "staged") return true;
  if (placement !== "on_trailer") return false;
  return snapshot.custody_trailer_id != null && snapshot.custody_trailer_id === trip.trailer_id;
}

export function showFinalDelivery(
  trip: TripDetail,
  member: TripMemberLoad,
  snapshot: LoadCustodySnapshot | null | undefined,
): boolean {
  if (trip.cancelled_at || (trip.status || "").toLowerCase() !== "in_progress") return false;
  if (!snapshot || !activeMembership(member)) return false;
  return (snapshot.custody_owner || "").toLowerCase() === "trip" && snapshot.custody_trip_id === trip.id;
}

export function showHandoff(
  trip: TripDetail,
  member: TripMemberLoad,
  snapshot: LoadCustodySnapshot | null | undefined,
): boolean {
  if (trip.cancelled_at) return false;
  const status = (trip.status || "").toLowerCase();
  if (status === "completed" || status === "cancelled" || status === "planned") return false;
  if (!snapshot || !activeMembership(member)) return false;
  return (snapshot.custody_owner || "").toLowerCase() === "trip" && snapshot.custody_trip_id === trip.id;
}

export function canCompleteTrip(trip: Pick<TripDetail, "status" | "cancelled_at" | "member_loads">): boolean {
  if (trip.cancelled_at) return false;
  if ((trip.status || "").toLowerCase() !== "in_progress") return false;
  return (trip.member_loads ?? []).every((member) => !isOpenTripMembership(member));
}
