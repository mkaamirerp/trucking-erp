import { useCallback, useEffect, useMemo, useState } from "react";
import {
  type Driver,
  type FutureMovementPlan,
  type Load,
  type TripListItem,
  listDrivers,
  listFutureMovementPlans,
  listLoads,
  listTrips,
} from "../api";
import { formatRouteFromStops, firstPickupAppointmentDate } from "../utils/loadStops";

/** Canonical open Trip statuses (Trip operational truth — not legacy Load.status). */
export const OPEN_TRIP_STATUSES = new Set(["planned", "assigned", "in_progress"]);

export const INBOUND_ETA_NOT_RECORDED = "ETA not recorded";

export const POD_PANEL_DISCONNECTED_MESSAGE =
  "Delivery/POD queue not yet connected. TruckERP has no tenant-level API here that proves operational final delivery and missing POD without per-load probes.";

export type DriverAvailabilityStatus =
  | "available"
  | "executing"
  | "scheduled"
  | "unverified"
  | "license_blocked";

export type DriverAvailabilityRow = {
  driver: Driver;
  status: DriverAvailabilityStatus;
  truckLabel: string | null;
  tripNumber: string | null;
  licenseWarning: string | null;
};

export type InboundYardRow = {
  key: string;
  tripNumber: string | null;
  tripId: number | null;
  loadNumber: string | null;
  loadId: number | null;
  etaLabel: string;
  fmpPlanId: number | null;
};

export type AssignQueueRow =
  | {
      kind: "unassigned_load";
      id: number;
      label: string;
      sublabel: string;
      href: string;
      badge: "Unassigned";
    }
  | {
      kind: "fmp";
      id: number;
      label: string;
      sublabel: string;
      href: string;
      loadCount: number;
    }
  | {
      kind: "trip";
      id: number;
      label: string;
      sublabel: string;
      href: string;
      loadCount: number;
      queueKind: "needs_driver" | "needs_equipment";
    };

export type PodPanelState = {
  connected: boolean;
  message: string;
};

export function formatShortEta(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) {
    return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function licenseExpiryWarning(driver: Driver): string | null {
  if (!driver.license_expiry_date) return null;
  const exp = new Date(driver.license_expiry_date);
  if (Number.isNaN(exp.getTime())) return null;
  const days = (exp.getTime() - Date.now()) / (86400 * 1000);
  if (days < 0) return "License expired";
  if (days <= 30) return "License expiring soon";
  return null;
}

export function isLicenseExpired(driver: Driver): boolean {
  return licenseExpiryWarning(driver) === "License expired";
}

function tripStatusRank(status: string): number {
  const st = status.toLowerCase();
  if (st === "in_progress") return 0;
  if (st === "assigned") return 1;
  if (st === "planned") return 2;
  return 99;
}

/** Prefer current execution over future assignment when multiple open trips exist. */
export function pickOpenTripForDriver(trips: TripListItem[], driverId: number): TripListItem | null {
  const candidates = trips.filter((t) => {
    if (t.driver_id !== driverId || t.cancelled_at || t.completed_at) return false;
    const st = (t.status || "").toLowerCase();
    return OPEN_TRIP_STATUSES.has(st);
  });
  if (!candidates.length) return null;
  candidates.sort((a, b) => tripStatusRank(a.status) - tripStatusRank(b.status));
  return candidates[0];
}

export function buildDriverRows(
  drivers: Driver[],
  trips: TripListItem[],
  options: { tripsListMayBeIncomplete: boolean },
): DriverAvailabilityRow[] {
  return drivers
    .filter((d) => d.is_active)
    .map((driver) => {
      const licenseWarning = licenseExpiryWarning(driver);
      const expired = isLicenseExpired(driver);
      const openTrip = pickOpenTripForDriver(trips, driver.id);
      let status: DriverAvailabilityStatus;

      if (openTrip) {
        const st = (openTrip.status || "").toLowerCase();
        status = st === "in_progress" ? "executing" : "scheduled";
      } else if (options.tripsListMayBeIncomplete) {
        status = "unverified";
      } else if (expired) {
        status = "license_blocked";
      } else {
        status = "available";
      }

      if (!openTrip && expired && status === "unverified") {
        status = "license_blocked";
      }

      const truckLabel = openTrip?.truck?.unit_number ? `Trk ${openTrip.truck.unit_number}` : null;
      return {
        driver,
        status,
        truckLabel,
        tripNumber: openTrip?.trip_number ?? null,
        licenseWarning,
      };
    })
    .sort((a, b) => {
      const an = `${a.driver.last_name} ${a.driver.first_name}`.toLowerCase();
      const bn = `${b.driver.last_name} ${b.driver.first_name}`.toLowerCase();
      return an.localeCompare(bn);
    });
}

/** Inbound ETA: only from the inbound Trip schedule (expected completion), never FMP outbound pickup. */
export function inboundEtaLabel(inboundTrip: TripListItem | undefined): string {
  if (!inboundTrip?.expected_completion_at) return INBOUND_ETA_NOT_RECORDED;
  return formatShortEta(inboundTrip.expected_completion_at);
}

export function buildInboundRows(
  fmpPlans: FutureMovementPlan[],
  trips: TripListItem[],
): InboundYardRow[] {
  const tripMap = new Map(trips.map((t) => [t.id, t]));
  const rows: InboundYardRow[] = [];
  for (const plan of fmpPlans) {
    if (plan.status === "converted" || plan.status === "cancelled") continue;
    for (const line of plan.lines || []) {
      if (line.inbound_trip_id == null) continue;
      const inboundTrip = tripMap.get(line.inbound_trip_id);
      rows.push({
        key: `fmp-${plan.id}-in-${line.inbound_trip_id}-load-${line.load_id}`,
        tripNumber: inboundTrip?.trip_number ?? `Trip #${line.inbound_trip_id}`,
        tripId: line.inbound_trip_id,
        loadNumber: line.load_number ?? `Load ${line.load_id}`,
        loadId: line.load_id,
        etaLabel: inboundEtaLabel(inboundTrip),
        fmpPlanId: plan.id,
      });
    }
  }
  return rows.slice(0, 40);
}

export const DISPATCH_UNASSIGNED_LOADS_PAGE_SIZE = 50;

export function buildUnassignedLoadAssignRows(loads: Load[]): AssignQueueRow[] {
  return loads.map((load) => {
    const loadNumber = (load.load_number || "").trim() || `Load ${load.id}`;
    const route = formatRouteFromStops(load.stops ?? []);
    const pickup = firstPickupAppointmentDate(load.stops) || "—";
    const rate =
      load.rate != null && String(load.rate).trim() !== "" ? `$${load.rate}` : "—";
    return {
      kind: "unassigned_load",
      id: load.id,
      label: loadNumber,
      sublabel: `${route} · PU ${pickup} · ${rate}`,
      href: `/loads/${load.id}`,
      badge: "Unassigned",
    };
  });
}

export function mergeAssignQueue(unassignedLoads: Load[], tripAndFmpRows: AssignQueueRow[]): AssignQueueRow[] {
  return [...buildUnassignedLoadAssignRows(unassignedLoads), ...tripAndFmpRows];
}

export function buildAssignQueue(
  fmpPlans: FutureMovementPlan[],
  trips: TripListItem[],
): AssignQueueRow[] {
  const rows: AssignQueueRow[] = [];
  for (const plan of fmpPlans) {
    const st = (plan.status || "").toLowerCase();
    if (st === "converted" || st === "cancelled") continue;
    if (plan.converted_trip_id != null) continue;
    const loads = plan.lines?.length ?? 0;
    rows.push({
      kind: "fmp",
      id: plan.id,
      label: `Future plan #${plan.id}`,
      sublabel: plan.driver_id ? "Driver set — convert in workspace" : "Unassigned onward movement",
      href: `/dispatch/future-plans/${plan.id}`,
      loadCount: loads,
    });
  }
  for (const trip of trips) {
    const st = (trip.status || "").toLowerCase();
    if (trip.cancelled_at || trip.completed_at) continue;
    if (st === "assigned") continue;
    if (st !== "planned") continue;

    if (trip.driver_id == null) {
      rows.push({
        kind: "trip",
        id: trip.id,
        label: trip.trip_number,
        sublabel: "Planned trip — needs driver",
        href: `/trips/${trip.id}`,
        loadCount: trip.member_load_count ?? 0,
        queueKind: "needs_driver",
      });
      continue;
    }
    const needsTruck = trip.truck_id == null;
    const needsTrailer = trip.trailer_id == null;
    if (needsTruck || needsTrailer) {
      const parts = [needsTruck ? "truck" : null, needsTrailer ? "trailer" : null].filter(Boolean);
      rows.push({
        kind: "trip",
        id: trip.id,
        label: trip.trip_number,
        sublabel: `Planned trip — needs ${parts.join(" & ")}`,
        href: `/trips/${trip.id}`,
        loadCount: trip.member_load_count ?? 0,
        queueKind: "needs_equipment",
      });
    }
  }
  rows.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "fmp" ? -1 : 1;
    return b.id - a.id;
  });
  return rows;
}

export function tripsFetchMayBeIncomplete(fetched: TripListItem[], total: number): boolean {
  return total > fetched.length;
}

export type DispatchHomeState = {
  loading: boolean;
  error: string | null;
  partialErrors: string[];
  drivers: DriverAvailabilityRow[];
  inbound: InboundYardRow[];
  assignQueue: AssignQueueRow[];
  podPanel: PodPanelState;
  refetch: () => void;
};

export function useDispatchHomeDashboard(): DispatchHomeState {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [partialErrors, setPartialErrors] = useState<string[]>([]);
  const [drivers, setDrivers] = useState<DriverAvailabilityRow[]>([]);
  const [inbound, setInbound] = useState<InboundYardRow[]>([]);
  const [assignQueue, setAssignQueue] = useState<AssignQueueRow[]>([]);

  const podPanel: PodPanelState = useMemo(
    () => ({ connected: false, message: POD_PANEL_DISCONNECTED_MESSAGE }),
    [],
  );

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    const partial: string[] = [];

    let driverList: Driver[] = [];
    let tripItems: TripListItem[] = [];
    let tripTotal = 0;
    let fmpItems: FutureMovementPlan[] = [];

    try {
      driverList = await listDrivers({ limit: 80, include_inactive: false });
    } catch (e) {
      partial.push(`drivers: ${e instanceof Error ? e.message : "failed"}`);
    }

    try {
      const trips = await listTrips({ page: 1, size: 80 });
      tripItems = trips.items ?? [];
      tripTotal = trips.total ?? tripItems.length;
    } catch (e) {
      partial.push(`trips: ${e instanceof Error ? e.message : "failed"}`);
      tripTotal = 0;
    }

    try {
      const fmp = await listFutureMovementPlans({ page: 1, size: 50 });
      fmpItems = fmp.items ?? [];
    } catch (e) {
      partial.push(`future plans: ${e instanceof Error ? e.message : "failed"}`);
    }

    let unassignedLoads: Load[] = [];
    try {
      const unassigned = await listLoads({
        dispatch_unassigned: true,
        page: 1,
        size: DISPATCH_UNASSIGNED_LOADS_PAGE_SIZE,
      });
      unassignedLoads = unassigned.items ?? [];
    } catch (e) {
      partial.push(`unassigned loads: ${e instanceof Error ? e.message : "failed"}`);
    }

    const tripsIncomplete = tripItems.length > 0 && tripsFetchMayBeIncomplete(tripItems, tripTotal);

    setDrivers(
      buildDriverRows(driverList, tripItems, {
        tripsListMayBeIncomplete: tripsIncomplete || partial.some((p) => p.startsWith("trips:")),
      }),
    );
    setInbound(buildInboundRows(fmpItems, tripItems));
    setAssignQueue(mergeAssignQueue(unassignedLoads, buildAssignQueue(fmpItems, tripItems)));

    setPartialErrors(partial);
    setLoading(false);
    if (partial.length && !driverList.length && !tripItems.length) {
      setError(partial.join(" | "));
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return useMemo(
    () => ({
      loading,
      error,
      partialErrors,
      drivers,
      inbound,
      assignQueue,
      podPanel,
      refetch,
    }),
    [loading, error, partialErrors, drivers, inbound, assignQueue, podPanel, refetch],
  );
}
