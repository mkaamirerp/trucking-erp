import { useCallback, useEffect, useMemo, useState } from "react";
import {
  type Driver,
  type FutureMovementPlan,
  type Load,
  type TripListItem,
  listDrivers,
  listFutureMovementPlans,
  listLoadPodEvidence,
  listLoads,
  listTrips,
} from "../api";

const OPEN_TRIP_STATUSES = new Set(["planned", "assigned", "active"]);
const POD_PROBE_LIMIT = 12;

export type DriverAvailabilityRow = {
  driver: Driver;
  status: "available" | "assigned" | "inactive";
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
      needsDriver: boolean;
    };

export type PodGapRow = {
  loadId: number;
  loadNumber: string;
  href: string;
  deliveredHint: string;
  podChecked: boolean;
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

export function buildDriverRows(drivers: Driver[], trips: TripListItem[]): DriverAvailabilityRow[] {
  const tripByDriver = new Map<number, TripListItem>();
  for (const t of trips) {
    if (t.driver_id == null || t.cancelled_at) continue;
    const st = (t.status || "").toLowerCase();
    if (!OPEN_TRIP_STATUSES.has(st)) continue;
    tripByDriver.set(t.driver_id, t);
  }

  return drivers
    .filter((d) => d.is_active)
    .map((driver) => {
      const trip = tripByDriver.get(driver.id);
      let licenseWarning: string | null = null;
      if (driver.license_expiry_date) {
        const exp = new Date(driver.license_expiry_date);
        const days = (exp.getTime() - Date.now()) / (86400 * 1000);
        if (days < 0) licenseWarning = "License expired";
        else if (days <= 30) licenseWarning = "License expiring soon";
      }
      if (!trip) {
        return {
          driver,
          status: "available" as const,
          truckLabel: null,
          tripNumber: null,
          licenseWarning,
        };
      }
      const truckLabel = trip.truck?.unit_number ? `Trk ${trip.truck.unit_number}` : null;
      return {
        driver,
        status: "assigned" as const,
        truckLabel,
        tripNumber: trip.trip_number,
        licenseWarning,
      };
    })
    .sort((a, b) => {
      const an = `${a.driver.last_name} ${a.driver.first_name}`.toLowerCase();
      const bn = `${b.driver.last_name} ${b.driver.first_name}`.toLowerCase();
      return an.localeCompare(bn);
    });
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
      const trip = tripMap.get(line.inbound_trip_id);
      rows.push({
        key: `fmp-${plan.id}-in-${line.inbound_trip_id}-load-${line.load_id}`,
        tripNumber: trip?.trip_number ?? `Trip #${line.inbound_trip_id}`,
        tripId: line.inbound_trip_id,
        loadNumber: line.load_number ?? `Load ${line.load_id}`,
        loadId: line.load_id,
        etaLabel: formatShortEta(plan.planned_start_at ?? trip?.expected_completion_at ?? trip?.planned_start_at),
        fmpPlanId: plan.id,
      });
    }
  }
  return rows.slice(0, 40);
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
    if (st !== "planned" && st !== "assigned") continue;
    if (trip.cancelled_at || trip.completed_at) continue;
    const needsDriver = trip.driver_id == null;
    rows.push({
      kind: "trip",
      id: trip.id,
      label: trip.trip_number,
      sublabel: needsDriver ? "Planned trip — assign driver" : `Trip · ${st}`,
      href: `/trips/${trip.id}`,
      loadCount: trip.member_load_count ?? 0,
      needsDriver,
    });
  }
  rows.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "fmp" ? -1 : 1;
    return b.id - a.id;
  });
  return rows;
}

async function probePodGaps(loads: Load[]): Promise<PodGapRow[]> {
  const candidates = loads.slice(0, POD_PROBE_LIMIT);
  const gaps: PodGapRow[] = [];
  for (const load of candidates) {
    try {
      const items = await listLoadPodEvidence(load.id);
      if (!items.length) {
        gaps.push({
          loadId: load.id,
          loadNumber: load.load_number,
          href: `/loads/${load.id}`,
          deliveredHint: load.status || "delivered",
          podChecked: true,
        });
      }
    } catch {
      gaps.push({
        loadId: load.id,
        loadNumber: load.load_number,
        href: `/loads/${load.id}`,
        deliveredHint: load.status || "delivered",
        podChecked: false,
      });
    }
  }
  return gaps;
}

export type DispatchHomeState = {
  loading: boolean;
  error: string | null;
  partialErrors: string[];
  drivers: DriverAvailabilityRow[];
  inbound: InboundYardRow[];
  assignQueue: AssignQueueRow[];
  podGaps: PodGapRow[];
  podNote: string | null;
  refetch: () => void;
};

export function useDispatchHomeDashboard(): DispatchHomeState {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [partialErrors, setPartialErrors] = useState<string[]>([]);
  const [drivers, setDrivers] = useState<DriverAvailabilityRow[]>([]);
  const [inbound, setInbound] = useState<InboundYardRow[]>([]);
  const [assignQueue, setAssignQueue] = useState<AssignQueueRow[]>([]);
  const [podGaps, setPodGaps] = useState<PodGapRow[]>([]);
  const [podNote, setPodNote] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    const partial: string[] = [];

    let driverList: Driver[] = [];
    let tripItems: TripListItem[] = [];
    let fmpItems: FutureMovementPlan[] = [];
    let deliveredLoads: Load[] = [];

    try {
      driverList = await listDrivers({ limit: 80, include_inactive: false });
    } catch (e) {
      partial.push(`drivers: ${e instanceof Error ? e.message : "failed"}`);
    }

    try {
      const trips = await listTrips({ page: 1, size: 80 });
      tripItems = trips.items ?? [];
    } catch (e) {
      partial.push(`trips: ${e instanceof Error ? e.message : "failed"}`);
    }

    try {
      const fmp = await listFutureMovementPlans({ page: 1, size: 50 });
      fmpItems = fmp.items ?? [];
    } catch (e) {
      partial.push(`future plans: ${e instanceof Error ? e.message : "failed"}`);
    }

    try {
      const loads = await listLoads({ status: ["delivered"], page: 1, size: POD_PROBE_LIMIT + 8 });
      deliveredLoads = loads.items ?? [];
    } catch (e) {
      partial.push(`delivered loads: ${e instanceof Error ? e.message : "failed"}`);
    }

    setDrivers(buildDriverRows(driverList, tripItems));
    setInbound(buildInboundRows(fmpItems, tripItems));
    setAssignQueue(buildAssignQueue(fmpItems, tripItems));

    if (deliveredLoads.length === 0) {
      setPodGaps([]);
      setPodNote(partial.find((p) => p.startsWith("delivered")) ? null : "No delivered loads in the current page.");
    } else {
      const gaps = await probePodGaps(deliveredLoads);
      setPodGaps(gaps);
      const total = deliveredLoads.length;
      setPodNote(
        total > POD_PROBE_LIMIT
          ? `Showing POD check for first ${POD_PROBE_LIMIT} of ${total} recent delivered loads.`
          : null,
      );
    }

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
      podGaps,
      podNote,
      refetch,
    }),
    [loading, error, partialErrors, drivers, inbound, assignQueue, podGaps, podNote, refetch],
  );
}
