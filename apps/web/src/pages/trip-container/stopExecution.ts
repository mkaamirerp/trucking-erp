import type { LoadStop } from "@/api";

const EXECUTABLE_STOP_TYPES = new Set(["PICKUP", "DROP", "DELIVERY"]);

export function stopExecutionEligible(
  tripStatus: string | null | undefined,
  membershipStatus: string | null | undefined,
  stop: Pick<LoadStop, "stop_type">,
): boolean {
  if ((tripStatus || "").toLowerCase() !== "in_progress") return false;
  if ((membershipStatus || "").toLowerCase() !== "active") return false;
  return EXECUTABLE_STOP_TYPES.has((stop.stop_type || "").toUpperCase());
}

export function showArrive(
  tripStatus: string | null | undefined,
  membershipStatus: string | null | undefined,
  stop: Pick<LoadStop, "stop_type" | "arrived_at">,
): boolean {
  return stopExecutionEligible(tripStatus, membershipStatus, stop) && !stop.arrived_at;
}

export function showDepart(
  tripStatus: string | null | undefined,
  membershipStatus: string | null | undefined,
  stop: Pick<LoadStop, "stop_type" | "arrived_at" | "departed_at">,
): boolean {
  return stopExecutionEligible(tripStatus, membershipStatus, stop) && !!stop.arrived_at && !stop.departed_at;
}
