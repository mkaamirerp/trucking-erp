/**
 * Operator-facing load status (Task 15). Stored `loads.status` is not shown verbatim
 * except for unknown legacy values.
 */

export type OperatorLoadStatusLabel =
  | "Draft"
  | "Unassigned"
  | "Assigned"
  | "In transit"
  | "Delivered"
  | "Cancelled";

export type OperatorLoadStatusInput = {
  status?: string | null;
  active_trip_id?: number | null;
  open_planned_trip_id?: number | null;
  open_future_movement_plan_id?: number | null;
  /** From loads.custody_owner — final delivery without changing commercial status. */
  custody_owner?: string | null;
};

export type OperatorLoadStatusResult =
  | { kind: "known"; label: OperatorLoadStatusLabel }
  | { kind: "unknown"; label: string; storedStatus: string };

const IN_TRANSIT_STORED = new Set([
  "dispatched",
  "arrived_pickup",
  "in_transit",
  "arrived_delivery",
]);

const ASSIGNED_STORED = new Set(["assigned"]);

function norm(s: string | null | undefined): string {
  return (s ?? "").trim().toLowerCase();
}

export function deriveOperatorLoadStatus(input: OperatorLoadStatusInput): OperatorLoadStatusResult {
  const stored = norm(input.status);
  const custody = norm(input.custody_owner);

  if (!stored) {
    return { kind: "unknown", label: "—", storedStatus: "" };
  }
  if (stored === "cancelled") {
    return { kind: "known", label: "Cancelled" };
  }
  if (stored === "draft") {
    return { kind: "known", label: "Draft" };
  }
  if (stored === "delivered" || custody === "delivered") {
    return { kind: "known", label: "Delivered" };
  }
  if (IN_TRANSIT_STORED.has(stored)) {
    return { kind: "known", label: "In transit" };
  }
  if (input.active_trip_id != null) {
    return { kind: "known", label: "In transit" };
  }
  if (input.open_planned_trip_id != null || input.open_future_movement_plan_id != null) {
    return { kind: "known", label: "Assigned" };
  }
  if (ASSIGNED_STORED.has(stored) || stored === "dispatched") {
    return { kind: "known", label: "Assigned" };
  }
  if (stored === "ready" || stored === "unassigned") {
    return { kind: "known", label: "Unassigned" };
  }

  return { kind: "unknown", label: stored, storedStatus: stored };
}

export function operatorLoadStatusDisplayText(result: OperatorLoadStatusResult): string {
  return result.label;
}

export function isOperatorUnassignedLoad(input: OperatorLoadStatusInput): boolean {
  const r = deriveOperatorLoadStatus(input);
  return r.kind === "known" && r.label === "Unassigned";
}
